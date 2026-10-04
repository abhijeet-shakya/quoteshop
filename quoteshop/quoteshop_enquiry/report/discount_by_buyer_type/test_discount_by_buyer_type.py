"""REP-03 Discount by Buyer Type reconciles with accepted QS Enquiries; Sales User sees only own."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from quoteshop.quoteshop_enquiry.report.discount_by_buyer_type.discount_by_buyer_type import execute
from quoteshop.quoteshop_enquiry.tests.factories import make_report_dataset, report_filters


class TestDiscountByBuyerType(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = make_report_dataset()

	def rows(self):
		_columns, data, _msg, _chart, summary = execute(report_filters(self.data))
		return {
			r.buyer_type: (
				r.enquiries,
				flt(r.total_listed, 2),
				flt(r.total_offered, 2),
				flt(r.total_saved, 2),
			)
			for r in data
		}, {s["label"]: s["value"] for s in summary}

	def test_totals_reconcile(self):
		rows, summary = self.rows()
		self.assertEqual(rows, {"Retailer": (1, 1200, 1080, 120), "Club": (1, 250, 200, 50)})
		self.assertEqual(flt(summary["Listed"], 2), 1450)
		self.assertEqual(flt(summary["Discount %"], 2), flt(170 * 100 / 1450, 2))

	def test_sales_user_sees_only_own(self):
		with self.set_user(self.data.sales_2):
			rows, _summary = self.rows()
		self.assertEqual(rows, {"Club": (1, 250, 200, 50)})
