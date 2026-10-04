"""Phase 3 quote-list APIs (CONTRACTS §7.2; TEST_MATRIX QTE-03..05, NFR-14 part): get_quote_items, parse_quote_paste.

Guest APIs, also callable by a buyer, Sales User and Sales Manager. Only published, enabled, non-template items.
"""

import time

import frappe

from quoteshop.quoteshop_enquiry.api import parse_quote_paste
from quoteshop.quoteshop_enquiry.tests.factories import (
	EnquiryTestCase,
	call_api,
	make_published_item,
	make_user,
	make_website_user,
)

GET_ITEMS = "quoteshop.quoteshop_enquiry.api.get_quote_items"
PASTE = "quoteshop.quoteshop_enquiry.api.parse_quote_paste"
A, B, C = "_QS Q-A", "_QS Q-B", "_QS Q-C"
HIDDEN, DISABLED, TEMPLATE = "_QS Q-Unpublished", "_QS Q-Disabled", "_QS Q-Template"


class QuoteAPITestCase(EnquiryTestCase):
	def setUp(self):
		super().setUp()
		make_published_item(A, rate=150, item_name="_QS Cue Stick Pro")
		make_published_item(B, rate=99.5)
		make_published_item(C, qs_min_qty=10)  # no price → Price on request
		make_published_item(HIDDEN, rate=10, published=0)
		make_published_item(DISABLED, rate=10, disabled=1)
		make_published_item(TEMPLATE)
		frappe.db.set_value("Item", TEMPLATE, "has_variants", 1)  # a template needs attributes to save

	def users(self):
		return (
			"Guest",
			make_website_user("_qs_buyer_q@example.com"),
			make_user("_qs_sales_user_q@example.com", ("Sales User",)),
			make_user("_qs_sales_manager_q@example.com", ("Sales Manager",)),
		)


