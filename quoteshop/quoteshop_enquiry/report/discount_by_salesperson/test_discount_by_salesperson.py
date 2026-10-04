"""REP-02 Discount by Salesperson reconciles with accepted QS Enquiries; Sales User sees only own."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from quoteshop.quoteshop_enquiry.report.discount_by_salesperson.discount_by_salesperson import execute
from quoteshop.quoteshop_enquiry.tests.factories import make_report_dataset, report_filters


class TestDiscountBySalesperson(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = make_report_dataset()

	def rows(self, **extra):
		_columns, data, _msg, _chart, summary = execute(report_filters(self.data, **extra))
		return {
			r.salesperson: (
				r.enquiries,
				flt(r.total_listed, 2),
				flt(r.total_offered, 2),
				flt(r.total_saved, 2),
				flt(r.discount_pct, 2),
			)
			for r in data
		}, {s["label"]: s["value"] for s in summary}

	def test_totals_reconcile(self):
		rows, summary = self.rows()
		self.assertEqual(
			rows, {self.data.sales_1: (1, 1200, 1080, 120, 10), self.data.sales_2: (1, 250, 200, 50, 20)}
		)
		accepted = [frappe.get_doc("QS Enquiry", n) for n in (self.data.e1, self.data.e2)]
		self.assertEqual(flt(summary["Discount"], 2), flt(sum(e.total_saved for e in accepted), 2))
		self.assertEqual(flt(summary["Sold / Offered"], 2), flt(sum(e.total_offered for e in accepted), 2))

	def test_sales_user_sees_only_own(self):
		with self.set_user(self.data.sales_1):
			rows, _summary = self.rows()
		self.assertEqual(list(rows), [self.data.sales_1])
