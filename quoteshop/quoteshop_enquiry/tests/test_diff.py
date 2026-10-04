"""CONTRACTS §6.2 - diff_lines(previous, current) -> {item_code: change_flag}. Pure, no DB."""

import frappe
from frappe.tests import UnitTestCase

from quoteshop.quoteshop_enquiry.diff import diff_lines


def row(item_code, qty=2.0, rate=100.0, availability="Available", alternative_item=None):
	return {
		"item_code": item_code,
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
		self.assertEqual(diff_lines([row("A")], [row("A"), row("B")]), {"A": "", "B": "Added"})

	def test_removed(self):
		self.assertEqual(diff_lines([row("A"), row("B")], [row("A")]), {"A": "", "B": "Removed"})

	def test_qty_changed(self):
		self.assertEqual(diff_lines([row("A", qty=2)], [row("A", qty=3)]), {"A": "Qty changed"})

	def test_price_changed(self):
		self.assertEqual(diff_lines([row("A", rate=100)], [row("A", rate=95.5)]), {"A": "Price changed"})

	def test_price_changed_takes_precedence_over_qty_changed(self):
		self.assertEqual(
			diff_lines([row("A", qty=2, rate=100)], [row("A", qty=5, rate=90)]), {"A": "Price changed"}
		)

	def test_alternative(self):
		self.assertEqual(
			diff_lines([row("A")], [row("A", availability="Alternative", alternative_item="Z")]),
			{"A": "Alternative"},
		)

	def test_alternative_takes_precedence_over_price_and_qty_changed(self):
		self.assertEqual(
			diff_lines(
				[row("A", qty=2, rate=100)],
				[row("A", qty=4, rate=80, availability="Alternative", alternative_item="Z")],
			),
			{"A": "Alternative"},
		)

	def test_already_alternative_then_price_change_is_price_changed(self):
		# "became Alternative" - an unchanged Alternative availability is not a new Alternative.
		prev = [row("A", rate=100, availability="Alternative", alternative_item="Z")]
		curr = [row("A", rate=90, availability="Alternative", alternative_item="Z")]
		self.assertEqual(diff_lines(prev, curr), {"A": "Price changed"})

	def test_alternative_item_changed_is_alternative(self):
		prev = [row("A", rate=100, availability="Alternative", alternative_item="Z")]
		self.assertEqual(
			diff_lines(prev, [row("A", rate=100, availability="Alternative", alternative_item="Y")]),
			{"A": "Alternative"},
		)
		self.assertEqual(
			diff_lines(prev, [row("A", rate=90, availability="Alternative", alternative_item="Y")]),
			{"A": "Alternative"},
		)

	def test_alternative_item_none_equals_empty(self):
		none_alt = [row("A", availability="Alternative", alternative_item=None)]
		empty_alt = [row("A", availability="Alternative", alternative_item="")]
		self.assertEqual(diff_lines(none_alt, empty_alt), {"A": ""})
		self.assertEqual(diff_lines(empty_alt, none_alt), {"A": ""})

	def test_rows_may_be_child_table_like(self):
		prev = [frappe._dict(row("A")), frappe._dict(row("B", qty=1))]
		curr = [GetOnlyRow(**row("A", rate=90)), GetOnlyRow(**row("C"))]
		self.assertEqual(diff_lines(prev, curr), {"A": "Price changed", "B": "Removed", "C": "Added"})

	def test_default_precisions(self):
		# defaults rate_precision=2, qty_precision=3: both pairs round to the same value
		self.assertEqual(diff_lines([row("A", rate=10.004)], [row("A", rate=10.001)]), {"A": ""})
		self.assertEqual(diff_lines([row("A", qty=2.0004)], [row("A", qty=2.0001)]), {"A": ""})

	def test_rate_precision_kwarg(self):
		prev, curr = [row("A", rate=10.004)], [row("A", rate=10.001)]
		self.assertEqual(diff_lines(prev, curr, rate_precision=2), {"A": ""})
		self.assertEqual(diff_lines(prev, curr, rate_precision=3), {"A": "Price changed"})

	def test_qty_precision_kwarg(self):
		prev, curr = [row("A", qty=2.0004)], [row("A", qty=2.0001)]
		self.assertEqual(diff_lines(prev, curr, qty_precision=3), {"A": ""})
		self.assertEqual(diff_lines(prev, curr, qty_precision=4), {"A": "Qty changed"})

	def test_precisions_are_keyword_only(self):
		with self.assertRaises(TypeError):
			diff_lines([row("A")], [row("A")], 3)

	def test_unchanged_empty_flag(self):
		self.assertEqual(diff_lines([row("A"), row("B")], [row("A"), row("B")]), {"A": "", "B": ""})

	def test_float_noise_is_not_a_change(self):
		prev = [row("A", qty=0.3, rate=0.3), row("B", qty=2, rate=10.1)]
		curr = [row("A", qty=0.1 + 0.2, rate=0.1 + 0.2), row("B", qty=2.0000000001, rate=10.1000000001)]
		self.assertEqual(diff_lines(prev, curr), {"A": "", "B": ""})

	def test_order_independent(self):
		prev = [row("A"), row("B", qty=1), row("C", rate=50)]
		curr = [row("D"), row("C", rate=40), row("B", qty=7)]
		expected = {"A": "Removed", "B": "Qty changed", "C": "Price changed", "D": "Added"}
		self.assertEqual(diff_lines(prev, curr), expected)
		self.assertEqual(diff_lines(list(reversed(prev)), list(reversed(curr))), expected)

	def test_both_empty(self):
		self.assertEqual(diff_lines([], []), {})

	def test_inputs_not_mutated(self):
		prev, curr = [row("A")], [row("A", qty=9)]
		snapshot = (repr(prev), repr(curr))
		diff_lines(prev, curr)
		self.assertEqual((repr(prev), repr(curr)), snapshot)
