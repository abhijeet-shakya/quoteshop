"""Phase 6 - buyer view, buyer changes, accept (website + WhatsApp), downloads (TESTING §3 Accept & order)."""

import io
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry import orders, quote_view, versions, whatsapp
from quoteshop.quoteshop_enquiry.tests.factories import (
	DEFAULT_MOBILE,
	WA_POST,
	link_wa_templates,
	make_enquiry_settings,
	make_order_settings,
	make_published_item,
	make_quote,
	send_quote,
)

DAY = "2026-06-10 10:00:00"


def line(code, qty, listed, **extra):
	return {"item_code": code, "requested_qty": qty, "listed_rate": listed, **extra}


def token_of(url):
	return parse_qs(urlsplit(url).query)["t"][0]


class QuoteViewTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_order_settings()
		make_enquiry_settings()
		make_published_item("_QS-Q-NEW", rate=40)
		make_published_item("_QS-Q-HIDDEN", published=0)

	def setUp(self):
		super().setUp()
		patcher = patch("frappe.enqueue")
		self.enqueue = patcher.start()
		self.addCleanup(patcher.stop)

	def sent_quote(self, **fields):
		doc = make_quote([line("_QS-Q-A", 3, 100), line("_QS-Q-B", 2, 50)], **fields)
		return doc, send_quote(doc.name).token

	def as_guest(self, fn, *args, **kwargs):
		with self.set_user("Guest"):
			return fn(*args, **kwargs)

	def jobs(self, method):
		return [c for c in self.enqueue.call_args_list if c.args and c.args[0].endswith(method)]


class TestGetQuoteView(QuoteViewTestCase):
	def test_latest_version(self):
		doc, token = self.sent_quote()
		view = self.as_guest(quote_view.get_quote_view, doc.name, token)
		self.assertEqual((view["version"], view["status"], view["can_accept"]), (1, "Price Sent", True))
		self.assertEqual(
			{ln["item_code"]: ln["offered_qty"] for ln in view["lines"]}, {"_QS-Q-A": 3.0, "_QS-Q-B": 2.0}
		)
		self.assertEqual(view["totals"]["total_offered"], 400.0)
		self.assertNotIn("token_hash", str(view))

	def test_outdated_version(self):
		doc, token = self.sent_quote()
		send_quote(doc.name)
		view = self.as_guest(quote_view.get_quote_view, doc.name, token)
		self.assertTrue(view["outdated"])
		self.assertEqual(view["current_version"], 2)
		self.assertNotIn("lines", view)
		self.assertEqual(view["url"], versions.login_url(doc.name))  # CONTRACTS §10: sign-in link
		self.assertTrue(view["url"].endswith(f"/account?next=/q/{doc.name}"))

	def test_expired_version(self):
		doc = make_quote([line("_QS-Q-E", 1, 10)])
		with self.freeze_time(DAY):
			token = send_quote(doc.name).token
		with self.freeze_time("2026-06-25 23:59:00"):  # valid_till 2026-06-25: still open that day
			self.assertEqual(self.as_guest(quote_view.get_quote_view, doc.name, token)["version"], 1)
		with self.freeze_time("2026-06-26 00:00:01"):
			self.assertTrue(self.as_guest(quote_view.get_quote_view, doc.name, token)["outdated"])

	def test_wrong_token_denied(self):
		doc, _token = self.sent_quote()
		_other, other_token = self.sent_quote()
		for name, token in (
			(doc.name, "not-a-token"),
			(doc.name, None),
			(doc.name, other_token),
			("RFQ-99999", other_token),
		):
			with self.subTest(name=name, token=token), self.assertRaises(frappe.PermissionError):
				self.as_guest(quote_view.get_quote_view, name, token)


