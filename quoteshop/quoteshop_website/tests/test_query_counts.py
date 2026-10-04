"""Query-count budgets (CONTRACTS §7.1 / §9.9, TESTING §2.8). TEST_MATRIX NFR-01, NFR-02, NFR-03 (phase-2 pages).

Fixture: 24 published items (2 photos, 1 price each) in two groups, products_per_page = 24.
"Cold" = catalog Redis keys (and website page cache) empty; "warm" = second call. Settings docs
(frappe.get_cached_doc) stay cached in both: they are only invalidated by a settings save, not by catalog writes.

Proposed page budgets (test-lead, not yet in CONTRACTS): cold <= 12, warm <= 6 for `/` and `/c/<route>`.
Cold = list_products (<= 5) + get_categories (<= 2) + framework/route resolution (<= 5).
Warm = catalog (<= 1 + <= 1) + framework (<= 4).
"""

from unittest.mock import patch

import frappe

from quoteshop.quoteshop_catalog.tests.base import (
	CatalogTestCase,
	get_categories,
	get_product,
	list_products,
	route_of,
)
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_group_tree,
	make_homepage_settings,
	make_published_item,
)
from quoteshop.quoteshop_website.tests.helpers import render

LIST_COLD, LIST_WARM = 5, 1
PRODUCT_COLD, PRODUCT_WARM = 8, 1
PAGE_COLD, PAGE_WARM = 12, 6


class TestQueryCounts(CatalogTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_homepage_settings(hero_title="Query Count Hero")
		make_group_tree({"_QS QC Odd": {}, "_QS QC Even": {}})
		for i in range(1, 25):
			code = f"_QS-QC{i:02}"
			make_published_item(
				code,
				rate=100 + i,
				group="_QS QC Odd" if i % 2 else "_QS QC Even",
				item_name=f"Query Count Item {i:02}",
				qs_display_order=i,
			)
			for n in (1, 2):
				frappe.get_doc(
					{
						"doctype": "QS Item Photo",
						"parent": code,
						"parenttype": "Item",
						"parentfield": "qs_photos",
						"idx": n,
						"image": f"/files/qc{i}-{n}.png",
						"alt_text": f"Alt {i} {n}",
						"thumb": f"/files/qc{i}-{n}-400.webp",
						"medium": f"/files/qc{i}-{n}-1000.webp",
						"large": f"/files/qc{i}-{n}-1800.webp",
					}
				).insert(ignore_permissions=True)
		cls.product_route = route_of("Item", "_QS-QC07")
		cls.category_route = route_of("Item Group", "_QS QC Odd")

	def setUp(self):
		super().setUp()
		for doctype in ("QS Store Settings", "QS Homepage Settings", "QS Enquiry Settings"):
			frappe.get_cached_doc(doctype)  # settings cache is independent of the catalog cache
		self.addCleanup(frappe.set_user, "Administrator")
		patcher = patch.dict(frappe.local.conf, {"disable_website_cache": 1})
		patcher.start()
		self.addCleanup(patcher.stop)

	def clear_catalog(self):
		frappe.cache.delete_keys("qs:catalog:")
		frappe.cache.delete_keys("website_page::")

	# --- service (NFR-01, NFR-02) ---------------------------------------------------------------

	def test_list_products_24(self):
		"""NFR-01: <= 5 cold, <= 1 warm"""
		with self.assertQueryCount(LIST_COLD):
			cold = list_products()
		self.assertEqual((len(cold["items"]), cold["total"], cold["has_more"]), (24, 24, False))
		with self.assertQueryCount(LIST_WARM):
			warm = list_products()
		self.assertEqual(warm, cold)

	def test_list_products_filtered_24_stays_in_budget(self):
		"""Category and search take the same single-query path."""
		with self.assertQueryCount(LIST_COLD):
			result = list_products(category=self.category_route, q="query count")
		self.assertEqual(result["total"], 12)

	def test_get_product(self):
		"""NFR-02: <= 8 cold, <= 1 warm"""
		with self.assertQueryCount(PRODUCT_COLD):
			cold = get_product(self.product_route)
		self.assertEqual(len(cold["photos"]), 2)
		with self.assertQueryCount(PRODUCT_WARM):
			warm = get_product(self.product_route)
		self.assertEqual(warm, cold)

	def test_get_categories(self):
		with self.assertQueryCount(2):
			cold = get_categories()
		self.assertEqual(len(cold), 2)
		with self.assertQueryCount(PRODUCT_WARM):
			get_categories()

	# --- pages ------------------------------------------------------------------------------------

	def assert_page_budget(self, route, query=None, cards=None, text=None):
		"""Cold and warm render of `route` stay in budget AND show real content (not a login/404 page)."""

		def check(page):
			self.assertEqual(page.status, 200)
			if cards is not None:
				self.assertEqual(len(set(page.links("/p/"))), cards)
			if text:
				self.assertIn(text, page.text)

		render(route, query)  # loads controllers / meta once: framework warm-up is not the page's cost
		self.clear_catalog()
		with self.assertQueryCount(PAGE_COLD):
			cold = render(route, query)
		check(cold)
		with self.assertQueryCount(PAGE_WARM):
			warm = render(route, query)
		check(warm)
		self.assertEqual(warm.text, cold.text)

	def test_home_page(self):
		"""`/` with 24 cards"""
		self.assert_page_budget("/", cards=24, text="Query Count Hero")

	def test_category_page(self):
		"""`/c/<route>` with 12 cards"""
		self.assert_page_budget(f"/c/{self.category_route}", cards=12)

	def test_product_page(self):
		self.assert_page_budget(f"/p/{self.product_route}", text="Query Count Item 07")

	def test_search_page(self):
		self.assert_page_budget("/search", {"q": "query"}, cards=24)
