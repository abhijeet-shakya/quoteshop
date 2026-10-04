"""Phase 3-4 WhatsApp (CONTRACTS §4.1-4.5, §7.2, §9.1; TEST_MATRIX QTE-26, CRM-08..11, NFR-15).

Outgoing: Meta mocked at frappe_whatsapp's make_post_request; one POST per (enquiry, version, event) with the
body params in order; empty template → no send + Error Log. Incoming: Meta payload through
frappe_whatsapp.utils.webhook.post(); quick reply matched via reply_to_message_id → QS Enquiry Message;
sender must be the enquiry mobile; duplicates handled once; the hook never raises.
"""

import json
from itertools import count
from unittest.mock import patch

import frappe
from frappe_whatsapp.utils import webhook

from quoteshop.quoteshop_enquiry import whatsapp
from quoteshop.quoteshop_enquiry.tests.factories import (
	WA_POST,
	EnquiryTestCase,
	link_wa_templates,
	make_quote,
	make_store_settings,
	make_user,
	make_wa_template,
	send_quote,
	wa_incoming_payload,
)

MOBILE = "+919811500001"
A, B = "_QS WA-A", "_QS WA-B"
LINES = [
	{"item_code": A, "requested_qty": 2, "listed_rate": 100},
	{"item_code": B, "requested_qty": 3, "listed_rate": 50},
]
SEND_JOB = "quoteshop.quoteshop_enquiry.whatsapp.send_message"
REPLY_JOB = "quoteshop.quoteshop_enquiry.whatsapp.handle_reply"
ORDER_JOB = "quoteshop.quoteshop_enquiry.orders.create_order"


def job_calls(enqueue, method):
	return [c for c in enqueue.call_args_list if c.args and c.args[0] == method]


class BrokenMessage:
	"""A WhatsApp Message whose attribute access fails."""

	@property
	def type(self):
		raise RuntimeError("boom")


class WhatsAppTestCase(EnquiryTestCase):
	def setUp(self):
		super().setUp()
		link_wa_templates(
			"otp",
			"enquiry_received_buyer",
			"enquiry_alert_sales",
			"price_sent",
			"changes_requested",
			"accepted",
		)
		self.ids = count(1)
		patcher = patch(WA_POST, side_effect=self.fake_meta)
		self.post = patcher.start()
		self.addCleanup(patcher.stop)

	def fake_meta(self, *args, **kwargs):
		return {"messages": [{"id": f"wamid.TEST{next(self.ids)}"}]}

	def sent(self):
		"""Meta payloads POSTed so far."""
		return [json.loads(call.kwargs["data"]) for call in self.post.call_args_list]

	@staticmethod
	def body_params(payload):
		body = next(c for c in payload["template"]["components"] if c["type"] == "body")
		return [p["text"] for p in body["parameters"]]

	def log(self, enquiry, **filters):
		return frappe.get_all(
			"QS Enquiry Message",
			filters={"parenttype": "QS Enquiry", "parent": enquiry, **filters},
			fields=["version", "event", "direction", "message_id", "whatsapp_message"],
		)

	def error_logs(self, title_like):
		return frappe.get_all("Error Log", filters={"method": ("like", f"%{title_like}%")}, pluck="name")


