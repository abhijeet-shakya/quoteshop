"""CONTRACTS §6.2 - diff_lines(previous, current) -> {line_key: change_flag}, line_key = item_code + US + colour (CONTRACTS §11). Pure, no DB."""

import frappe
from frappe.tests import UnitTestCase

from quoteshop.quoteshop_enquiry.diff import diff_lines, line_key


def k(item_code, colour=""):
	return f"{item_code}\x1f{colour}"


def row(item_code, qty=2.0, rate=100.0, availability="Available", alternative_item=None, colour=None):
	return {
		"item_code": item_code,
		"colour": colour,
		"offered_qty": qty,
		"offered_rate": rate,
		"availability": availability,
		"alternative_item": alternative_item,
	}


class GetOnlyRow:
	"""Child-table-like row: readable only through .get (no item access)."""

	def __init__(self, **values):
		self._values = values

	def get(self, key, default=None):
		return self._values.get(key, default)


class TestDiffLines(UnitTestCase):
	def test_added(self):
		self.assertEqual(diff_lines([row("A")], [row("A"), row("B")]), {k("A"): "", k("B"): "Added"})

	def test_removed(self):
		self.assertEqual(diff_lines([row("A"), row("B")], [row("A")]), {k("A"): "", k("B"): "Removed"})

	def test_qty_changed(self):
		self.assertEqual(diff_lines([row("A", qty=2)], [row("A", qty=3)]), {k("A"): "Qty changed"})

	def test_price_changed(self):
		self.assertEqual(diff_lines([row("A", rate=100)], [row("A", rate=95.5)]), {k("A"): "Price changed"})

	def test_price_changed_takes_precedence_over_qty_changed(self):
		self.assertEqual(
			diff_lines([row("A", qty=2, rate=100)], [row("A", qty=5, rate=90)]), {k("A"): "Price changed"}
		)

	def test_alternative(self):
		self.assertEqual(
			diff_lines([row("A")], [row("A", availability="Alternative", alternative_item="Z")]),
			{k("A"): "Alternative"},
		)

	def test_alternative_takes_precedence_over_price_and_qty_changed(self):
		self.assertEqual(
			diff_lines(
				[row("A", qty=2, rate=100)],
				[row("A", qty=4, rate=80, availability="Alternative", alternative_item="Z")],
			),
			{k("A"): "Alternative"},
		)

	def test_already_alternative_then_price_change_is_price_changed(self):
		# "became Alternative" - an unchanged Alternative availability is not a new Alternative.
		prev = [row("A", rate=100, availability="Alternative", alternative_item="Z")]
		curr = [row("A", rate=90, availability="Alternative", alternative_item="Z")]
		self.assertEqual(diff_lines(prev, curr), {k("A"): "Price changed"})

	def test_alternative_item_changed_is_alternative(self):
		prev = [row("A", rate=100, availability="Alternative", alternative_item="Z")]
		self.assertEqual(
			diff_lines(prev, [row("A", rate=100, availability="Alternative", alternative_item="Y")]),
			{k("A"): "Alternative"},
		)
		self.assertEqual(
			diff_lines(prev, [row("A", rate=90, availability="Alternative", alternative_item="Y")]),
			{k("A"): "Alternative"},
		)

	def test_alternative_item_none_equals_empty(self):
		none_alt = [row("A", availability="Alternative", alternative_item=None)]
		empty_alt = [row("A", availability="Alternative", alternative_item="")]
		self.assertEqual(diff_lines(none_alt, empty_alt), {k("A"): ""})
		self.assertEqual(diff_lines(empty_alt, none_alt), {k("A"): ""})

	def test_rows_may_be_child_table_like(self):
		prev = [frappe._dict(row("A")), frappe._dict(row("B", qty=1))]
		curr = [GetOnlyRow(**row("A", rate=90)), GetOnlyRow(**row("C"))]
		self.assertEqual(
			diff_lines(prev, curr), {k("A"): "Price changed", k("B"): "Removed", k("C"): "Added"}
		)

	def test_default_precisions(self):
		# defaults rate_precision=2, qty_precision=3: both pairs round to the same value
		self.assertEqual(diff_lines([row("A", rate=10.004)], [row("A", rate=10.001)]), {k("A"): ""})
		self.assertEqual(diff_lines([row("A", qty=2.0004)], [row("A", qty=2.0001)]), {k("A"): ""})

	def test_rate_precision_kwarg(self):
		prev, curr = [row("A", rate=10.004)], [row("A", rate=10.001)]
		self.assertEqual(diff_lines(prev, curr, rate_precision=2), {k("A"): ""})
		self.assertEqual(diff_lines(prev, curr, rate_precision=3), {k("A"): "Price changed"})

	def test_qty_precision_kwarg(self):
		prev, curr = [row("A", qty=2.0004)], [row("A", qty=2.0001)]
		self.assertEqual(diff_lines(prev, curr, qty_precision=3), {k("A"): ""})
		self.assertEqual(diff_lines(prev, curr, qty_precision=4), {k("A"): "Qty changed"})

	def test_precisions_are_keyword_only(self):
		with self.assertRaises(TypeError):
			diff_lines([row("A")], [row("A")], 3)

	def test_unchanged_empty_flag(self):
		self.assertEqual(diff_lines([row("A"), row("B")], [row("A"), row("B")]), {k("A"): "", k("B"): ""})

	def test_float_noise_is_not_a_change(self):
		prev = [row("A", qty=0.3, rate=0.3), row("B", qty=2, rate=10.1)]
		curr = [row("A", qty=0.1 + 0.2, rate=0.1 + 0.2), row("B", qty=2.0000000001, rate=10.1000000001)]
		self.assertEqual(diff_lines(prev, curr), {k("A"): "", k("B"): ""})

	def test_order_independent(self):
		prev = [row("A"), row("B", qty=1), row("C", rate=50)]
		curr = [row("D"), row("C", rate=40), row("B", qty=7)]
		expected = {k("A"): "Removed", k("B"): "Qty changed", k("C"): "Price changed", k("D"): "Added"}
		self.assertEqual(diff_lines(prev, curr), expected)
		self.assertEqual(diff_lines(list(reversed(prev)), list(reversed(curr))), expected)

	def test_both_empty(self):
		self.assertEqual(diff_lines([], []), {})

	def test_inputs_not_mutated(self):
		prev, curr = [row("A")], [row("A", qty=9)]
		snapshot = (repr(prev), repr(curr))
		diff_lines(prev, curr)
		self.assertEqual((repr(prev), repr(curr)), snapshot)


