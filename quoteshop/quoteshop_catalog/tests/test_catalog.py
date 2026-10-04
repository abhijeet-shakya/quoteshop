"""CONTRACTS §7.1 catalog service: list_products / get_product / get_categories.

TEST_MATRIX CAT-01..04, 09..11, 15..18 (service half of CAT-02/05/10/11).
Every test runs in a savepoint (see base.py), so totals are exact. Prices use dates relative to
today (never frozen: the starting-price rule is "valid_from <= today").
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
	make_customer_group,
	make_group_tree,
	make_item_price,
	make_photo,
	make_price_list,
	make_published_item,
	make_territory,
)

CARD_KEYS = {
	"item_code",
	"item_name",
	"route",
	"item_group",
	"group_route",
	"short_description",
	"min_qty",
	"image",
	"starting_price",
	"currency",
	"has_colours",
}
PRODUCT_EXTRA_KEYS = {"description", "colours", "photos", "specs", "related", "lead_time", "uom"}


def days(n):
	return add_days(today(), n)


def update_item(item_code, **values):
	doc = frappe.get_doc("Item", item_code)
	doc.update(values)
	doc.save(ignore_permissions=True)
	return doc


def starting_price(item_code):
	(card,) = [c for c in list_products()["items"] if c["item_code"] == item_code]
	return card["starting_price"]


class TestPublishedOnly(CatalogTestCase):
	def test_only_published_enabled_items_listed(self):
		"""CAT-01"""
		make_published_item("_QS-PUB", rate=10)
		make_published_item("_QS-DRAFT", rate=10, published=0)
		make_published_item("_QS-OFF", rate=10, disabled=1)
		make_published_item("_QS-TPL", rate=10)
		frappe.db.set_value("Item", "_QS-TPL", "has_variants", 1)  # template items never listed
		result = list_products()
		self.assertEqual(codes(result), ["_QS-PUB"])
		self.assertEqual(result["total"], 1)

	def test_unpublish_removes_item_everywhere(self):
		"""CAT-03/04/05 (service half): unpublish -> gone from listing, search, product page, even when cached."""
		make_published_item("_QS-UNPUB", rate=10, item_name="Unpublish Me")
		route = route_of("Item", "_QS-UNPUB")
		self.assertEqual(codes(list_products()), ["_QS-UNPUB"])  # warms the list cache
		self.assertEqual(codes(list_products(q="unpublish")), ["_QS-UNPUB"])
		self.assertEqual(get_product(route)["item_code"], "_QS-UNPUB")  # warms the product cache

		update_item("_QS-UNPUB", qs_published=0)

		self.assertEqual(codes(list_products()), [])
		self.assertEqual(codes(list_products(q="unpublish")), [])
		with self.assertRaises(frappe.DoesNotExistError):
			get_product(route)

	def test_disabling_item_removes_it(self):
		make_published_item("_QS-DIS", rate=10)
		route = route_of("Item", "_QS-DIS")
		self.assertEqual(codes(list_products()), ["_QS-DIS"])
		update_item("_QS-DIS", disabled=1)
		self.assertEqual(codes(list_products()), [])
		with self.assertRaises(frappe.DoesNotExistError):
			get_product(route)

	def test_unknown_route_does_not_exist(self):
		with self.assertRaises(frappe.DoesNotExistError):
			get_product("no-such-product")

	def test_group_publish_state_does_not_hide_items(self):
		"""§7.1b: an item is listed iff qs_published, enabled, not a template; its group does not matter."""
		make_group_tree({"_QS Unpublished Home": {}}, published=0)
		make_published_item("_QS-IN-HIDDEN-GROUP", rate=10, group="_QS Unpublished Home")
		self.assertEqual(codes(list_products()), ["_QS-IN-HIDDEN-GROUP"])

	def test_nested_published_groups_are_flat_in_categories(self):
		"""§7.1b: chips = all published groups, flat (children included), qs_display_order, name."""
		make_group_tree({"_QS Flat Parent": {"_QS Flat Child": {}}})
		self.assertEqual([c["name"] for c in get_categories()], ["_QS Flat Child", "_QS Flat Parent"])

	def test_only_published_groups_in_categories(self):
		"""CAT-02 (service half): get_categories exposes published groups only, ordered by qs_display_order, name."""
		make_group_tree({"_QS Cat B": {}, "_QS Cat A": {}, "_QS Cat C": {}})
		make_group_tree({"_QS Cat Hidden": {}}, published=0)
		for name, order in (("_QS Cat B", 2), ("_QS Cat A", 2), ("_QS Cat C", 1)):
			group = frappe.get_doc("Item Group", name)
			group.qs_display_order = order
			group.save(ignore_permissions=True)
		cats = get_categories()
		self.assertEqual([c["name"] for c in cats], ["_QS Cat C", "_QS Cat A", "_QS Cat B"])
		for cat in cats:
			self.assertEqual(set(cat), {"name", "route", "image", "display_order"})
			self.assertEqual(cat["route"], route_of("Item Group", cat["name"]))
		self.assertEqual([c["display_order"] for c in cats], [1, 2, 2])

	def test_category_image(self):
		make_group_tree({"_QS Cat Img": {}})
		group = frappe.get_doc("Item Group", "_QS Cat Img")
		group.qs_image = "/files/_qs_cat.png"
		group.save(ignore_permissions=True)
		(cat,) = get_categories()
		self.assertEqual(cat["image"], "/files/_qs_cat.png")

	def test_unpublished_group_leaves_categories(self):
		make_group_tree({"_QS Cat Gone": {}})
		self.assertEqual([c["name"] for c in get_categories()], ["_QS Cat Gone"])
		group = frappe.get_doc("Item Group", "_QS Cat Gone")
		group.qs_published = 0
		group.save(ignore_permissions=True)
		self.assertEqual(get_categories(), [])

	def test_catalog_functions_are_guest_get_apis(self):
		"""§7.1: exposed @frappe.whitelist(allow_guest=True, methods=["GET"])."""
		from quoteshop.quoteshop_catalog import catalog

		for fn in (catalog.list_products, catalog.get_product, catalog.get_categories):
			self.assertIn(fn, frappe.guest_methods, fn.__name__)
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[fn], ["GET"], fn.__name__)


class TestStartingPrice(CatalogTestCase):
	def test_price_from_starting_list_only(self):
		"""CAT-09"""
		make_published_item("_QS-LIST", rate=100)
		make_item_price("_QS-LIST", 55, price_list=make_price_list("_QS Test Other List"))
		self.assertEqual(starting_price("_QS-LIST"), 100.0)

	def test_card_currency_from_price_list(self):
		make_published_item("_QS-CUR", rate=100)
		(card,) = list_products()["items"]
		self.assertEqual(card["currency"], "INR")

	def test_newest_valid_from_wins(self):
		make_published_item("_QS-NEW")
		make_item_price("_QS-NEW", 80, valid_from=days(-30))
		make_item_price("_QS-NEW", 90, valid_from=days(-10))
		make_item_price("_QS-NEW", 70, valid_from=days(-20))
		self.assertEqual(starting_price("_QS-NEW"), 90.0)

	def test_expired_price_ignored(self):
		make_published_item("_QS-EXP")
		make_item_price("_QS-EXP", 95, valid_from=days(-60))
		make_item_price("_QS-EXP", 60, valid_from=days(-30), valid_upto=days(-1))  # newer but expired
		self.assertEqual(starting_price("_QS-EXP"), 95.0)

	def test_only_expired_price_is_none(self):
		make_published_item("_QS-EXP2")
		make_item_price("_QS-EXP2", 60, valid_from=days(-30), valid_upto=days(-1))
		self.assertIsNone(starting_price("_QS-EXP2"))

	def test_future_price_ignored(self):
		make_published_item("_QS-FUT")
		make_item_price("_QS-FUT", 120, valid_from=days(-5))
		make_item_price("_QS-FUT", 50, valid_from=days(5))
		self.assertEqual(starting_price("_QS-FUT"), 120.0)

	def test_only_future_price_is_none(self):
		make_published_item("_QS-FUT2")
		make_item_price("_QS-FUT2", 50, valid_from=days(5))
		self.assertIsNone(starting_price("_QS-FUT2"))

	def test_price_valid_until_today_still_counts(self):
		make_published_item("_QS-LAST")
		make_item_price("_QS-LAST", 77, valid_from=days(-5), valid_upto=today())
		self.assertEqual(starting_price("_QS-LAST"), 77.0)

	def test_price_valid_from_today_counts(self):
		make_published_item("_QS-FIRST")
		make_item_price("_QS-FIRST", 66, valid_from=today())
		self.assertEqual(starting_price("_QS-FIRST"), 66.0)

	def _customer(self):
		name = "_QS Test Price Customer"
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Individual",
					"customer_group": make_customer_group(),
					"territory": make_territory(),
				}
			).insert(ignore_permissions=True)
		return name

	def test_customer_specific_price_ignored(self):
		make_published_item("_QS-CUST", rate=100)
		make_item_price("_QS-CUST", 10, customer=self._customer(), valid_from=days(-1))
		self.assertEqual(starting_price("_QS-CUST"), 100.0)

	def test_only_customer_specific_price_is_none(self):
		make_published_item("_QS-CUST2")
		make_item_price("_QS-CUST2", 10, customer=self._customer())
		self.assertIsNone(starting_price("_QS-CUST2"))

	def test_price_in_other_uom_ignored(self):
		"""§2.4: uom must equal the item's stock UOM."""
		make_published_item("_QS-UOM")
		if not frappe.db.exists("UOM", "_QS Box"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "_QS Box"}).insert(ignore_permissions=True)
		item = frappe.get_doc("Item", "_QS-UOM")
		item.append("uoms", {"uom": "_QS Box", "conversion_factor": 10})
		item.save(ignore_permissions=True)
		make_item_price("_QS-UOM", 999, uom="_QS Box", valid_from=days(-1))
		make_item_price("_QS-UOM", 40, valid_from=days(-9))
		self.assertEqual(starting_price("_QS-UOM"), 40.0)

	def test_null_valid_from_counts_as_valid(self):
		"""§7.1b: IFNULL(valid_from, '1900-01-01') <= today"""
		make_published_item("_QS-NULLFROM")
		name = make_item_price("_QS-NULLFROM", 45)
		frappe.db.set_value("Item Price", name, "valid_from", None)
		self.assertEqual(starting_price("_QS-NULLFROM"), 45.0)

	def test_dated_price_beats_null_valid_from(self):
		make_published_item("_QS-NULLFROM2")
		name = make_item_price("_QS-NULLFROM2", 45)
		frappe.db.set_value("Item Price", name, "valid_from", None)
		make_item_price("_QS-NULLFROM2", 50, valid_from=days(-2))
		self.assertEqual(starting_price("_QS-NULLFROM2"), 50.0)

	def test_no_price_is_none(self):
		make_published_item("_QS-NOPRICE")
		self.assertIsNone(starting_price("_QS-NOPRICE"))

	def test_price_on_request_when_hidden_globally(self):
		"""CAT-10 (service half)"""
		make_published_item("_QS-GLOBAL", rate=100)
		self.assertEqual(starting_price("_QS-GLOBAL"), 100.0)
		self.set_settings(show_starting_prices=0)
		self.assertIsNone(starting_price("_QS-GLOBAL"))
		self.assertIsNone(get_product(route_of("Item", "_QS-GLOBAL"))["starting_price"])

	def test_price_on_request_when_hidden_per_item(self):
		"""CAT-11 (service half)"""
		make_published_item("_QS-HIDE", rate=100, qs_hide_price=1)
		make_published_item("_QS-SHOW", rate=100)
		self.assertIsNone(starting_price("_QS-HIDE"))
		self.assertEqual(starting_price("_QS-SHOW"), 100.0)
		self.assertIsNone(get_product(route_of("Item", "_QS-HIDE"))["starting_price"])


