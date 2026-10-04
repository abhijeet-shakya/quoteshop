"""CONTRACTS §11 colour options: Item validator (QS Item Colour rows, photo colour tags) and the catalog payloads."""

import frappe

from quoteshop.quoteshop_catalog.tests.base import CatalogTestCase, get_product, list_products, route_of
from quoteshop.quoteshop_enquiry.tests.factories import (
	call_api,
	clear_qs_redis,
	make_colours,
	make_photo,
	make_published_item,
)

ITEM = "_QS-COL"
LIST_COLD, PRODUCT_COLD, WARM = 6, 8, 1  # NFR-01 / NFR-02 budgets (test_query_counts), colours must fit


def save_colours(item_code, rows):
	doc = frappe.get_doc("Item", item_code)
	doc.set("qs_colours", rows)
	doc.save(ignore_permissions=True)
	return doc


def colour_rows(item_code):
	return frappe.get_all(
		"QS Item Colour",
		filters={"parent": item_code, "parentfield": "qs_colours"},
		fields=["label", "swatch"],
		order_by="idx asc",
	)


class TestColourValidator(CatalogTestCase):
	def setUp(self):
		super().setUp()
		make_published_item(ITEM, rate=10)

	def assertRejected(self, rows, message=None):
		with self.assertRaisesRegex(frappe.ValidationError, message or ""):
			save_colours(ITEM, rows)
		self.assertEqual(colour_rows(ITEM), [])

	def test_valid_colours_saved_in_order(self):
		save_colours(
			ITEM, [{"label": "Red", "swatch": "#FF0000"}, {"label": "Dark Blue", "swatch": "#00008B"}]
		)
		self.assertEqual(
			colour_rows(ITEM),
			[{"label": "Red", "swatch": "#FF0000"}, {"label": "Dark Blue", "swatch": "#00008B"}],
		)

	def test_no_colours_is_valid(self):
		save_colours(ITEM, [])
		self.assertEqual(colour_rows(ITEM), [])

	def test_at_most_12_colours(self):
		twelve = [{"label": f"C{i}", "swatch": "#101010"} for i in range(12)]
		save_colours(ITEM, twelve)
		self.assertEqual(len(colour_rows(ITEM)), 12)
		with self.assertRaisesRegex(frappe.ValidationError, "at most 12"):
			save_colours(ITEM, [*twelve, {"label": "C12", "swatch": "#101010"}])

	def test_labels_unique_case_insensitive(self):
		for labels in (("Red", "Red"), ("Red", "red"), ("Red", "RED"), ("Red", " red ")):
			with self.subTest(labels=labels):
				self.assertRejected(
					[{"label": label, "swatch": "#FF0000"} for label in labels], "more than once"
				)

	def test_distinct_labels_allowed(self):
		save_colours(ITEM, [{"label": "Red", "swatch": "#FF0000"}, {"label": "Red 2", "swatch": "#FF0001"}])
		self.assertEqual(len(colour_rows(ITEM)), 2)

	def test_label_required(self):
		for label in ("", "   ", None):
			with self.subTest(label=label):
				with self.assertRaises(frappe.ValidationError):
					save_colours(ITEM, [{"label": label, "swatch": "#FF0000"}])

	def test_label_trimmed(self):
		save_colours(ITEM, [{"label": "  Red  ", "swatch": "#FF0000"}])
		self.assertEqual(colour_rows(ITEM)[0].label, "Red")

	def test_swatch_must_be_hex_rrggbb(self):
		for swatch in (
			"red",
			"#FFF",
			"#GGGGGG",
			"FF0000",
			"#FF00000",
			"#FF000",
			"rgb(1,2,3)",
			" #FF0000",
			"",
		):
			with self.subTest(swatch=swatch):
				with self.assertRaises(frappe.ValidationError):
					save_colours(ITEM, [{"label": "Red", "swatch": swatch}])

	def test_swatch_normalised_to_upper_case(self):
		save_colours(ITEM, [{"label": "Mint", "swatch": "#aabbcc"}, {"label": "Mix", "swatch": "#aBc123"}])
		self.assertEqual([c.swatch for c in colour_rows(ITEM)], ["#AABBCC", "#ABC123"])

	def test_photo_colour_must_match_a_label_exactly(self):
		make_colours(ITEM, "Red", "Blue")
		photo = make_photo(ITEM, 10, 10, stem="_qs_col_photo")
		for tag in ("red", "Green", "Red "):
			with self.subTest(tag=tag):
				doc = frappe.get_doc("Item", ITEM)
				doc.qs_photos[0].colour = tag
				with self.assertRaisesRegex(frappe.ValidationError, "not one of this item's colours"):
					doc.save(ignore_permissions=True)
		doc = frappe.get_doc("Item", ITEM)
		doc.qs_photos[0].colour = "Blue"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("QS Item Photo", photo.row, "colour"), "Blue")

	def test_photo_colour_empty_is_a_general_photo(self):
		make_colours(ITEM, "Red")
		make_photo(ITEM, 10, 10, stem="_qs_col_general")
		doc = frappe.get_doc("Item", ITEM)
		doc.save(ignore_permissions=True)
		self.assertFalse(frappe.get_doc("Item", ITEM).qs_photos[0].colour)

	def test_photo_colour_rejected_when_item_has_no_colours(self):
		make_photo(ITEM, 10, 10, stem="_qs_col_none")
		doc = frappe.get_doc("Item", ITEM)
		doc.qs_photos[0].colour = "Red"
		with self.assertRaisesRegex(frappe.ValidationError, "no colours"):
			doc.save(ignore_permissions=True)

	def test_removing_a_colour_that_a_photo_uses_is_rejected(self):
		make_colours(ITEM, "Red", "Blue")
		make_photo(ITEM, 10, 10, stem="_qs_col_used", colour="Blue")
		with self.assertRaisesRegex(frappe.ValidationError, "not one of this item's colours"):
			save_colours(ITEM, [{"label": "Red", "swatch": "#FF0000"}])