class TestGetQuoteItems(QuoteAPITestCase):
	def test_cards_for_every_role(self):
		for user in self.users():
			with self.subTest(user=user):
				cards = call_api(GET_ITEMS, user=user, item_codes=[A, B])
				self.assertEqual([c["item_code"] for c in cards], [A, B])

	def test_card_shape_and_prices(self):
		cards = {c["item_code"]: c for c in call_api(GET_ITEMS, item_codes=[A, B, C])}
		self.assertTrue(
			{
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
			}
			<= set(cards[A])
		)
		self.assertEqual(cards[A]["item_name"], "_QS Cue Stick Pro")
		self.assertEqual(cards[A]["starting_price"], 150.0)
		self.assertEqual(cards[B]["starting_price"], 99.5)
		self.assertIsNone(cards[C]["starting_price"])
		self.assertEqual(cards[C]["min_qty"], 10)

	def test_json_string_input_and_given_order_deduped(self):
		cards = call_api(GET_ITEMS, item_codes=frappe.as_json([B, A, B]))
		self.assertEqual([c["item_code"] for c in cards], [B, A])

	def test_get_allowed(self):
		self.assertEqual(len(call_api(GET_ITEMS, http_method="GET", item_codes=frappe.as_json([A]))), 1)

	def test_unpublished_disabled_template_unknown_dropped(self):
		"""Tampered input: only published, enabled, non-template items come back."""
		cards = call_api(GET_ITEMS, item_codes=[HIDDEN, A, DISABLED, TEMPLATE, "_QS no such item"])
		self.assertEqual([c["item_code"] for c in cards], [A])

	def test_unpublish_takes_effect(self):
		frappe.db.set_value("Item", A, "qs_published", 0)
		self.assertEqual(call_api(GET_ITEMS, item_codes=[A]), [])

	def test_empty_list(self):
		self.assertEqual(call_api(GET_ITEMS, item_codes=[]), [])

	def test_invalid_input_rejected(self):
		for value in (frappe.as_json({"a": 1}), frappe.as_json([1, 2]), frappe.as_json([[A]]), "123"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				call_api(GET_ITEMS, item_codes=value)

	def test_malformed_json_is_a_validation_error(self):
		"""Malformed JSON must be a clean 4xx ValidationError, not an unhandled decode error (HTTP 500)."""
		with self.assertRaises(frappe.ValidationError):
			call_api(GET_ITEMS, item_codes="[not json")

	def test_max_500_codes(self):
		self.assertEqual(call_api(GET_ITEMS, item_codes=[A] * 500)[0]["item_code"], A)
		with self.assertRaises(frappe.ValidationError):
			call_api(GET_ITEMS, item_codes=[A] * 501)

	def test_sql_metacharacters_inert(self):
		self.assertEqual(call_api(GET_ITEMS, item_codes=["' or 1=1 --", "%", "_"]), [])

	def test_rate_limited_per_ip(self):
		for _ in range(600):
			call_api(GET_ITEMS, item_codes=[], ip="10.5.0.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			call_api(GET_ITEMS, item_codes=[], ip="10.5.0.1")


class TestParseQuotePaste(QuoteAPITestCase):
	def paste(self, text, **kwargs):
		return call_api(PASTE, text=text, **kwargs)

	def test_matches_codes_and_qty(self):
		"""QTE-04: tab, comma, semicolon and space separators; exact item name also matches."""
		result = self.paste(f"{A}\t5\n{B}, 3\n_QS Cue Stick Pro;2\n{C} 12")
		self.assertEqual(
			result["matched"],
			[
				{"item_code": A, "item_name": "_QS Cue Stick Pro", "qty": 7.0},
				{"item_code": B, "item_name": B, "qty": 3.0},
				{"item_code": C, "item_name": C, "qty": 12.0},
			],
		)
		self.assertEqual(result["unmatched"], [])

	def test_every_role(self):
		for user in self.users():
			with self.subTest(user=user):
				self.assertEqual(len(self.paste(f"{A},1", user=user)["matched"]), 1)

	def test_case_insensitive_and_quoted(self):
		result = self.paste(f'"{A.lower()}",4\n\'_qs cue stick pro\'\t1')
		self.assertEqual(result["matched"], [{"item_code": A, "item_name": "_QS Cue Stick Pro", "qty": 5.0}])

	def test_reports_unmatched_rows(self):
		"""QTE-05: unknown/unpublished items and rows without a positive quantity are reported, not dropped."""
		lines = [f"{HIDDEN},2", f"{DISABLED},2", f"{TEMPLATE},2", "_QS nothing,2", f"{A}", f"{A},0", f"{A},-3", f"{A},abc"]
		result = self.paste("\n".join(lines))
		self.assertEqual(result["matched"], [])
		self.assertCountEqual([row["line"] for row in result["unmatched"]], lines)  # order not specified
		self.assertTrue(all(row["reason"] for row in result["unmatched"]))

	def test_blank_lines_ignored(self):
		result = self.paste(f"\n\n{A},1\n   \n")
		self.assertEqual((len(result["matched"]), result["unmatched"]), (1, []))

	def test_min_qty_applied(self):
		self.assertEqual(self.paste(f"{C},2")["matched"][0]["qty"], 10.0)

	def test_max_500_lines(self):
		self.assertEqual(len(self.paste("\n".join([f"{A},1"] * 500))["matched"]), 1)
		with self.assertRaises(frappe.ValidationError):
			self.paste("\n".join([f"{A},1"] * 501))

	def test_post_only(self):
		with self.assertRaises(frappe.PermissionError):
			self.paste(f"{A},1", http_method="GET")

	def test_rate_limited_per_ip(self):
		for _ in range(120):
			self.paste("", ip="10.6.0.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.paste("", ip="10.6.0.1")


class TestPasteLimits(QuoteAPITestCase):
	"""CONTRACTS §10 phase-3 limits: 50 KB, 200-char lines, last-separator split, 0 < qty ≤ 100000."""

	def test_text_over_50_kb_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			call_api(PASTE, text=f"{A},1\n" + "x" * (50 * 1024))
		self.assertEqual(len(call_api(PASTE, text=f"{A},1\n" + " " * 40000)["matched"]), 1)

	def test_line_over_200_chars_unmatched(self):
		long_line = f"{A}" + " " * 200 + "1"
		result = call_api(PASTE, text=f"{long_line}\n{B},2")
		self.assertEqual([m["item_code"] for m in result["matched"]], [B])
		(row,) = result["unmatched"]
		self.assertLessEqual(len(row["line"]), 201)
		self.assertTrue(row["reason"])

	def test_split_at_last_separator(self):
		"""Names with spaces/commas: everything before the last separator run is the name."""
		result = call_api(PASTE, text="_QS Cue Stick Pro 3\n_QS Cue Stick Pro ,; \t 2")
		self.assertEqual(result["matched"], [{"item_code": A, "item_name": "_QS Cue Stick Pro", "qty": 5.0}])

	def test_qty_must_be_finite_positive_and_capped(self):
		bad = [f"{A},{q}" for q in ("inf", "-inf", "nan", "NaN", "1e309", "100001", "0", "-1", "1e5x")]
		result = call_api(PASTE, text="\n".join(bad))
		self.assertEqual(result["matched"], [])
		self.assertCountEqual([r["line"] for r in result["unmatched"]], bad)
		self.assertEqual(call_api(PASTE, text=f"{A},100000")["matched"][0]["qty"], 100000.0)

	def test_redos_pathological_line_is_fast(self):
		"""Regression: the old "name<sep>qty" regex backtracked quadratically on long separator runs."""
		parse_quote_paste("warm,up\n" + "y" * 300)  # load translations etc. outside the timed calls
		for line in ("a" + "\t" * 1598 + "x", "a" + " ,;\t" * 399 + "x", "a" + " " * 197 + "x"):
			with self.subTest(length=len(line)):
				start = time.perf_counter()
				result = parse_quote_paste(line)
				self.assertLess(time.perf_counter() - start, 0.05)
				self.assertEqual(result["matched"], [])
		start = time.perf_counter()
		parse_quote_paste("\n".join(["a" + " " * 190 + "x"] * 250))  # ~48 KB of worst-case lines
		self.assertLess(time.perf_counter() - start, 1.0)