class TestPagination(CatalogTestCase):
	def _items(self, n):
		for i in range(1, n + 1):
			make_published_item(f"_QS-P{i:02}", rate=10, item_name=f"Pager {i:02}", qs_display_order=i)

	def test_pagination(self):
		"""CAT-15: page_size = products_per_page; middle and last page; has_more; total"""
		self._items(12)
		self.set_settings(products_per_page=5)
		first = list_products()
		self.assertEqual(
			(first["page"], first["page_size"], first["total"], first["has_more"]), (1, 5, 12, True)
		)
		self.assertEqual(codes(first), [f"_QS-P{i:02}" for i in range(1, 6)])
		middle = list_products(page=2)
		self.assertEqual((middle["page"], middle["has_more"]), (2, True))
		self.assertEqual(codes(middle), [f"_QS-P{i:02}" for i in range(6, 11)])
		last = list_products(page=3)
		self.assertEqual((last["page"], last["has_more"], last["total"]), (3, False, 12))
		self.assertEqual(codes(last), ["_QS-P11", "_QS-P12"])

	def test_exact_multiple_has_no_more(self):
		self._items(10)
		self.set_settings(products_per_page=5)
		self.assertFalse(list_products(page=2)["has_more"])
		self.assertTrue(list_products(page=1)["has_more"])

	def test_page_below_one_is_page_one(self):
		self._items(3)
		for bad in (0, -4):
			result = list_products(page=bad)
			self.assertEqual(result["page"], 1)
			self.assertEqual(codes(result), ["_QS-P01", "_QS-P02", "_QS-P03"])

	def test_page_as_string_is_accepted(self):
		"""§7.1b: page = cint(page) (GET sends strings)"""
		self._items(3)
		self.set_settings(products_per_page=2)
		result = list_products(page="2")
		self.assertEqual((result["page"], codes(result)), (2, ["_QS-P03"]))
		self.assertEqual(list_products(page="junk")["page"], 1)

	def test_page_past_the_end_is_empty(self):
		self._items(3)
		result = list_products(page=9)
		self.assertEqual((result["items"], result["has_more"], result["total"]), ([], False, 3))

	def test_default_page_size_is_24(self):
		self._items(26)
		result = list_products()
		self.assertEqual((result["page_size"], len(result["items"]), result["has_more"]), (24, 24, True))
		self.assertEqual(len(list_products(page=2)["items"]), 2)

	def test_stable_ordering_across_pages(self):
		"""CAT-18: qs_display_order, item_name, name; pages concatenate to the full order without repeats."""
		spec = [
			("_QS-O1", "Bravo", 2),
			("_QS-O2", "Alpha", 2),
			("_QS-O3", "Zulu", 1),
			("_QS-O4B", "Same", 3),
			("_QS-O4A", "Same", 3),
			("_QS-O5", "Echo", 0),
		]
		for code, name, order in spec:
			make_published_item(code, rate=10, item_name=name, qs_display_order=order)
		expected = ["_QS-O5", "_QS-O3", "_QS-O2", "_QS-O1", "_QS-O4A", "_QS-O4B"]
		self.assertEqual(codes(list_products()), expected)
		self.set_settings(products_per_page=2)
		paged = [c for page in (1, 2, 3) for c in codes(list_products(page=page))]
		self.assertEqual(paged, expected)


