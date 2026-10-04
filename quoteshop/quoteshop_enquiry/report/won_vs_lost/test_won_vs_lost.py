"""REP-04 Won vs Lost (with reasons) reconciles with QS Enquiry statuses; Sales User sees only own."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from quoteshop.quoteshop_enquiry.report.won_vs_lost.won_vs_lost import execute
from quoteshop.quoteshop_enquiry.tests.factories import make_report_dataset, report_filters


class TestWonVsLost(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = make_report_dataset()

	def rows(self, **extra):
		_columns, data, _msg, _chart, summary = execute(report_filters(self.data, **extra))
		return {(r.status, r.lost_reason): (r.enquiries, flt(r.total_offered, 2)) for r in data}, {
			s["label"]: s["value"] for s in summary
		}

	def test_totals_reconcile(self):
		rows, summary = self.rows()
		self.assertEqual(rows, {("Accepted", ""): (2, 1280), ("Lost", "Too expensive"): (2, 310)})
		self.assertEqual((summary["Won"], summary["Lost"], summary["Win Rate"]), (2, 2, 50))
		lost = frappe.get_all(
			"QS Enquiry", filters={"name": ("in", [self.data.e3, self.data.e4])}, pluck="total_offered"
		)
		self.assertEqual(flt(summary["Lost Value"], 2), flt(sum(lost), 2))

	def test_filters(self):
		rows, _summary = self.rows(salesperson=self.data.sales_2, buyer_type="Club")
		self.assertEqual(rows, {("Accepted", ""): (1, 200), ("Lost", "Too expensive"): (1, 60)})

	def test_sales_user_sees_only_own(self):
		with self.set_user(self.data.sales_1):
			rows, _summary = self.rows()
		self.assertEqual(rows, {("Accepted", ""): (1, 1080), ("Lost", "Too expensive"): (1, 250)})