class TestOutgoing(WhatsAppTestCase):
	def test_enquiry_received_buyer_once(self):
		"""CRM-08: to the buyer, params buyer_name, ref, items, pcs; logged; second run sends nothing."""
		doc = make_quote(LINES, mobile=MOBILE, deal=True)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		(payload,) = self.sent()
		self.assertEqual(payload["to"], MOBILE.lstrip("+"))
		self.assertEqual(payload["template"]["name"], "_qs_test_enquiry_received_buyer")
		self.assertEqual(self.body_params(payload), ["_QS Test Buyer", doc.name, "2", "5"])
		(row,) = self.log(doc.name)
		self.assertEqual(
			(row.version, row.event, row.direction, row.message_id),
			(0, "enquiry_received_buyer", "Outgoing", "wamid.TEST1"),
		)
		self.assertEqual(
			frappe.db.get_value("WhatsApp Message", row.whatsapp_message, "message_id"), "wamid.TEST1"
		)

	def test_enquiry_alert_sales_once_to_assignee(self):
		"""CRM-09: to the assignee's mobile; params ref, buyer_name, mobile, items, pcs."""
		user = make_user("_qs_wa_sales@example.com", ("Sales User",))
		frappe.db.set_value("User", user, "mobile_no", "+919811599991")
		doc = make_quote(LINES, mobile=MOBILE, deal=True, assigned_to=user)
		whatsapp.send_message(doc.name, "enquiry_alert_sales", 0)
		whatsapp.send_message(doc.name, "enquiry_alert_sales", 0)
		(payload,) = self.sent()
		self.assertEqual(payload["to"], "919811599991")
		self.assertEqual(self.body_params(payload), [doc.name, "_QS Test Buyer", MOBILE, "2", "5"])

	def test_alert_falls_back_to_store_number(self):
		make_store_settings(whatsapp_number="98115 99992")
		doc = make_quote(LINES, mobile=MOBILE)
		whatsapp.send_message(doc.name, "enquiry_alert_sales", 0)
		self.assertEqual([p["to"] for p in self.sent()], ["919811599992"])

	def test_alert_without_any_number_logs_error(self):
		make_store_settings(whatsapp_number=None)
		doc = make_quote(LINES, mobile=MOBILE)
		whatsapp.send_message(doc.name, "enquiry_alert_sales", 0)
		self.assertEqual(self.sent(), [])
		self.assertTrue(self.error_logs("no WhatsApp number for enquiry_alert_sales"))

	def test_template_field_names_set_param_order(self):
		make_wa_template("_qs_test_custom_order", field_names="ref, pcs ,buyer_name")
		frappe.db.set_single_value(
			"QS Enquiry Settings", "enquiry_received_buyer_template", "_qs_test_custom_order-en"
		)
		frappe.clear_document_cache("QS Enquiry Settings")
		doc = make_quote(LINES, mobile=MOBILE)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		self.assertEqual(self.body_params(self.sent()[0]), [doc.name, "5", "_QS Test Buyer"])

	def test_template_empty_no_send_and_error_log(self):
		frappe.db.set_single_value("QS Enquiry Settings", "enquiry_received_buyer_template", None)
		frappe.clear_document_cache("QS Enquiry Settings")
		doc = make_quote(LINES, mobile=MOBILE)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		self.assertEqual(self.sent(), [])
		self.assertEqual(self.log(doc.name), [])
		logs = frappe.get_all(
			"Error Log",
			filters={"method": ("like", "%no WhatsApp template for enquiry_received_buyer%")},
			fields=["reference_doctype", "reference_name"],
		)
		self.assertIn(frappe._dict(reference_doctype="QS Enquiry", reference_name=doc.name), logs)

	def test_queue_message_args(self):
		"""Jobs after commit, job_id per (enquiry, version, event), deduplicated."""
		doc = make_quote(LINES, mobile=MOBILE)
		with patch("frappe.enqueue") as enqueue:
			whatsapp.queue_message(doc.name, "enquiry_received_buyer")
			whatsapp.queue_message(doc.name, "enquiry_received_buyer", 0)
		self.assertEqual(enqueue.call_count, 2)
		for call in enqueue.call_args_list:
			self.assertEqual(call.args[0], SEND_JOB)
			self.assertEqual(call.kwargs["job_id"], f"qs-wa-{doc.name}-0-enquiry_received_buyer")
			self.assertIs(call.kwargs["enqueue_after_commit"], True)
			self.assertIs(call.kwargs["deduplicate"], True)
			self.assertEqual(
				(call.kwargs["enquiry"], call.kwargs["event"], call.kwargs["version"]),
				(doc.name, "enquiry_received_buyer", 0),
			)

	def test_duplicate_event_single_message(self):
		"""CRM-10: per-version dedupe; a new version of the same event is a new message."""
		doc = make_quote(LINES, mobile=MOBILE)
		for _ in range(3):
			whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 1)
		self.assertEqual(len(self.sent()), 2)
		self.assertEqual(sorted(r.version for r in self.log(doc.name)), [0, 1])

	def test_otp_template_once_with_variables(self):
		"""QTE-26: OTP template to the number with the code as the only body param."""
		whatsapp.send_otp_message(MOBILE, "042137")
		(payload,) = self.sent()
		self.assertEqual((payload["to"], payload["template"]["name"]), (MOBILE.lstrip("+"), "_qs_test_otp"))
		self.assertEqual(self.body_params(payload), ["042137"])

	def test_can_send(self):
		self.assertTrue(whatsapp.can_send("otp"))
		self.assertFalse(whatsapp.can_send("version_outdated"))  # template not linked
		frappe.db.set_value("WhatsApp Account", {"is_default_outgoing": 1}, "is_default_outgoing", 0)
		self.assertFalse(whatsapp.can_send("otp"))

	def test_deal_reference_on_message(self):
		doc = make_quote(LINES, mobile=MOBILE, deal=True)
		whatsapp.send_message(doc.name, "enquiry_received_buyer", 0)
		(row,) = self.log(doc.name)
		self.assertEqual(frappe.db.get_value("WhatsApp Message", row.whatsapp_message, "type"), "Outgoing")


