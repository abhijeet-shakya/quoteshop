"""CONTRACTS §6.1 - QSEnquiry.set_totals() (runs in validate). Exact values to currency precision."""

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.doctype.qs_enquiry.qs_enquiry import QSEnquiry
from quoteshop.quoteshop_enquiry.tests.factories import make_enquiry, make_item

# All links are built by factories (CONTRACTS §5.1); Items via make_item inside make_enquiry.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Customer",
	"Contact",
	"CRM Deal",
	"Sales Order",
	"User",
	"Item",
	"UOM",
	"WhatsApp Message",
]

A, B, C, D, E, F, G = (f"_QS Test Item {x}" for x in "ABCDEFG")


def line(item_code, requested_qty, listed_rate, offered_rate=None, offered_qty=None, **extra):
	d = {"item_code": item_code, "requested_qty": requested_qty, "listed_rate": listed_rate, **extra}
	if offered_rate is not None:
		d["offered_rate"] = offered_rate
	if offered_qty is not None:
		d["offered_qty"] = offered_qty
	return d


class TestQSEnquiry(IntegrationTestCase):
	def assertTotals(self, doc, **expected):
		self.assertEqual({k: doc.get(k) for k in expected}, expected)

	def test_controller_class(self):
		self.assertIsInstance(make_enquiry([line(A, 1, 10)]), QSEnquiry)

	def test_naming_series(self):
		self.assertRegex(make_enquiry([line(A, 1, 10)]).name, r"^RFQ-\d{5}$")

	def test_totals_one_line(self):
		doc = make_enquiry([line(A, 7, 120, offered_rate=99.97)])
		self.assertEqual(doc.items[0].amount, 699.79)
		self.assertTotals(
			doc,
			total_listed=840.0,
			total_offered=699.79,
			total_saved=140.21,
			saved_pct=16.69,
			line_count=1,
			unit_count=7.0,
			available_count=1,
			partial_count=0,
			not_available_count=0,
		)

	def test_totals_hundred_lines(self):
		lines = [
			line(
				f"_QS Test Item {i:03d}",
				i % 5 + 1,
				round(100 + i * 1.37, 2),
				offered_rate=round(100 + i * 1.37 - (i % 4) * 3.11, 2),
			)
			for i in range(1, 101)
		]
		doc = make_enquiry(lines)
		self.assertTotals(
			doc,
			total_listed=50755.5,
			total_offered=49356.0,
			total_saved=1399.5,
			saved_pct=2.76,
			line_count=100,
			unit_count=300.0,
			available_count=100,
			partial_count=0,
			not_available_count=0,
		)
		# line 7: qty 3, listed 109.59, offered 109.59 - 3 * 3.11 = 100.26
		row = doc.items[6]
		self.assertEqual((row.offered_qty, row.offered_rate, row.amount), (3.0, 100.26, 300.78))

	def test_defaults_offered_qty_and_rate(self):
		doc = make_enquiry([line(A, 4, 25)])
		row = doc.items[0]
		self.assertEqual((row.offered_qty, row.offered_rate, row.amount), (4.0, 25.0, 100.0))
		self.assertTotals(doc, total_listed=100.0, total_offered=100.0, total_saved=0.0, saved_pct=0.0)

	def test_explicit_zero_offered_qty_not_defaulted(self):
		doc = make_enquiry([line(A, 4, 25, offered_qty=0), line(B, 1, 10)])
		self.assertEqual((doc.items[0].offered_qty, doc.items[0].amount), (0.0, 0.0))
		self.assertTotals(doc, total_listed=10.0, total_offered=10.0, unit_count=1.0, line_count=2)

	def test_not_available_and_removed_excluded(self):
		doc = make_enquiry(
			[
				line(A, 2, 50, offered_rate=45),
				line(B, 3, 20, offered_rate=0, availability="Not Available"),
				line(C, 1, 10, offered_rate=10, change_flag="Removed"),
			]
		)
		self.assertEqual([r.amount for r in doc.items], [90.0, 0.0, 0.0])
		self.assertTotals(
			doc,
			total_listed=100.0,
			total_offered=90.0,
			total_saved=10.0,
			saved_pct=10.0,
			line_count=2,
			unit_count=2.0,
			available_count=1,
			partial_count=0,
			not_available_count=1,
		)

	def test_counts(self):
		doc = make_enquiry(
			[
				line(A, 2, 100, offered_rate=90),
				line(B, 10, 10, offered_rate=9.5, offered_qty=6, availability="Partial"),
				line(C, 1, 200, offered_rate=200, availability="Made to Order"),
				line(D, 5, 30, availability="Not Available"),
				line(E, 3, 40, offered_rate=35, availability="Alternative", alternative_item=F),
				line(F, 4, 25, offered_rate=20, availability="Partial", change_flag="Removed"),
			]
		)
		self.assertEqual([r.amount for r in doc.items], [180.0, 57.0, 200.0, 0.0, 105.0, 0.0])
		self.assertTotals(
			doc,
			total_listed=580.0,
			total_offered=542.0,
			total_saved=38.0,
			saved_pct=6.55,
			line_count=5,
			unit_count=12.0,
			available_count=1,
			partial_count=1,
			not_available_count=1,
		)

	def test_saved_pct_rounding(self):
		self.assertEqual(make_enquiry([line(A, 1, 7, offered_rate=6)]).saved_pct, 14.29)
		self.assertEqual(make_enquiry([line(A, 3, 33.33, offered_rate=33)]).saved_pct, 0.99)

	def test_saved_pct_zero_listed(self):
		doc = make_enquiry([line(A, 1, 0, offered_rate=50)])
		self.assertTotals(doc, total_listed=0.0, total_offered=50.0, total_saved=-50.0, saved_pct=0.0)
		doc = make_enquiry([line(A, 2, 10, availability="Not Available")])
		self.assertTotals(doc, total_listed=0.0, total_offered=0.0, total_saved=0.0, saved_pct=0.0)

	def test_totals_recomputed_on_save(self):
		doc = make_enquiry([line(A, 2, 50, offered_rate=45)])
		doc.items[0].offered_rate = 40
		doc.save(ignore_permissions=True)
		self.assertTotals(doc, total_offered=80.0, total_saved=20.0, saved_pct=20.0)

	def test_listed_rate_never_refreshed(self):
		"""listed_rate is the request-time snapshot; validate never reads the current Item Price."""
		make_item(G, rate=500)  # current starting price differs from the snapshot
		doc = make_enquiry([line(G, 2, 10, offered_rate=9)])
		self.assertEqual(doc.items[0].listed_rate, 10.0)
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(doc.items[0].listed_rate, 10.0)
		self.assertTotals(doc, total_listed=20.0, total_offered=18.0, total_saved=2.0, saved_pct=10.0)

	def test_zero_offered_rate_on_counting_line_rejected_when_priced(self):
		"""CONTRACTS §6.1: a priced quote (Price Sent / Accepted) cannot hold a counting line at rate 0."""
		for status in ("Price Sent", "Accepted"):
			with self.subTest(status=status), self.assertRaises(frappe.ValidationError):
				make_enquiry([line(A, 2, 50, offered_rate=0)], status=status)

	def test_zero_offered_rate_rejected_when_moving_to_price_sent(self):
		doc = make_enquiry([line(A, 2, 50, offered_rate=0)], status="Requested")
		doc.status = "Price Sent"
		doc.flags.qs_status_change = True  # CONTRACTS §10: only QuoteShop actions move the status
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		doc.reload()  # a rejected save leaves the in-memory doc stale
		doc.status = "Price Sent"
		doc.flags.qs_status_change = True
		doc.items[0].offered_rate = 45
		doc.save(ignore_permissions=True)  # control: priced line is fine
		self.assertTotals(doc, total_offered=90.0)

	def test_zero_offered_rate_allowed_before_pricing(self):
		"""Unpriced lines (Draft / Requested / Changes Requested) save and add 0 to total_offered."""
		for status in ("Draft", "Requested", "Changes Requested"):
			with self.subTest(status=status):
				doc = make_enquiry([line(A, 2, 50, offered_rate=0), line(B, 1, 10)], status=status)
				self.assertEqual((doc.items[0].offered_rate, doc.items[0].amount), (0.0, 0.0))
				self.assertTotals(doc, total_offered=10.0, unit_count=3.0, line_count=2)

	def test_unpriced_listed_rate_zero_before_pricing_only(self):
		"""'Price on request' item: listed_rate 0 defaults offered_rate 0; fine until a price is sent."""
		doc = make_enquiry([line(A, 3, 0)])
		self.assertEqual((doc.items[0].offered_rate, doc.items[0].amount), (0.0, 0.0))
		self.assertTotals(doc, total_listed=0.0, total_offered=0.0, saved_pct=0.0)
		doc.status = "Price Sent"
		doc.flags.qs_status_change = True
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_zero_offered_rate_allowed_when_offered_qty_zero(self):
		doc = make_enquiry([line(A, 2, 50, offered_rate=0, offered_qty=0)])
		self.assertTotals(doc, total_offered=0.0, unit_count=0.0)

	def test_duplicate_item_code_rejected(self):
		"""One line per item_code (§6.1): duplicates rejected on insert and on save."""
		with self.assertRaises(frappe.ValidationError):
			make_enquiry([line(A, 1, 10), line(A, 2, 10)])
		doc = make_enquiry([line(A, 1, 10)])  # control: the same line alone is valid
		doc.append("items", line(A, 2, 10))
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_status_change_only_through_quoteshop_actions(self):
		"""CONTRACTS §10: a plain save / client set_value (Kanban drag) cannot move the status."""
		from frappe.client import set_value

		doc = make_enquiry([line(A, 2, 50, offered_rate=45)], status="Requested")
		doc.status = "Lost"
		with self.assertRaisesRegex(frappe.ValidationError, "Status changes only through QuoteShop actions"):
			doc.save(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "Status changes only through QuoteShop actions"):
			set_value("QS Enquiry", doc.name, "status", "Price Sent")
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Requested")

		doc.reload()
		doc.notes = "edit without a status change"
		doc.save(ignore_permissions=True)  # control: other edits still save
		doc.status = "Lost"
		doc.flags.qs_status_change = True
		doc.save(ignore_permissions=True)  # control: the QuoteShop flag allows it
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Lost")