class TestRequestChanges(QuoteViewTestCase):
	def test_change_qty_remove_add(self):
		doc, token = self.sent_quote()
		result = self.as_guest(
			quote_view.request_changes,
			doc.name,
			token,
			[{"item_code": "_QS-Q-A", "qty": 5}, {"item_code": "_QS-Q-NEW", "qty": 2}],
		)
		doc.reload()
		self.assertEqual((doc.status, doc.current_version), ("Changes Requested", 2))
		v2 = max(doc.versions, key=lambda v: v.version)
		self.assertEqual(v2.created_by_type, "Buyer")
		rows = {r.item_code: r for r in doc.items}
		self.assertEqual(
			{c: (r.requested_qty, r.change_flag) for c, r in rows.items()},
			{"_QS-Q-A": (5.0, "Qty changed"), "_QS-Q-B": (2.0, "Removed"), "_QS-Q-NEW": (2.0, "Added")},
		)
		self.assertEqual(rows["_QS-Q-NEW"].listed_rate, 40.0)  # starting price snapshot, not buyer input
		self.assertEqual(rows["_QS-Q-A"].offered_rate, 100.0)

		new_token = token_of(result["url"])
		self.assertTrue(self.as_guest(quote_view.get_quote_view, doc.name, token)["outdated"])
		self.assertEqual(self.as_guest(quote_view.get_quote_view, doc.name, new_token)["version"], 2)
		(job,) = self.jobs("whatsapp.send_message")  # send_quote patches its own enqueue for price_sent
		self.assertEqual((job.kwargs["event"], job.kwargs["version"]), ("changes_requested", 2))

	def test_any_price_in_input_rejected(self):
		doc, token = self.sent_quote()
		for item in (
			{"item_code": "_QS-Q-A", "qty": 3, "rate": 1},
			{"item_code": "_QS-Q-A", "qty": 3, "offered_rate": 1},
			{"item_code": "_QS-Q-A", "qty": 3, "listed_rate": 1},
			{"item_code": "_QS-Q-A", "qty": 3, "price_list_rate": 1},
		):
			with self.subTest(item=item), self.assertRaises(frappe.ValidationError):
				self.as_guest(quote_view.request_changes, doc.name, token, [item])
		doc.reload()
		self.assertEqual((doc.status, doc.current_version), ("Price Sent", 1))

	def test_unpublished_or_bad_qty_rejected(self):
		doc, token = self.sent_quote()
		for items in (
			[{"item_code": "_QS-Q-A", "qty": 3}, {"item_code": "_QS-Q-HIDDEN", "qty": 1}],
			[{"item_code": "_QS-Q-A", "qty": 3}, {"item_code": "_QS no such item", "qty": 1}],
			[{"item_code": "_QS-Q-NEW", "qty": 0}],
			[{"item_code": "_QS-Q-NEW", "qty": -2}],
			[],
		):
			with self.subTest(items=items), self.assertRaises(frappe.ValidationError):
				self.as_guest(quote_view.request_changes, doc.name, token, items)
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "current_version"), 1)

	def test_old_token_cannot_request_changes(self):
		doc, token = self.sent_quote()
		send_quote(doc.name)
		result = self.as_guest(
			quote_view.request_changes, doc.name, token, [{"item_code": "_QS-Q-A", "qty": 1}]
		)
		self.assertTrue(result["outdated"])
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")