class TestCategoryFilter(CatalogTestCase):
	def _tree(self):
		make_group_tree(
			{"_QS Root": {"_QS Mid": {"_QS Leaf": {}}, "_QS Side": {}}, "_QS Other": {}},
		)
		for code, group in (
			("_QS-ROOT", "_QS Root"),
			("_QS-MID", "_QS Mid"),
			("_QS-LEAF", "_QS Leaf"),
			("_QS-SIDE", "_QS Side"),
			("_QS-OTHER", "_QS Other"),
		):
			make_published_item(code, rate=10, group=group, item_name=f"Tree {code}")

	def test_category_filter_includes_descendants(self):
		"""CAT-16"""
		self._tree()
		by_group = lambda name: sorted(codes(list_products(category=route_of("Item Group", name))))  # noqa: E731
		self.assertEqual(by_group("_QS Leaf"), ["_QS-LEAF"])
		self.assertEqual(by_group("_QS Mid"), ["_QS-LEAF", "_QS-MID"])
		self.assertEqual(by_group("_QS Root"), ["_QS-LEAF", "_QS-MID", "_QS-ROOT", "_QS-SIDE"])
		self.assertEqual(by_group("_QS Other"), ["_QS-OTHER"])

	def test_category_total_and_unfiltered(self):
		self._tree()
		self.assertEqual(list_products()["total"], 5)
		self.assertEqual(list_products(category=route_of("Item Group", "_QS Root"))["total"], 4)

	def test_category_and_search_combine(self):
		self._tree()
		result = list_products(category=route_of("Item Group", "_QS Root"), q="tree _qs-m")
		self.assertEqual(codes(result), ["_QS-MID"])

	def test_unpublished_descendant_group_still_included(self):
		"""§7.1b: published category + ALL descendants, published or not."""
		self._tree()
		leaf = frappe.get_doc("Item Group", "_QS Leaf")
		leaf.qs_published = 0
		leaf.save(ignore_permissions=True)
		self.assertEqual(
			sorted(codes(list_products(category=route_of("Item Group", "_QS Mid")))), ["_QS-LEAF", "_QS-MID"]
		)

	def test_unpublished_category_does_not_exist(self):
		"""§7.1b: unknown or unpublished category -> DoesNotExistError"""
		self._tree()
		route = route_of("Item Group", "_QS Other")
		other = frappe.get_doc("Item Group", "_QS Other")
		other.qs_published = 0
		other.save(ignore_permissions=True)
		with self.assertRaises(frappe.DoesNotExistError):
			list_products(category=route)

	def test_unknown_category_does_not_exist(self):
		with self.assertRaises(frappe.DoesNotExistError):
			list_products(category="no-such-category")

	def test_card_group_fields(self):
		self._tree()
		(card,) = list_products(category=route_of("Item Group", "_QS Leaf"))["items"]
		self.assertEqual(card["item_group"], "_QS Leaf")
		self.assertEqual(card["group_route"], route_of("Item Group", "_QS Leaf"))