class TestLineKey(UnitTestCase):
	def test_key_is_item_code_unit_separator_colour(self):
		self.assertEqual(line_key(row("A", colour="Red")), "A\x1fRed")
		self.assertEqual(line_key(row("A")), "A\x1f")

	def test_dict_and_doc_rows(self):
		for r in (frappe._dict(row("A", colour="Red")), GetOnlyRow(**row("A", colour="Red"))):
			self.assertEqual(line_key(r), "A\x1fRed")

	def test_none_colour_equals_empty(self):
		self.assertEqual(line_key({"item_code": "A"}), line_key({"item_code": "A", "colour": ""}))
		self.assertEqual(line_key({"item_code": "A", "colour": None}), "A\x1f")
		self.assertEqual(diff_lines([row("A", colour=None)], [row("A", colour="")]), {k("A"): ""})
		self.assertEqual(
			diff_lines(
				[row("A", colour="")],
				[{"item_code": "A", "offered_qty": 2.0, "offered_rate": 100.0, "availability": "Available"}],
			),
			{k("A"): ""},
		)


class TestDiffColours(UnitTestCase):
	def test_colour_switch_is_removed_plus_added(self):
		self.assertEqual(
			diff_lines([row("A", colour="Red")], [row("A", colour="Blue")]),
			{k("A", "Red"): "Removed", k("A", "Blue"): "Added"},
		)

	def test_no_colour_to_colour_is_removed_plus_added(self):
		self.assertEqual(
			diff_lines([row("A")], [row("A", colour="Red")]), {k("A"): "Removed", k("A", "Red"): "Added"}
		)

	def test_same_item_two_colours_are_two_keys(self):
		current = [row("A", colour="Red"), row("A", colour="Blue", qty=5)]
		self.assertEqual(
			diff_lines([row("A", colour="Red"), row("A", colour="Blue")], current),
			{k("A", "Red"): "", k("A", "Blue"): "Qty changed"},
		)

	def test_adding_a_second_colour(self):
		self.assertEqual(
			diff_lines([row("A", colour="Red")], [row("A", colour="Red"), row("A", colour="Blue")]),
			{k("A", "Red"): "", k("A", "Blue"): "Added"},
		)

	def test_dropping_one_of_two_colours(self):
		self.assertEqual(
			diff_lines([row("A", colour="Red"), row("A", colour="Blue")], [row("A", colour="Red")]),
			{k("A", "Red"): "", k("A", "Blue"): "Removed"},
		)

	def test_colour_compared_exactly(self):
		self.assertEqual(
			diff_lines([row("A", colour="Red")], [row("A", colour="red")]),
			{k("A", "Red"): "Removed", k("A", "red"): "Added"},
		)
