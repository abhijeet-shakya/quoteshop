"""Phase 5 - desk pricing actions and quote versions (TESTING §3 Pricing & versions, CONTRACTS §6.1, §7.2)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate

from quoteshop.quoteshop_enquiry import quote_view, versions
from quoteshop.quoteshop_enquiry.tests.factories import (
	SECOND_MOBILE,
	accept_and_order,
	make_enquiry_settings,
	make_group_tree,
	make_order_settings,
	make_published_item,
	make_quote,
	make_user,
	send_quote,
)

SALES_1 = "qs-b-sales-1@example.com"
SALES_2 = "qs-b-sales-2@example.com"
DAY = "2026-06-10 10:00:00"


def line(code, qty, listed, **extra):
	return {"item_code": code, "requested_qty": qty, "listed_rate": listed, **extra}


def by_code(doc):
	return {row.item_code: row for row in doc.items}


class PricingTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_order_settings()
		make_enquiry_settings()
		make_user(SALES_1, ["Sales User"])
		make_user(SALES_2, ["Sales User"])


class TestTotals(PricingTestCase):
	def test_one_line_after_discount(self):
		doc = make_quote([line("_QS-V-T1", 3, 100)])
		versions.apply_discount(doc.name, 10, "all")
		doc.reload()
		self.assertEqual(doc.items[0].offered_rate, 90.0)
		self.assertEqual(doc.items[0].amount, 270.0)
		self.assertEqual(
			(doc.total_listed, doc.total_offered, doc.total_saved, doc.saved_pct), (300.0, 270.0, 30.0, 10.0)
		)

	def test_hundred_lines_after_discount(self):
		lines = [line(f"_QS-V-H{i:03d}", i % 7 + 1, flt(99.99 + i * 3.37, 2)) for i in range(100)]
		doc = make_quote(lines)
		versions.apply_discount(doc.name, 7.5, "all")
		doc.reload()

		listed = offered = 0.0
		for spec in lines:
			rate = flt(spec["listed_rate"] * 0.925, 2)
			row = by_code(doc)[spec["item_code"]]
			self.assertEqual(row.offered_rate, rate, spec["item_code"])
			self.assertEqual(row.amount, flt(rate * spec["requested_qty"], 2), spec["item_code"])
			listed += spec["listed_rate"] * spec["requested_qty"]
			offered += flt(rate * spec["requested_qty"], 2)
		self.assertEqual(doc.total_listed, flt(listed, 2))
		self.assertEqual(doc.total_offered, flt(offered, 2))
		self.assertEqual(doc.total_saved, flt(flt(listed, 2) - flt(offered, 2), 2))
		self.assertEqual(doc.saved_pct, flt(doc.total_saved / doc.total_listed * 100, 2))
		self.assertEqual((doc.line_count, doc.unit_count), (100, sum(s["requested_qty"] for s in lines)))


class TestBulkDiscount(PricingTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_group_tree({"_QS-V Cues": {"_QS-V Cue Cases": {}}, "_QS-V Chalk": {}})
		make_published_item("_QS-V-CUE", group="_QS-V Cues")
		make_published_item("_QS-V-CASE", group="_QS-V Cue Cases")
		make_published_item("_QS-V-CHALK", group="_QS-V Chalk")

	def quote(self):
		return make_quote(
			[
				line("_QS-V-CUE", 2, 1000),
				line("_QS-V-CASE", 1, 450.5),
				line("_QS-V-CHALK", 10, 33.33),
				line("_QS-V-POR", 1, 0),  # price on request: never discounted
			]
		)

	def rates(self, name):
		return {r.item_code: r.offered_rate for r in frappe.get_doc("QS Enquiry", name).items}

	def test_discount_all_lines(self):
		doc = self.quote()
		self.assertEqual(versions.apply_discount(doc.name, 8, "all"), {"updated": 3})
		self.assertEqual(
			self.rates(doc.name),
			{"_QS-V-CUE": 920.0, "_QS-V-CASE": 414.46, "_QS-V-CHALK": 30.66, "_QS-V-POR": 0.0},
		)
		doc.reload()
		self.assertEqual(doc.total_offered, flt(1840 + 414.46 + 306.6, 2))

	def test_discount_selected_lines(self):
		doc = self.quote()
		rows = [by_code(doc)["_QS-V-CASE"].name, by_code(doc)["_QS-V-CHALK"].name]
		self.assertEqual(
			versions.apply_discount(doc.name, 10, "selected", rows=json.dumps(rows)), {"updated": 2}
		)
		self.assertEqual(
			self.rates(doc.name),
			{"_QS-V-CUE": 1000.0, "_QS-V-CASE": 405.45, "_QS-V-CHALK": 30.0, "_QS-V-POR": 0.0},
		)

	def test_discount_by_category_includes_descendants(self):
		doc = self.quote()
		self.assertEqual(
			versions.apply_discount(doc.name, 5, "category", item_group="_QS-V Cues"), {"updated": 2}
		)
		self.assertEqual(
			self.rates(doc.name),
			{"_QS-V-CUE": 950.0, "_QS-V-CASE": 427.98, "_QS-V-CHALK": 33.33, "_QS-V-POR": 0.0},
		)

	def test_invalid_input_rejected(self):
		doc = self.quote()
		other = make_quote([line("_QS-V-CUE", 1, 1000)])
		for kwargs in (
			{"percent": 100, "scope": "all"},
			{"percent": -1, "scope": "all"},
			{"percent": 5, "scope": "everything"},
			{"percent": 5, "scope": "selected", "rows": []},
			{"percent": 5, "scope": "selected", "rows": [other.items[0].name]},
			{"percent": 5, "scope": "category", "item_group": "_QS no such group"},
		):
			with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
				versions.apply_discount(doc.name, **kwargs)
		self.assertEqual(self.rates(doc.name)["_QS-V-CUE"], 1000.0)


class TestAvailability(PricingTestCase):
	def quote(self):
		return make_quote([line("_QS-V-A1", 10, 100), line("_QS-V-A2", 4, 50), line("_QS-V-A3", 2, 300)])

	def test_partial_updates_totals_and_counts(self):
		doc = self.quote()
		row = by_code(doc)["_QS-V-A1"]
		versions.set_availability(
			doc.name, [row.name], "Partial", note="6 now", lead_time_days=5, offered_qty=6
		)
		doc.reload()
		row = by_code(doc)["_QS-V-A1"]
		self.assertEqual((row.offered_qty, row.lead_time_days, row.availability_note), (6.0, 5, "6 now"))
		self.assertEqual((doc.total_listed, doc.total_offered), (600 + 200 + 600.0, 600 + 200 + 600.0))
		self.assertEqual((doc.unit_count, doc.partial_count, doc.available_count), (12.0, 1, 2))

	def test_not_available_excluded_and_counted(self):
		doc = self.quote()
		versions.set_availability(doc.name, [by_code(doc)["_QS-V-A3"].name], "Not Available")
		doc.reload()
		self.assertEqual(by_code(doc)["_QS-V-A3"].amount, 0.0)
		self.assertEqual((doc.total_listed, doc.total_offered), (1200.0, 1200.0))
		self.assertEqual((doc.line_count, doc.unit_count), (3, 14.0))
		self.assertEqual((doc.available_count, doc.not_available_count), (2, 1))

	def test_alternative_counts_in_totals_not_in_availability_counts(self):
		doc = self.quote()
		versions.set_availability(
			doc.name, [by_code(doc)["_QS-V-A2"].name], "Alternative", note="Blue instead"
		)
		doc.reload()
		self.assertEqual(doc.total_offered, 1000 + 200 + 600.0)
		self.assertEqual((doc.available_count, doc.partial_count, doc.not_available_count), (2, 0, 0))
		self.assertEqual(doc.line_count, 3)

	def test_invalid_availability_rejected(self):
		doc = self.quote()
		rows = [doc.items[0].name]
		for kwargs in ({"availability": "Maybe"}, {"availability": "Partial", "offered_qty": -1}):
			with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
				versions.set_availability(doc.name, rows, **kwargs)


class TestCopyFromLastOrder(PricingTestCase):
	def test_rates_from_last_submitted_order(self):
		with self.change_settings("QS Store Settings", auto_submit_sales_order=1):
			first = make_quote([line("_QS-V-C1", 2, 500), line("_QS-V-C2", 1, 80)], mobile=SECOND_MOBILE)
			versions.apply_discount(first.name, 12, "all")
			order = accept_and_order(first.name, send_quote(first.name).token)
		self.assertEqual(frappe.db.get_value("Sales Order", order, "docstatus"), 1)

		repeat = make_quote([line("_QS-V-C1", 5, 500), line("_QS-V-C3", 1, 70)], mobile=SECOND_MOBILE)
		self.assertEqual(versions.copy_from_last_order(repeat.name), {"updated": 1, "sales_order": order})
		rates = {r.item_code: r.offered_rate for r in frappe.get_doc("QS Enquiry", repeat.name).items}
		self.assertEqual(rates, {"_QS-V-C1": 440.0, "_QS-V-C3": 70.0})

	def test_no_previous_order_rejected(self):
		doc = make_quote([line("_QS-V-C9", 1, 10)], mobile="+919800000099")
		with self.assertRaises(frappe.ValidationError):
			versions.copy_from_last_order(doc.name)


class TestSendPrice(PricingTestCase):
	def test_send_price_creates_version_and_enqueues_once(self):
		doc = make_quote([line("_QS-V-S1", 2, 100)])
		with self.freeze_time(DAY):
			sent = send_quote(doc.name)
		doc.reload()
		self.assertEqual((sent.version, doc.current_version, doc.status), (1, 1, "Price Sent"))
		self.assertEqual(getdate(doc.valid_till), getdate(add_days("2026-06-10", 15)))
		self.assertIn(f"/q/{doc.name}?t=", sent.url)

		sent.enqueue.assert_called_once()
		call = sent.enqueue.call_args
		self.assertEqual(call.args[0], "quoteshop.quoteshop_enquiry.whatsapp.send_message")
		self.assertTrue(call.kwargs["enqueue_after_commit"])
		self.assertEqual(call.kwargs["job_id"], f"qs-wa-{doc.name}-1-price_sent")
		self.assertEqual((call.kwargs["event"], call.kwargs["version"]), ("price_sent", 1))
		self.assertEqual(call.kwargs["url"], sent.url)  # PDF is built inside this one job (header DOCUMENT)

	def test_unpriced_line_blocks_send(self):
		doc = make_quote([line("_QS-V-S2", 1, 0)])
		with self.assertRaises(frappe.ValidationError):
			send_quote(doc.name)
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Requested")

	def test_accepted_enquiry_cannot_be_priced(self):
		doc = make_quote([line("_QS-V-S3", 1, 10)])
		accept_and_order(doc.name, send_quote(doc.name).token)
		for call in (
			lambda: versions.send_price(doc.name),
			lambda: versions.apply_discount(doc.name, 5, "all"),
			lambda: versions.mark_lost(doc.name, "late"),
		):
			with self.assertRaises(frappe.ValidationError):
				call()


class TestCreateVersion(PricingTestCase):
	def two_versions(self):
		doc = make_quote(
			[
				line("_QS-V-V1", 2, 100),
				line("_QS-V-V2", 3, 50),
				line("_QS-V-V3", 1, 10),
				line("_QS-V-V4", 1, 20),
			]
		)
		with self.freeze_time(DAY):
			v1 = send_quote(doc.name)
		doc.reload()
		rows = by_code(doc)
		rows["_QS-V-V1"].offered_rate = 95
		rows["_QS-V-V2"].offered_qty = 2
		rows["_QS-V-V3"].availability = "Alternative"
		rows["_QS-V-V3"].alternative_item = make_published_item("_QS-V-V3-ALT")
		doc.save()
		with self.freeze_time("2026-06-14 09:00:00"):
			v2 = send_quote(doc.name)
		return frappe.get_doc("QS Enquiry", doc.name), v1, v2

	def test_snapshot(self):
		doc, _v1, _v2 = self.two_versions()
		v1, v2 = sorted(doc.versions, key=lambda v: v.version)
		snap1, snap2 = json.loads(v1.snapshot), json.loads(v2.snapshot)
		self.assertEqual({ln["item_code"]: ln["offered_rate"] for ln in snap1["lines"]}["_QS-V-V1"], 100.0)
		self.assertEqual({ln["item_code"]: ln["offered_rate"] for ln in snap2["lines"]}["_QS-V-V1"], 95.0)
		self.assertEqual(snap1["totals"]["total_offered"], 200 + 150 + 10 + 20.0)
		self.assertEqual(snap2["totals"]["total_offered"], doc.total_offered)
		self.assertEqual(snap2["totals"]["total_offered"], 190 + 100 + 10 + 20.0)

	def test_change_flags_set(self):
		doc, _v1, _v2 = self.two_versions()
		self.assertEqual(
			{r.item_code: r.change_flag for r in doc.items},
			{
				"_QS-V-V1": "Price changed",
				"_QS-V-V2": "Qty changed",
				"_QS-V-V3": "Alternative",
				"_QS-V-V4": "",
			},
		)
		v1 = min(doc.versions, key=lambda v: v.version)
		self.assertTrue(all(not ln["change_flag"] for ln in json.loads(v1.snapshot)["lines"]))

	def test_token_rotation_old_invalid(self):
		doc, v1, v2 = self.two_versions()
		self.assertNotEqual(v1.token, v2.token)
		with self.set_user("Guest"), self.freeze_time("2026-06-15 09:00:00"):  # v2 is valid till 2026-06-29
			self.assertTrue(quote_view.get_quote_view(doc.name, v1.token)["outdated"])
			self.assertEqual(quote_view.get_quote_view(doc.name, v2.token)["version"], 2)
			old = quote_view.accept_quote(doc.name, v1.token)
		self.assertTrue(old.get("outdated"))
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")
		stored = [v.token_hash for v in doc.versions]
		self.assertNotIn(v2.token, stored)  # raw tokens never stored

	def test_validity_reset(self):
		doc, _v1, _v2 = self.two_versions()
		self.assertEqual(getdate(doc.valid_till), getdate("2026-06-29"))
		v2 = max(doc.versions, key=lambda v: v.version)
		self.assertEqual(getdate(v2.token_expires), getdate("2026-06-30"))

	def test_summary_and_version_meta(self):
		doc, _v1, _v2 = self.two_versions()
		v1, v2 = sorted(doc.versions, key=lambda v: v.version)
		self.assertEqual((v1.version, v1.created_by_type, v1.summary), (1, "Sales", "First quote"))
		self.assertEqual((v2.version, v2.created_by_type, v2.created_by), (2, "Sales", "Administrator"))
		self.assertEqual(
			sorted(v2.summary.split(", ")), ["1 alternative", "1 price changed", "1 qty changed"]
		)

	def test_unchanged_resend_says_no_changes(self):
		doc = make_quote([line("_QS-V-N1", 1, 10)])
		send_quote(doc.name)
		send_quote(doc.name)
		v2 = max(frappe.get_doc("QS Enquiry", doc.name).versions, key=lambda v: v.version)
		self.assertEqual(v2.summary, "No changes")


class TestMarkLost(PricingTestCase):
	def test_mark_lost_sets_reason_and_deal(self):
		doc = make_quote([line("_QS-V-L1", 1, 10)], deal=True)
		versions.mark_lost(doc.name, "  Bought elsewhere  ")
		doc.reload()
		self.assertEqual((doc.status, doc.lost_reason), ("Lost", "Bought elsewhere"))
		deal = frappe.db.get_value(
			"CRM Deal", doc.crm_deal, ["status", "lost_reason", "lost_notes"], as_dict=True
		)
		self.assertEqual(frappe.db.get_value("CRM Deal Status", deal.status, "type"), "Lost")
		self.assertEqual((deal.lost_reason, deal.lost_notes), ("Other", "Bought elsewhere"))

	def test_blank_reason_and_repeat_rejected(self):
		doc = make_quote([line("_QS-V-L2", 1, 10)])
		with self.assertRaises(frappe.ValidationError):
			versions.mark_lost(doc.name, "  ")
		versions.mark_lost(doc.name, "No reply")
		with self.assertRaises(frappe.ValidationError):
			versions.mark_lost(doc.name, "again")


class TestDeskPermissions(PricingTestCase):
	"""Sales User acts only on own/assigned enquiries; others (and Guest) are denied."""

	def actions(self, doc):
		row = doc.items[0].name
		return {
			"apply_discount": lambda: versions.apply_discount(doc.name, 5, "all"),
			"set_availability": lambda: versions.set_availability(doc.name, [row], "Partial"),
			"copy_from_last_order": lambda: versions.copy_from_last_order(doc.name),
			"send_price": lambda: versions.send_price(doc.name),
			"mark_lost": lambda: versions.mark_lost(doc.name, "x"),
		}

	def test_assigned_sales_user_allowed(self):
		doc = make_quote([line("_QS-V-P1", 2, 100)], assigned_to=SALES_1)
		with self.set_user(SALES_1), patch("frappe.enqueue"):
			versions.apply_discount(doc.name, 5, "all")
			versions.set_availability(doc.name, [doc.items[0].name], "Partial", offered_qty=1)
			self.assertEqual(versions.send_price(doc.name)["version"], 1)
			versions.mark_lost(doc.name, "Too slow")
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Lost")

	def test_other_sales_user_and_guest_denied(self):
		doc = make_quote([line("_QS-V-P2", 2, 100)], assigned_to=SALES_1)
		for user in (SALES_2, "Guest"):
			for action, call in self.actions(doc).items():
				with (
					self.subTest(user=user, action=action),
					self.set_user(user),
					patch("frappe.enqueue") as enqueue,
					self.assertRaises(frappe.PermissionError),
				):
					call()
				enqueue.assert_not_called()
		doc.reload()
		self.assertEqual(
			(doc.status, doc.current_version, doc.items[0].offered_rate), ("Requested", 0, 100.0)
		)


class TestStatusLock(PricingTestCase):
	"""CONTRACTS §10: status (and valid_till) change only through QuoteShop actions."""

	def test_status_and_valid_till_read_only_in_meta(self):
		meta = frappe.get_meta("QS Enquiry")
		self.assertTrue(meta.get_field("status").read_only)
		self.assertTrue(meta.get_field("valid_till").read_only)

	def test_form_save_refused(self):
		doc = make_quote([line("_QS-V-K1", 1, 10)])
		doc.status = "Accepted"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Requested")

	def test_set_value_refused(self):
		doc = make_quote([line("_QS-V-K2", 1, 10)])
		for target in ("Accepted", "Lost", "Price Sent"):
			with self.subTest(target=target), self.assertRaises(frappe.ValidationError):
				frappe.client.set_value("QS Enquiry", doc.name, "status", target)
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Requested")

	def test_kanban_drag_refused(self):
		from frappe.desk.doctype.kanban_board.kanban_board import update_order_for_single_card

		doc = make_quote([line("_QS-V-K3", 1, 10)])
		with self.assertRaises(frappe.ValidationError):
			update_order_for_single_card("Enquiry Pipeline", doc.name, "Requested", "Accepted", 0, 0)
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Requested")

	def test_quoteshop_actions_still_move_status(self):
		doc = make_quote([line("_QS-V-K4", 1, 10)])
		send_quote(doc.name)
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")
		versions.mark_lost(doc.name, "No budget")
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Lost")

	def test_other_edits_allowed_without_status_change(self):
		doc = make_quote([line("_QS-V-K5", 1, 10)])
		doc.notes = "call after 5pm"
		doc.save()
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "notes"), "call after 5pm")


class TestResendPrice(PricingTestCase):
	"""CONTRACTS §10: resend_price = same version, no token rotation, sign-in link, job_id suffix -resend."""

	def test_resend_same_version_no_rotation(self):
		doc = make_quote([line("_QS-V-R1", 2, 100)])
		with self.freeze_time(DAY):
			sent = send_quote(doc.name)
			with patch("frappe.enqueue") as enqueue:
				result = versions.resend_price(doc.name)
			after = frappe.get_doc("QS Enquiry", doc.name)
			self.assertEqual(result, {"version": 1, "url": versions.login_url(doc.name)})
			self.assertEqual((after.current_version, len(after.versions)), (1, 1))
			self.assertEqual(getdate(after.valid_till), getdate("2026-06-25"))
			with self.set_user("Guest"):
				self.assertEqual(
					quote_view.get_quote_view(doc.name, sent.token)["version"], 1
				)  # old link works

		enqueue.assert_called_once()
		call = enqueue.call_args
		self.assertEqual(call.kwargs["job_id"], f"qs-wa-{doc.name}-1-price_sent-resend")
		self.assertEqual(
			(call.kwargs["event"], call.kwargs["version"], call.kwargs["resend"]), ("price_sent", 1, True)
		)
		self.assertEqual(call.kwargs["url"], versions.login_url(doc.name))

	def test_resend_needs_open_price_sent(self):
		doc = make_quote([line("_QS-V-R2", 1, 10)])
		with self.assertRaises(frappe.ValidationError):
			versions.resend_price(doc.name)  # never priced
		with self.freeze_time(DAY):
			send_quote(doc.name)
		with self.freeze_time("2026-07-01 09:00:00"), self.assertRaises(frappe.ValidationError):
			versions.resend_price(doc.name)  # expired link

	def test_resend_permission(self):
		doc = make_quote([line("_QS-V-R3", 1, 10)], assigned_to=SALES_1)
		send_quote(doc.name)
		for user in (SALES_2, "Guest"):
			with self.subTest(user=user), self.set_user(user), patch("frappe.enqueue") as enqueue:
				with self.assertRaises(frappe.PermissionError):
					versions.resend_price(doc.name)
				enqueue.assert_not_called()
		with self.set_user(SALES_1), patch("frappe.enqueue"):
			self.assertEqual(versions.resend_price(doc.name)["version"], 1)