class TestAcceptWebsite(QuoteViewTestCase):
	def test_accept_latest(self):
		doc, token = self.sent_quote()
		self.assertEqual(self.as_guest(quote_view.accept_quote, doc.name, token), {"accepted": True})
		doc.reload()
		v1 = doc.versions[0]
		self.assertEqual((doc.status, v1.accepted_via), ("Accepted", "Website"))
		self.assertTrue(v1.accepted_on)
		(job,) = self.jobs("orders.create_order")
		self.assertEqual(job.kwargs["job_id"], f"qs-order-{doc.name}")
		self.assertTrue(job.kwargs["enqueue_after_commit"])
		self.assertEqual((job.kwargs["enquiry"], job.kwargs["version"]), (doc.name, 1))

	def test_expired_rejected(self):
		doc = make_quote([line("_QS-Q-X", 1, 10)])
		with self.freeze_time(DAY):
			token = send_quote(doc.name).token
		with self.freeze_time("2026-06-27 09:00:00"):
			self.assertTrue(self.as_guest(quote_view.accept_quote, doc.name, token)["outdated"])
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")
		self.assertFalse(self.jobs("orders.create_order"))

	def test_old_version_rejected(self):
		doc, token = self.sent_quote()
		send_quote(doc.name)
		self.assertTrue(self.as_guest(quote_view.accept_quote, doc.name, token)["outdated"])
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")

	def test_buyer_version_not_acceptable(self):
		doc, token = self.sent_quote()
		url = self.as_guest(
			quote_view.request_changes, doc.name, token, [{"item_code": "_QS-Q-A", "qty": 1}]
		)["url"]
		with self.assertRaises(frappe.ValidationError):
			self.as_guest(quote_view.accept_quote, doc.name, token_of(url))
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Changes Requested")

	def test_wrong_token_denied(self):
		doc, _token = self.sent_quote()
		with self.assertRaises(frappe.PermissionError):
			self.as_guest(quote_view.accept_quote, doc.name, "forged")

	def test_double_accept_one_sales_order(self):
		doc, token = self.sent_quote()
		self.as_guest(quote_view.accept_quote, doc.name, token)
		self.assertEqual(self.as_guest(quote_view.accept_quote, doc.name, token), {"accepted": True})
		self.assertEqual(len(self.jobs("orders.create_order")), 1)
		with self.set_user("Guest"):
			first = orders.create_order(doc.name, 1)
		second = orders.create_order(doc.name, 1)  # duplicate job run
		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count("Sales Order", {"qs_enquiry": doc.name}), 1)


class TestAcceptWhatsApp(QuoteViewTestCase):
	"""Quick reply "Accept quote" correlated through reply_to_message_id → QS message log (CONTRACTS §4.3)."""

	def outgoing(self, doc, version, wamid):
		whatsapp.log_message(
			doc.name, version, "price_sent", "Outgoing", frappe._dict(message_id=wamid, name=None)
		)

	def reply(self, to_wamid, sender, label="Accept quote"):
		msg = frappe.get_doc(
			{
				"doctype": "WhatsApp Message",
				"type": "Incoming",
				"from": sender,
				"message": label,
				"content_type": "button",
				"message_id": f"wamid.IN-{frappe.generate_hash(length=8)}",
				"reply_to_message_id": to_wamid,
			}
		)
		msg.db_insert()  # the webhook path itself is covered by test_whatsapp
		whatsapp.handle_reply(msg.name)
		return msg

	def test_accept_from_registered_number(self):
		doc, _token = self.sent_quote()
		self.outgoing(doc, 1, "wamid.OUT-1")
		self.reply("wamid.OUT-1", DEFAULT_MOBILE.lstrip("+"))
		doc.reload()
		self.assertEqual((doc.status, doc.versions[0].accepted_via), ("Accepted", "WhatsApp"))
		self.assertEqual(len(self.jobs("orders.create_order")), 1)

	def test_other_number_rejected(self):
		doc, _token = self.sent_quote()
		self.outgoing(doc, 1, "wamid.OUT-2")
		self.reply("wamid.OUT-2", "919811111111")
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")
		self.assertFalse(self.jobs("orders.create_order"))

	def test_duplicate_reply_one_order(self):
		doc, _token = self.sent_quote()
		self.outgoing(doc, 1, "wamid.OUT-3")
		first = self.reply("wamid.OUT-3", DEFAULT_MOBILE.lstrip("+"))
		whatsapp.handle_reply(first.name)  # same Meta delivery processed twice
		self.reply("wamid.OUT-3", DEFAULT_MOBILE.lstrip("+"))  # second tap
		self.assertEqual(len(self.jobs("orders.create_order")), 1)
		orders.create_order(doc.name, 1)
		orders.create_order(doc.name, 1)
		self.assertEqual(frappe.db.count("Sales Order", {"qs_enquiry": doc.name}), 1)

	def test_old_version_gets_version_outdated(self):
		doc, _token = self.sent_quote()
		self.outgoing(doc, 1, "wamid.OUT-4")
		send_quote(doc.name)
		self.reply("wamid.OUT-4", DEFAULT_MOBILE.lstrip("+"))
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "status"), "Price Sent")
		outdated = [c for c in self.jobs("whatsapp.send_message") if c.kwargs["event"] == "version_outdated"]
		self.assertEqual(len(outdated), 1)
		self.assertEqual(outdated[0].kwargs["version"], 1)

	def test_version_outdated_carries_new_link(self):
		"""TESTING §3 "version_outdated reply with the new link"; CONTRACTS §10: url = sign-in link."""
		doc, _token = self.sent_quote()
		self.outgoing(doc, 1, "wamid.OUT-5")
		send_quote(doc.name)
		self.reply("wamid.OUT-5", DEFAULT_MOBILE.lstrip("+"))
		(job,) = [c for c in self.jobs("whatsapp.send_message") if c.kwargs["event"] == "version_outdated"]

		link_wa_templates("version_outdated")
		with patch(WA_POST, return_value={"messages": [{"id": "wamid.TEST-OUTDATED"}]}):
			whatsapp.send_message(**{k: job.kwargs[k] for k in ("enquiry", "event", "version", "url")})
		wa_name = frappe.db.get_value(
			"QS Enquiry Message",
			{"parent": doc.name, "event": "version_outdated", "direction": "Outgoing"},
			"whatsapp_message",
		)
		params = json.loads(frappe.db.get_value("WhatsApp Message", wa_name, "body_param"))
		self.assertEqual(params["url"], versions.login_url(doc.name))
		self.assertTrue(params["url"].endswith(f"/account?next=/q/{doc.name}"))
		self.assertEqual((params["version"], params["current_version"]), ("1", "2"))


