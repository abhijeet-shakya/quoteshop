"""REP-01 Listed vs Sold by Item reconciles with the submitted QuoteShop Sales Orders (known dataset)."""

import frappe
from frappe.desk.query_report import run
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from quoteshop.quoteshop_enquiry.report.listed_vs_sold_by_item.listed_vs_sold_by_item import execute
from quoteshop.quoteshop_enquiry.tests.factories import make_report_dataset, report_filters

REPORT = "Listed vs Sold by Item"


class TestListedVsSoldByItem(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = make_report_dataset()

	def rows(self, **extra):
		_columns, data, _msg, _chart, summary = execute(report_filters(self.data, **extra))
		return {r.item_code: r for r in data}, {s["label"]: s["value"] for s in summary}

	def test_totals_reconcile(self):
		rows, summary = self.rows()
		self.assertEqual(sorted(rows), ["_QS-REP-A", "_QS-REP-B"])
		got = {
			c: (
				r.qty,
				flt(r.listed_value, 2),
				flt(r.sold_value, 2),
				flt(r.discount_amount, 2),
				flt(r.discount_pct, 2),
			)
			for c, r in rows.items()
		}
		self.assertEqual(got, {"_QS-REP-A": (5, 1250, 1100, 150, 12), "_QS-REP-B": (2, 200, 180, 20, 10)})

		# against the source records
		orders = [frappe.get_doc("Sales Order", n) for n in (self.data.so1, self.data.so2)]
		self.assertEqual(flt(summary["Sold / Offered"], 2), flt(sum(o.base_net_total for o in orders), 2))
		listed = sum(r.base_price_list_rate * r.qty for o in orders for r in o.items)
		self.assertEqual(flt(summary["Listed"], 2), flt(listed, 2))
		self.assertEqual(flt(summary["Discount"], 2), flt(listed - sum(o.base_net_total for o in orders), 2))

	def test_item_group_and_date_filters(self):
		rows, _summary = self.rows(item_group="All Item Groups")
		self.assertEqual(len(rows), 2)
		rows, _summary = self.rows(from_date="2026-03-17", to_date="2026-03-17")
		self.assertEqual(rows, {})

	def test_report_roles(self):
		self.assertEqual(
			{r.role for r in frappe.get_doc("Report", REPORT).roles}, {"Sales Manager", "System Manager"}
		)
		with self.set_user(self.data.sales_1), self.assertRaises(frappe.PermissionError):
			run(REPORT, filters=report_filters(self.data))