class TestIncomingQuickReply(WhatsAppTestCase):
	"""CRM-11: Meta webhook → WhatsApp Message → QS hook → handle_reply job."""

	def setUp(self):
		super().setUp()
		self.doc = make_quote(LINES, mobile=MOBILE, deal=True)
		self.quote = send_quote(self.doc.name)  # v1, Price Sent
		whatsapp.send_message(self.doc.name, "price_sent", 1, url=self.quote.url)
		(row,) = self.log(self.doc.name, event="price_sent")
		self.price_sent_id = row.message_id

	def deliver(
		self,
		label="Accept quote",
		sender=None,
		reply_to=None,
		message_id="wamid.IN1",
		kind="button",
	):
		"""Run the webhook; returns the frappe.enqueue mock (hook jobs are not run)."""
		sender = sender or MOBILE.lstrip("+")
		frappe.local.form_dict = frappe._dict(
			wa_incoming_payload(sender, reply_to or self.price_sent_id, message_id, label, kind)
		)
		try:
			with patch("frappe.enqueue") as enqueue:
				webhook.post()
		finally:
			frappe.local.form_dict = frappe._dict()
		return enqueue

	def reply_jobs(self, enqueue):
		return [c for c in enqueue.call_args_list if c.args and c.args[0] == REPLY_JOB]

	def run_reply(self, enqueue):
		"""Run the queued handle_reply job(s); returns the frappe.enqueue mock of the job run."""
		with patch("frappe.enqueue") as job_enqueue:
			for call in self.reply_jobs(enqueue):
				whatsapp.handle_reply(message=call.kwargs["message"])
		return job_enqueue

	def status(self):
		return frappe.db.get_value("QS Enquiry", self.doc.name, "status")

	def test_matched_via_reply_to_message_id(self):
		enqueue = self.deliver()
		(job,) = self.reply_jobs(enqueue)
		self.assertEqual(job.kwargs["job_id"], "qs-wa-in-wamid.IN1")
		self.assertIs(job.kwargs["enqueue_after_commit"], True)
		self.assertEqual(
			frappe.db.get_value("WhatsApp Message", job.kwargs["message"], "reply_to_message_id"),
			self.price_sent_id,
		)

	def test_button_label_maps_to_accept(self):
		jobs = self.run_reply(self.deliver("Accept quote"))
		self.assertEqual(self.status(), "Accepted")
		version = frappe.get_all(
			"QS Enquiry Version",
			filters={"parent": self.doc.name, "version": 1},
			fields=["accepted_via", "accepted_on"],
		)[0]
		self.assertEqual(version.accepted_via, "WhatsApp")
		self.assertTrue(version.accepted_on)
		orders = job_calls(jobs, ORDER_JOB)
		self.assertEqual([c.kwargs["job_id"] for c in orders], [f"qs-order-{self.doc.name}"])
		self.assertEqual(
			[(r.direction, r.message_id) for r in self.log(self.doc.name, direction="Incoming")],
			[("Incoming", "wamid.IN1")],
		)

	def test_button_label_maps_to_request_changes(self):
		jobs = self.run_reply(self.deliver("Request changes"))
		self.assertEqual(self.status(), "Changes Requested")
		self.assertEqual(frappe.db.get_value("CRM Deal", self.doc.crm_deal, "status"), "Changes Requested")
		events = [c.kwargs.get("event") for c in job_calls(jobs, SEND_JOB)]
		self.assertEqual(events, ["changes_requested"])
		self.assertEqual(
			len(self.log(self.doc.name, direction="Incoming")), 1
		)  # reply kept in the message log

	def test_unknown_label_logged_no_action(self):
		self.run_reply(self.deliver("Call me"))
		self.assertEqual(self.status(), "Price Sent")

	def test_sender_must_match_enquiry_mobile(self):
		jobs = self.run_reply(self.deliver(sender="919811599999"))
		self.assertEqual(self.status(), "Price Sent")
		self.assertEqual(self.log(self.doc.name, direction="Incoming"), [])
		self.assertEqual(job_calls(jobs, ORDER_JOB), [])
		self.assertTrue(self.error_logs("unregistered number"))

	def test_duplicate_delivery_handled_once(self):
		first = self.deliver(message_id="wamid.DUP")
		second = self.deliver(message_id="wamid.DUP")
		jobs = self.run_reply(first)
		jobs_again = self.run_reply(second)
		self.assertEqual(self.status(), "Accepted")
		self.assertEqual(len(self.log(self.doc.name, direction="Incoming")), 1)
		self.assertEqual(len(job_calls(jobs, ORDER_JOB) + job_calls(jobs_again, ORDER_JOB)), 1)

	def test_unknown_reply_to_ignored_without_raising(self):
		self.assertEqual(self.reply_jobs(self.deliver(reply_to="wamid.NOT-OURS")), [])
		self.assertEqual(self.status(), "Price Sent")

	def test_plain_text_reply_ignored(self):
		self.assertEqual(self.reply_jobs(self.deliver("Accept quote", kind="text")), [])

	def test_outgoing_message_never_queues_reply(self):
		with patch("frappe.enqueue") as enqueue:
			whatsapp.send_message(self.doc.name, "accepted", 1)
		self.assertEqual(self.reply_jobs(enqueue), [])

	def test_malformed_message_ignored_without_raising(self):
		"""The after_insert hook never raises (an error would roll back frappe_whatsapp's insert)."""
		with patch("frappe.enqueue") as enqueue:
			whatsapp.on_whatsapp_message(BrokenMessage())
			whatsapp.on_whatsapp_message(frappe._dict())  # no fields at all
		enqueue.assert_not_called()
		self.assertTrue(self.error_logs("could not queue WhatsApp reply"))

	def test_handle_reply_for_missing_message_is_noop(self):
		whatsapp.handle_reply(message="_QS no such message")
		self.assertEqual(self.status(), "Price Sent")