class TestCatalogColours(CatalogTestCase):
	def setUp(self):
		super().setUp()
		make_published_item(ITEM, rate=10)
		make_published_item("_QS-COL-PLAIN", rate=5)

	def test_get_product_colours_and_photo_colour(self):
		make_colours(ITEM, ("Red", "#ff0000"), ("Blue", "#0000FF"))
		make_photo(ITEM, 10, 10, stem="_qs_cat_gen", alt_text="General", thumb="/files/g-400.webp")
		make_photo(
			ITEM, 10, 10, stem="_qs_cat_red", alt_text="Red one", colour="Red", thumb="/files/r-400.webp"
		)
		product = get_product(route_of("Item", ITEM))
		self.assertEqual(
			product["colours"],
			[{"label": "Red", "swatch": "#FF0000"}, {"label": "Blue", "swatch": "#0000FF"}],
		)
		self.assertEqual(
			[(p["alt"], p["colour"]) for p in product["photos"]], [("General", ""), ("Red one", "Red")]
		)
		self.assertTrue(product["has_colours"])

	def test_get_product_without_colours(self):
		make_photo("_QS-COL-PLAIN", 10, 10, stem="_qs_cat_plain")
		product = get_product(route_of("Item", "_QS-COL-PLAIN"))
		self.assertEqual(product["colours"], [])
		self.assertEqual(product["photos"][0]["colour"], "")
		self.assertFalse(product["has_colours"])

	def test_cards_has_colours(self):
		make_colours(ITEM, "Red")
		cards = {c["item_code"]: c for c in list_products()["items"]}
		self.assertIs(cards[ITEM]["has_colours"], True)
		self.assertIs(cards["_QS-COL-PLAIN"]["has_colours"], False)

	def test_cards_not_duplicated_by_many_colours(self):
		make_colours(ITEM, "Red", "Green", "Blue")
		result = list_products()
		self.assertEqual((result["total"], len(result["items"])), (2, 2))

	def test_card_cache_follows_item_save(self):
		cards = {c["item_code"]: c for c in list_products()["items"]}
		self.assertIs(cards[ITEM]["has_colours"], False)
		make_colours(ITEM, "Red")  # Item on_update clears the catalog cache
		cards = {c["item_code"]: c for c in list_products()["items"]}
		self.assertIs(cards[ITEM]["has_colours"], True)
		self.assertEqual(len(get_product(route_of("Item", ITEM))["colours"]), 1)

	def card(self, code=ITEM):
		return {c["item_code"]: c for c in list_products()["items"]}[code]

	def test_listing_card_colours_shape_and_order(self):
		"""§11 listing cards: colours [{label, swatch, image | None}], in order, only for items with colours."""
		make_colours(ITEM, ("Red", "#ff0000"), ("Blue", "#0000ff"))
		sizes = {"thumb": "/files/b-400.webp", "medium": "/files/b-1000.webp", "large": "/files/b-1800.webp"}
		make_photo(ITEM, 10, 10, stem="_qs_lc_general", thumb="/files/gen-400.webp")
		make_photo(ITEM, 10, 10, stem="_qs_lc_blue", alt_text="Blue view", colour="Blue", **sizes)
		card = self.card()
		self.assertTrue(card["has_colours"])
		self.assertEqual(
			card["colours"],
			[
				{
					"label": "Red",
					"swatch": "#FF0000",
					"image": None,
				},  # no tagged photo: keep the general image
				{"label": "Blue", "swatch": "#0000FF", "image": {**sizes, "alt": "Blue view"}},
			],
		)
		self.assertEqual(card["image"]["thumb"], "/files/gen-400.webp")  # the card's own image is unchanged
		plain = self.card("_QS-COL-PLAIN")
		self.assertFalse(plain["has_colours"])
		self.assertNotIn("colours", plain)

	def test_listing_colour_image_is_the_first_tagged_photo(self):
		make_colours(ITEM, "Red")
		make_photo(ITEM, 10, 10, stem="_qs_lc_r1", colour="Red", thumb="/files/r1-400.webp")
		make_photo(ITEM, 10, 10, stem="_qs_lc_r2", colour="Red", thumb="/files/r2-400.webp")
		self.assertEqual(self.card()["colours"][0]["image"]["thumb"], "/files/r1-400.webp")

	def test_listing_colours_capped_at_12(self):
		make_colours(ITEM, "C0")
		for n in range(1, 14):  # the validator stops at 12 on save: insert the rows directly
			frappe.get_doc(
				{
					"doctype": "QS Item Colour",
					"parent": ITEM,
					"parenttype": "Item",
					"parentfield": "qs_colours",
					"idx": n + 1,
					"label": f"C{n}",
					"swatch": "#101010",
				}
			).insert(ignore_permissions=True)
		frappe.cache.delete_keys("qs:catalog:")
		self.assertEqual([c["label"] for c in self.card()["colours"]], [f"C{n}" for n in range(12)])

	def test_colours_follow_item_save(self):
		make_colours(ITEM, "Red")
		self.assertEqual([c["label"] for c in self.card()["colours"]], ["Red"])
		make_colours(ITEM, "Green", "Red")
		self.assertEqual([c["label"] for c in self.card()["colours"]], ["Green", "Red"])
		make_colours(ITEM)
		card = self.card()
		self.assertFalse(card["has_colours"])
		self.assertNotIn("colours", card)

	def test_search_cards_carry_colours(self):
		make_colours(ITEM, "Red")
		(card,) = [c for c in list_products(q=ITEM)["items"] if c["item_code"] == ITEM]
		self.assertEqual([c["label"] for c in card["colours"]], ["Red"])

	def test_related_and_quote_item_cards_carry_only_has_colours(self):
		make_colours(ITEM, "Red")
		main = frappe.get_doc("Item", "_QS-COL-PLAIN")
		main.append("qs_related", {"item": ITEM})
		main.save(ignore_permissions=True)
		(related,) = get_product(route_of("Item", "_QS-COL-PLAIN"))["related"]
		self.assertIs(related["has_colours"], True)
		self.assertNotIn("colours", related)
		(card,) = call_api("quoteshop.quoteshop_enquiry.api.get_quote_items", item_codes=[ITEM])
		self.assertIs(card["has_colours"], True)
		self.assertNotIn("colours", card)

	def test_listing_query_budget_with_many_colour_items(self):
		codes = [ITEM] + [make_published_item(f"_QS-COL-L{i}", rate=1) for i in range(23)]
		for code in codes:
			make_colours(code, "Red", "Blue", "Green")
		list_products()  # framework warm-up outside the budget
		frappe.cache.delete_keys("qs:catalog:")
		with self.assertQueryCount(LIST_COLD):
			cold = list_products()
		self.assertEqual(sum(1 for c in cold["items"] if len(c.get("colours", [])) == 3), 24)
		with self.assertQueryCount(WARM):
			self.assertEqual(list_products(), cold)

	def test_query_budgets_with_colours(self):
		make_colours(ITEM, *[f"C{i}" for i in range(12)])
		make_photo(ITEM, 10, 10, stem="_qs_cat_budget", colour="C3")
		route = route_of("Item", ITEM)
		list_products()  # framework warm-up outside the budget
		get_product(route)
		frappe.cache.delete_keys("qs:catalog:")
		with self.assertQueryCount(LIST_COLD):
			cold = list_products()
		with self.assertQueryCount(WARM):
			self.assertEqual(list_products(), cold)
		with self.assertQueryCount(PRODUCT_COLD):
			cold = get_product(route)
		with self.assertQueryCount(WARM):
			self.assertEqual(get_product(route), cold)
		self.assertEqual(len(cold["colours"]), 12)


