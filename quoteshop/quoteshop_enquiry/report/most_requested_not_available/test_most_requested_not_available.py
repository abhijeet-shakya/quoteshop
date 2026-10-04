"""REP-05 Most-requested Not Available counts reconcile with QS Enquiry lines; Sales User sees only own."""

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.report.most_requested_not_available.most_requested_not_available import (
	execute,
)
from quoteshop.quoteshop_enquiry.tests.factories import make_report_dataset, report_filters


class TestMostRequestedNotAvailable(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = make_report_dataset()

	def rows(self):
		_columns, data, _msg, _chart = execute(report_filters(self.data))
		return {r.item_code: (r.times_requested, r.requested_qty) for r in data}

	def test_counts_reconcile(self):
		self.assertEqual(self.rows(), {"_QS-REP-C": (3, 10)})
		source = frappe.get_all(
			"QS Enquiry Item",
			filters={
				"parenttype": "QS Enquiry",
				"parent": ("in", [self.data[k] for k in ("e1", "e2", "e3", "e4", "e5")]),
				"availability": "Not Available",
			},
			fields=["parent", "requested_qty"],
		)
		self.assertEqual((len({r.parent for r in source}), sum(r.requested_qty for r in source)), (3, 10))

	def test_sales_user_sees_only_own(self):
		with self.set_user(self.data.sales_1):
			self.assertEqual(self.rows(), {"_QS-REP-C": (2, 7)})
