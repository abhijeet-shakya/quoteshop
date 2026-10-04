"""CONTRACTS §7.1 catalog Redis cache: warm calls skip the DB; every relevant write clears "qs:catalog:".

TEST_MATRIX CAT-06, CAT-07, CAT-08, SET-10 (catalog half), NFR-01/02 (warm half is also asserted here).
Keys: qs:catalog:list:<sha1(json params)>, qs:catalog:product:<route>, qs:catalog:categories.
"""

import frappe
from frappe.utils import add_days, today

from quoteshop.quoteshop_catalog.tests.base import (
	CatalogTestCase,
	codes,
	get_categories,
	get_product,
	list_products,
	route_of,
)
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_group_tree,
	make_item_price,
	make_published_item,
)

PREFIX = "qs:catalog:"


def cached_keys():
	return frappe.cache.get_keys(PREFIX)


def clear_list_keys():
	frappe.cache.delete_keys(PREFIX + "list:")


def read(key):
	return frappe.cache.get_value(key, expires=True, use_local_cache=False)


class TestCatalogCache(CatalogTestCase):
	def setUp(self):
		super().setUp()
		make_published_item("_QS-C1", rate=100, item_name="Cache Item")
		self.route = route_of("Item", "_QS-C1")
		self.group = frappe.db.get_value("Item", "_QS-C1", "item_group")

	def warm(self):
		"""Fill list, product and categories caches; return their values."""
		values = (list_products(), get_product(self.route), get_categories())
		self.assertEqual(len(frappe.cache.get_keys(PREFIX + "list:")), 1)
		self.assertIsNotNone(read(f"{PREFIX}product:{self.route}"))
		self.assertIsNotNone(read(f"{PREFIX}categories"))
		return values

	def assert_invalidated(self, action, check=None):
		"""Warm everything, run `action`, expect no catalog key left and (optionally) fresh data."""
		self.warm()
		action()
		self.assertEqual(cached_keys(), [], "catalog keys survived the write")
		if check:
			check()

	# --- warm calls skip the DB -------------------------------------------------------------------

	def test_warm_calls_hit_cache(self):
		cold = self.warm()
		with self.assertQueryCount(1):
			warm_list = list_products()
		with self.assertQueryCount(1):
			warm_product = get_product(self.route)
		with self.assertQueryCount(1):
			warm_categories = get_categories()
		self.assertEqual((warm_list, warm_product, warm_categories), cold)

	def test_different_params_use_different_list_keys(self):
		"""Non-empty, non-search listings: one key per (category, page) (CONTRACTS §10)."""
		make_published_item("_QS-C2", rate=50, item_name="Cache Item Two")
		self.set_settings(products_per_page=1)
		clear_list_keys()
		first, second = list_products(), list_products(page=2)
		in_group = list_products(category=route_of("Item Group", self.group))
		self.assertEqual(len(frappe.cache.get_keys(PREFIX + "list:")), 3)
		self.assertNotEqual(codes(first), codes(second))
		self.assertEqual((list_products(), list_products(page=2)), (first, second))  # served per key
		self.assertTrue(codes(in_group))

	def test_search_with_q_creates_no_key(self):
		"""CONTRACTS §10: free-text searches are never cached (unbounded keys)."""
		self.assertEqual(codes(list_products(q="cache")), ["_QS-C1"])
		self.assertEqual(codes(list_products(q="nothing")), [])
		self.assertEqual(frappe.cache.get_keys(PREFIX + "list:"), [])

	def test_empty_page_creates_no_key(self):
		"""CONTRACTS §10: pages past the end and empty categories are not cached (?page=N can't fill Redis)."""
		self.assertEqual(codes(list_products(page=99)), [])
		make_group_tree({"_QS Empty Cache Group": {}})
		self.assertEqual(codes(list_products(category=route_of("Item Group", "_QS Empty Cache Group"))), [])
		self.assertEqual(frappe.cache.get_keys(PREFIX + "list:"), [])

	def test_page_renders_create_no_rate_limit_counters(self):
		"""CONTRACTS §10: www pages call the undecorated products()/product()/categories(), so a page view
		never counts against the 600/h catalog API limit."""
		from frappe.utils import get_html_for_route

		frappe.cache.delete_keys("rl:")
		frappe.local.request_ip = "10.0.0.7"  # a decorated call would now create an rl: counter
		self.addCleanup(setattr, frappe.local, "request", None)
		routes = ("/", f"/c/{route_of('Item Group', self.group)}", f"/p/{self.route}", "/search")
		for route in routes:
			frappe.local.form_dict = frappe._dict(q="cache") if route == "/search" else frappe._dict()
			self.assertIn("Cache Item", get_html_for_route(route), route)
		self.assertEqual(frappe.cache.get_keys("rl:"), [])

	def test_catalog_get_apis_rate_limited(self):
		"""CONTRACTS §10: 600 calls/hour per IP on the guest catalog GET APIs."""
		from quoteshop.quoteshop_enquiry.tests.factories import call_api

		frappe.cache.delete_keys("rl:")
		cmd = "quoteshop.quoteshop_catalog.catalog.get_categories"
		for _ in range(600):
			call_api(cmd, http_method="GET", ip="10.0.0.8")
		with self.assertRaises(frappe.RateLimitExceededError):
			call_api(cmd, http_method="GET", ip="10.0.0.8")
		frappe.cache.delete_keys("rl:")

	def test_keys_expire_after_a_day(self):
		self.warm()
		for key in (f"{PREFIX}product:{self.route}", f"{PREFIX}categories"):
			ttl = frappe.cache.ttl(frappe.cache.make_key(key))
			self.assertTrue(86000 < ttl <= 86400, f"{key} ttl {ttl}")

	def test_cache_is_not_cleared_by_unrelated_doc_writes(self):
		self.warm()
		frappe.get_doc({"doctype": "ToDo", "description": "_QS Test unrelated"}).insert(
			ignore_permissions=True
		)
		self.assertEqual(len(frappe.cache.get_keys(PREFIX + "list:")), 1)

	# --- Item ----------------------------------------------------------------------------------------

	def test_item_unpublish_invalidates_cache(self):
		"""CAT-06"""

		def unpublish():
			item = frappe.get_doc("Item", "_QS-C1")
			item.qs_published = 0
			item.save(ignore_permissions=True)

		def check():
			self.assertEqual(codes(list_products()), [])
			with self.assertRaises(frappe.DoesNotExistError):
				get_product(self.route)

		self.assert_invalidated(unpublish, check)

	def test_item_edit_invalidates_cache(self):
		def rename_title():
			item = frappe.get_doc("Item", "_QS-C1")
			item.item_name = "Cache Item Renamed"
			item.save(ignore_permissions=True)

		self.assert_invalidated(
			rename_title,
			lambda: self.assertEqual(get_product(self.route)["item_name"], "Cache Item Renamed"),
		)

	def test_new_published_item_invalidates_cache(self):
		self.assert_invalidated(
			lambda: make_published_item("_QS-C2", rate=5, item_name="Zed Cache Item"),
			lambda: self.assertEqual(codes(list_products()), ["_QS-C1", "_QS-C2"]),
		)

	def test_item_delete_invalidates_cache(self):
		make_published_item("_QS-C3", item_name="Zed Deletable")  # no price: deletable
		self.assert_invalidated(
			lambda: frappe.delete_doc("Item", "_QS-C3", force=1, ignore_permissions=True),
			lambda: self.assertEqual(codes(list_products()), ["_QS-C1"]),
		)

	def test_item_rename_invalidates_cache(self):
		self.assert_invalidated(
			lambda: frappe.rename_doc("Item", "_QS-C1", "_QS-C1R", force=True),
			lambda: self.assertEqual(codes(list_products()), ["_QS-C1R"]),
		)

	# --- Item Group ------------------------------------------------------------------------------------

	def test_item_group_change_invalidates_cache(self):
		"""CAT-08"""
		make_group_tree({"_QS Cache Group B": {}})

		def reorder():
			group = frappe.get_doc("Item Group", "_QS Cache Group B")
			group.qs_display_order = 0
			group.save(ignore_permissions=True)

		self.assert_invalidated(
			reorder,
			lambda: self.assertEqual(next(c["name"] for c in get_categories()), "_QS Cache Group B"),
		)

	def test_item_group_unpublish_invalidates_cache(self):
		make_group_tree({"_QS Cache Group C": {}})

		def unpublish():
			group = frappe.get_doc("Item Group", "_QS Cache Group C")
			group.qs_published = 0
			group.save(ignore_permissions=True)

		self.assert_invalidated(
			unpublish,
			lambda: self.assertNotIn("_QS Cache Group C", [c["name"] for c in get_categories()]),
		)

	def test_item_group_delete_invalidates_cache(self):
		make_group_tree({"_QS Cache Group D": {}})
		self.assert_invalidated(
			lambda: frappe.delete_doc("Item Group", "_QS Cache Group D", force=1, ignore_permissions=True),
			lambda: self.assertNotIn("_QS Cache Group D", [c["name"] for c in get_categories()]),
		)

	def test_item_group_rename_invalidates_cache(self):
		make_group_tree({"_QS Cache Group E": {}})
		self.assert_invalidated(
			lambda: frappe.rename_doc("Item Group", "_QS Cache Group E", "_QS Cache Group E2", force=True),
			lambda: self.assertIn("_QS Cache Group E2", [c["name"] for c in get_categories()]),
		)

	# --- Item Price ----------------------------------------------------------------------------------

	def price(self):
		return list_products()["items"][0]["starting_price"]

	def test_item_price_change_invalidates_cache(self):
		"""CAT-07: new price row, edited rate, deleted row"""
		self.assert_invalidated(
			lambda: make_item_price("_QS-C1", 150, valid_from=today()),
			lambda: self.assertEqual(self.price(), 150.0),
		)

	def test_item_price_edit_invalidates_cache(self):
		name = frappe.db.get_value("Item Price", {"item_code": "_QS-C1"})

		def edit():
			doc = frappe.get_doc("Item Price", name)
			doc.price_list_rate = 120
			doc.save(ignore_permissions=True)

		self.assert_invalidated(edit, lambda: self.assertEqual(self.price(), 120.0))

	def test_item_price_delete_invalidates_cache(self):
		name = frappe.db.get_value("Item Price", {"item_code": "_QS-C1"})
		self.assert_invalidated(
			lambda: frappe.delete_doc("Item Price", name, force=1, ignore_permissions=True),
			lambda: self.assertIsNone(self.price()),
		)

	def test_expired_price_row_is_not_served_after_edit(self):
		"""Editing valid_upto into the past must show up immediately, not after the 24h TTL."""
		name = frappe.db.get_value("Item Price", {"item_code": "_QS-C1"})

		def expire():
			doc = frappe.get_doc("Item Price", name)
			doc.valid_upto = add_days(today(), -1)
			doc.valid_from = add_days(today(), -30)
			doc.save(ignore_permissions=True)

		self.assert_invalidated(expire, lambda: self.assertIsNone(self.price()))

	# --- settings ------------------------------------------------------------------------------------

	def test_store_settings_save_invalidates_cache(self):
		self.assert_invalidated(
			lambda: self.set_settings(show_starting_prices=0),
			lambda: self.assertIsNone(self.price()),
		)

	def test_store_settings_page_size_change_visible_at_once(self):
		make_published_item("_QS-C4", rate=1, item_name="Zed Second")
		self.assert_invalidated(
			lambda: self.set_settings(products_per_page=1),
			lambda: self.assertEqual(
				(codes(list_products()), list_products()["has_more"]), (["_QS-C1"], True)
			),
		)

	def test_homepage_settings_save_invalidates_cache(self):
		def save():
			doc = frappe.get_doc("QS Homepage Settings")
			doc.hero_title = "_QS Test Hero Changed"
			doc.save(ignore_permissions=True)

		self.assert_invalidated(save)

	def test_enquiry_settings_save_invalidates_cache(self):
		def save():
			doc = frappe.get_doc("QS Enquiry Settings")
			doc.quote_validity_days = 21
			doc.save(ignore_permissions=True)

		self.assert_invalidated(save)

	def test_website_clear_cache_hook_clears_catalog(self):
		"""§7.1: hook website_clear_cache -> clear_catalog_cache."""
		from frappe.website.utils import clear_website_cache

		self.assert_invalidated(clear_website_cache)