class TestSearch(CatalogTestCase):
	def test_search_case_insensitive_over_name_code_description(self):
		"""CAT-17"""
		make_published_item("_QS-S1", rate=1, item_name="Blue Chalk")
		make_published_item("_QS-CHK-9", rate=1, item_name="Other Thing")
		make_published_item("_QS-S3", rate=1, item_name="Plain", qs_short_description="Hand-finished tip")
		make_published_item("_QS-S4", rate=1, item_name="Unrelated")
		self.assertEqual(codes(list_products(q="bLUE cHALK")), ["_QS-S1"])
		self.assertEqual(codes(list_products(q="BLUE")), ["_QS-S1"])
		self.assertEqual(codes(list_products(q="chk-9")), ["_QS-CHK-9"])
		self.assertEqual(codes(list_products(q="HAND-FINISHED")), ["_QS-S3"])
		self.assertEqual(codes(list_products(q="no-such-thing")), [])
		self.assertEqual(list_products(q="no-such-thing")["total"], 0)

	def test_search_substring_match(self):
		make_published_item("_QS-SUB", rate=1, item_name="Premium Billiard Cue")
		self.assertEqual(codes(list_products(q="iard C")), ["_QS-SUB"])

	def test_whitespace_query_is_no_search(self):
		"""§7.1b: q is stripped; whitespace-only = no search"""
		make_published_item("_QS-W1", rate=1)
		make_published_item("_QS-W2", rate=1)
		self.assertEqual(sorted(codes(list_products(q="   "))), ["_QS-W1", "_QS-W2"])

	def test_query_is_stripped(self):
		make_published_item("_QS-STRIP", rate=1, item_name="Stripped Name")
		make_published_item("_QS-OTHER2", rate=1, item_name="Other")
		self.assertEqual(codes(list_products(q="  stripped name  ")), ["_QS-STRIP"])

	def test_empty_search_lists_everything(self):
		make_published_item("_QS-E1", rate=1)
		make_published_item("_QS-E2", rate=1)
		self.assertEqual(sorted(codes(list_products(q=""))), ["_QS-E1", "_QS-E2"])
		self.assertEqual(sorted(codes(list_products(q=None))), ["_QS-E1", "_QS-E2"])

	def test_percent_and_underscore_are_literal(self):
		make_published_item("_QS-PCT", rate=1, item_name="100% Cotton Cloth")
		make_published_item("_QS-ABC", rate=1, item_name="abc plain")
		make_published_item("_QS-AUS", rate=1, item_name="a_c underscore")
		self.assertEqual(codes(list_products(q="100%")), ["_QS-PCT"])
		self.assertEqual(codes(list_products(q="%")), ["_QS-PCT"])  # not "match everything"
		self.assertEqual(codes(list_products(q="a_c")), ["_QS-AUS"])  # `_` is not "any one char"

	def test_query_longer_than_100_chars_is_truncated(self):
		make_published_item("_QS-LONG", rate=1, item_name="x" * 100)
		self.assertEqual(codes(list_products(q="x" * 100 + "y" * 50)), ["_QS-LONG"])
		self.assertEqual(codes(list_products(q="x" * 101)), ["_QS-LONG"])

	def test_sql_metacharacters_are_inert(self):
		make_published_item("_QS-INJ", rate=1)
		result = list_products(q="x' OR '1'='1")
		self.assertEqual(codes(result), [])
		self.assertEqual(result["total"], 0)

	def test_search_is_paginated(self):
		for i in range(1, 8):
			make_published_item(f"_QS-F{i}", rate=1, item_name=f"Findme {i}", qs_display_order=i)
		self.set_settings(products_per_page=3)
		page2 = list_products(q="findme", page=2)
		self.assertEqual((page2["total"], page2["has_more"]), (7, True))
		self.assertEqual(codes(page2), ["_QS-F4", "_QS-F5", "_QS-F6"])