class TestDownloadQuote(QuoteViewTestCase):
	def download(self, name, token, fmt):
		frappe.local.response = frappe._dict()
		self.as_guest(quote_view.download_quote, name, token, fmt)
		return frappe.local.response

	def test_xlsx(self):
		from openpyxl import load_workbook

		doc, token = self.sent_quote()
		response = self.download(doc.name, token, "xlsx")
		self.assertEqual((response.type, response.filename), ("download", f"{doc.name}-v1.xlsx"))
		rows = list(load_workbook(io.BytesIO(response.filecontent)).active.values)
		self.assertEqual([r[0] for r in rows[1:-1]], ["_QS-Q-A", "_QS-Q-B"])
		self.assertEqual(rows[-1][6], 400)

	def test_pdf(self):
		doc, token = self.sent_quote()
		try:
			response = self.download(doc.name, token, "pdf")
		except Exception as e:
			if (
				"wkhtmltopdf" in str(e).lower()
				or "ContentNotFoundError" in repr(e)
				or "HostNotFound" in str(e)
			):
				self.skipTest(f"wkhtmltopdf cannot reach site assets without the web server: {e}")
			raise
		self.assertEqual(response.filename, f"{doc.name}-v1.pdf")
		self.assertTrue(response.filecontent.startswith(b"%PDF"))

	def test_pdf_serves_stored_file(self):
		"""CONTRACTS §10: the PDF already rendered for the WhatsApp message is served as is."""
		from pypdf import PdfWriter

		buffer = io.BytesIO()
		writer = PdfWriter()
		writer.add_blank_page(width=72, height=72)
		writer.add_metadata({"/Title": "stored quote"})
		writer.write(buffer)
		stored = buffer.getvalue()
		doc, token = self.sent_quote()
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{doc.name}-v1-{frappe.generate_hash(length=16)}.pdf",
				"attached_to_doctype": "QS Enquiry",
				"attached_to_name": doc.name,
				"is_private": 0,
				"content": stored,
			}
		).insert(ignore_permissions=True)
		with patch.object(quote_view, "render_pdf", side_effect=AssertionError("re-rendered")):
			response = self.download(doc.name, token, "pdf")
		self.assertEqual(response.filecontent, stored)

	def test_outdated_or_wrong_token_denied(self):
		doc, token = self.sent_quote()
		with self.assertRaises(frappe.PermissionError):
			self.download(doc.name, "forged", "xlsx")
		send_quote(doc.name)
		with self.assertRaises(frappe.ValidationError):
			self.download(doc.name, token, "xlsx")