GET_COLOURS = "quoteshop.quoteshop_catalog.catalog.get_colours"


class TestGetColours(CatalogTestCase):
	"""CONTRACTS §11: catalog.get_colours(item_codes) -> {item_code: [{label, swatch}]}, published items only, one query."""

	def setUp(self):
		super().setUp()
		make_published_item(ITEM, rate=1)
		make_colours(ITEM, ("Red", "#ff0000"), ("Blue", "#0000FF"))
		make_published_item("_QS-COL-PLAIN", rate=1)
		make_published_item("_QS-COL-HIDDEN", published=0)
		make_colours("_QS-COL-HIDDEN", "Red")
		make_published_item("_QS-COL-OFF", disabled=1)
		make_colours("_QS-COL-OFF", "Red")

	def test_colours_in_order_for_published_items_only(self):
		result = call_api(
			GET_COLOURS,
			item_codes=[ITEM, "_QS-COL-PLAIN", "_QS-COL-HIDDEN", "_QS-COL-OFF", "_QS-no-such-item"],
		)
		self.assertEqual(
			result, {ITEM: [{"label": "Red", "swatch": "#FF0000"}, {"label": "Blue", "swatch": "#0000FF"}]}
		)

	def test_template_item_excluded(self):
		frappe.db.set_value("Item", ITEM, "has_variants", 1)  # a template needs attributes to save
		self.assertEqual(call_api(GET_COLOURS, item_codes=[ITEM]), {})

	def test_json_string_get_and_post(self):
		for method in ("GET", "POST"):
			with self.subTest(method=method):
				result = call_api(GET_COLOURS, http_method=method, item_codes=frappe.as_json([ITEM]))
				self.assertEqual(list(result), [ITEM])

	def test_empty_and_duplicate_codes(self):
		self.assertEqual(call_api(GET_COLOURS, item_codes=[]), {})
		self.assertEqual(len(call_api(GET_COLOURS, item_codes=[ITEM, ITEM])[ITEM]), 2)

	def test_every_role(self):
		from quoteshop.quoteshop_enquiry.tests.factories import make_user, make_website_user

		for user in (
			"Guest",
			make_website_user("_qs_buyer_col@example.com"),
			make_user("_qs_sales_user_col@example.com", ("Sales User",)),
			make_user("_qs_sales_manager_col@example.com", ("Sales Manager",)),
		):
			with self.subTest(user=user):
				self.assertEqual(list(call_api(GET_COLOURS, user=user, item_codes=[ITEM])), [ITEM])

	def test_invalid_input_rejected(self):
		for value in (frappe.as_json({"a": 1}), frappe.as_json([1]), frappe.as_json([[ITEM]]), "5"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				call_api(GET_COLOURS, item_codes=value)

	def test_non_string_entries_rejected_by_the_type_check(self):
		with self.assertRaises(frappe.FrappeTypeError):
			call_api(GET_COLOURS, item_codes=[None])

	def test_max_500_codes(self):
		self.assertEqual(len(call_api(GET_COLOURS, item_codes=[ITEM] * 500)), 1)
		with self.assertRaises(frappe.ValidationError):
			call_api(GET_COLOURS, item_codes=[ITEM] * 501)

	def test_sql_metacharacters_inert(self):
		self.assertEqual(call_api(GET_COLOURS, item_codes=["' or 1=1 --", "%", "_"]), {})

	def test_one_query_for_many_items(self):
		from quoteshop.quoteshop_catalog.catalog import get_colours

		codes = [ITEM] + [make_published_item(f"_QS-COL-M{i}") for i in range(20)]
		get_colours(codes)  # warm-up
		with self.assertQueryCount(1):
			get_colours(codes)

	def test_rate_limited_per_ip(self):
		clear_qs_redis()  # rate-limit counters live in redis for an hour and are not rolled back
		self.addCleanup(clear_qs_redis)
		for _ in range(600):
			call_api(GET_COLOURS, item_codes=[], ip="10.5.1.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			call_api(GET_COLOURS, item_codes=[], ip="10.5.1.1")