class TestCardAndProduct(CatalogTestCase):
	def test_card_shape_and_values(self):
		make_published_item(
			"_QS-CARD",
			rate=250.5,
			item_name="Card Item",
			qs_short_description="Short words",
			qs_min_qty=5,
		)
		(card,) = list_products()["items"]
		self.assertEqual(set(card), CARD_KEYS)
		self.assertEqual(card["item_code"], "_QS-CARD")
		self.assertEqual(card["item_name"], "Card Item")
		self.assertEqual(card["route"], route_of("Item", "_QS-CARD"))
		self.assertTrue(card["route"])
		self.assertEqual(card["short_description"], "Short words")
		self.assertEqual(card["min_qty"], 5)
		self.assertEqual(card["starting_price"], 250.5)
		self.assertIsNone(card["image"])  # no photos

	def test_first_photo_selected(self):
		make_published_item("_QS-PH", rate=1)
		first = {"thumb": "/files/a-400.webp", "medium": "/files/a-1000.webp", "large": "/files/a-1800.webp"}
		second = {"thumb": "/files/b-400.webp", "medium": "/files/b-1000.webp", "large": "/files/b-1800.webp"}
		make_photo("_QS-PH", 10, 10, alt_text="Front view", stem="_qs_ph_a", **first)
		make_photo("_QS-PH", 10, 10, alt_text="Side view", stem="_qs_ph_b", **second)
		(card,) = list_products()["items"]
		self.assertEqual(card["image"], {**first, "alt": "Front view"})
		product = get_product(route_of("Item", "_QS-PH"))
		self.assertEqual(
			product["photos"],
			[{**first, "alt": "Front view", "colour": ""}, {**second, "alt": "Side view", "colour": ""}],
		)
		self.assertEqual(product["image"], card["image"])

	def test_photo_without_sizes_falls_back_to_original(self):
		"""§7.1b: no generated sizes -> thumb/medium/large = original image URL"""
		make_published_item("_QS-NOSIZE", rate=1)
		photo = make_photo("_QS-NOSIZE", 10, 10, alt_text="Raw", stem="_qs_nosize")
		(card,) = list_products()["items"]
		url = photo.file_url
		self.assertEqual(card["image"], {"thumb": url, "medium": url, "large": url, "alt": "Raw"})

	def test_alt_falls_back_to_item_name(self):
		"""§7.1b: alt = alt_text or the item name"""
		make_published_item("_QS-NOALT", rate=1, item_name="Alt Fallback Cue")
		make_photo("_QS-NOALT", 10, 10, stem="_qs_noalt", thumb="/files/n-400.webp")
		(card,) = list_products()["items"]
		self.assertEqual(card["image"]["alt"], "Alt Fallback Cue")
		self.assertEqual(get_product(route_of("Item", "_QS-NOALT"))["photos"][0]["alt"], "Alt Fallback Cue")

	def test_listing_has_one_card_per_item_with_many_photos(self):
		"""The photo join must not duplicate cards."""
		make_published_item("_QS-MANY", rate=1)
		for i in range(3):
			make_photo("_QS-MANY", 10, 10, stem=f"_qs_many_{i}", thumb=f"/files/m{i}-400.webp")
		result = list_products()
		self.assertEqual((codes(result), result["total"]), (["_QS-MANY"], 1))
		self.assertEqual(result["items"][0]["image"]["thumb"], "/files/m0-400.webp")

	def test_product_shape(self):
		make_published_item(
			"_QS-PROD",
			rate=99,
			item_name="Product Item",
			description="<p>Solid <b>ash</b> shaft</p>",
			qs_lead_time=7,
		)
		item = frappe.get_doc("Item", "_QS-PROD")
		item.append("qs_specs", {"label": "Weight", "value": "1.2 kg"})
		item.append("qs_specs", {"label": "Length", "value": "58 in"})
		item.save(ignore_permissions=True)
		product = get_product(route_of("Item", "_QS-PROD"))
		self.assertTrue((CARD_KEYS | PRODUCT_EXTRA_KEYS) <= set(product))
		self.assertEqual(product["item_code"], "_QS-PROD")
		self.assertEqual(product["starting_price"], 99.0)
		self.assertIn("Solid", product["description"])
		self.assertEqual(
			product["specs"], [{"label": "Weight", "value": "1.2 kg"}, {"label": "Length", "value": "58 in"}]
		)
		self.assertEqual(product["lead_time"], 7)
		self.assertEqual(product["uom"], "Nos")
		self.assertEqual(product["photos"], [])
		self.assertEqual(product["colours"], [])
		self.assertFalse(product["has_colours"])
		self.assertEqual(product["related"], [])

	def test_related_items_only_published(self):
		make_published_item("_QS-MAIN", rate=1)
		make_published_item("_QS-REL-OK", rate=1)
		make_published_item("_QS-REL-DRAFT", rate=1, published=0)
		make_published_item("_QS-REL-OFF", rate=1, disabled=1)
		item = frappe.get_doc("Item", "_QS-MAIN")
		for code in ("_QS-REL-OK", "_QS-REL-DRAFT", "_QS-REL-OFF"):
			item.append("qs_related", {"item": code})
		item.save(ignore_permissions=True)
		related = get_product(route_of("Item", "_QS-MAIN"))["related"]
		self.assertEqual([c["item_code"] for c in related], ["_QS-REL-OK"])
		self.assertEqual(set(related[0]), CARD_KEYS)

	def test_unpublishing_related_item_updates_product(self):
		make_published_item("_QS-MAIN2", rate=1)
		make_published_item("_QS-REL2", rate=1)
		item = frappe.get_doc("Item", "_QS-MAIN2")
		item.append("qs_related", {"item": "_QS-REL2"})
		item.save(ignore_permissions=True)
		route = route_of("Item", "_QS-MAIN2")
		self.assertEqual(len(get_product(route)["related"]), 1)  # warm cache
		update_item("_QS-REL2", qs_published=0)
		self.assertEqual(get_product(route)["related"], [])

	def test_product_price_matches_card(self):
		make_published_item("_QS-SAME", rate=321)
		self.assertEqual(get_product(route_of("Item", "_QS-SAME"))["starting_price"], 321.0)
