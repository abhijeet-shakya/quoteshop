"""WhatsApp messages via frappe_whatsapp (CONTRACTS §4, §9.1-9.2).

Every send runs in a job (frappe_whatsapp POSTs to Meta inside before_insert) and is logged in the
enquiry's QS Enquiry Message table; replies are matched through reply_to_message_id → that log."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import fmt_money, formatdate, get_url, now_datetime

from quoteshop.quoteshop_enquiry.tokens import hash_token

SALES_EVENTS = ("enquiry_alert_sales", "changes_requested")
# Body parameter order per event; a template's "Field Names" (comma separated keys) overrides it.
DEFAULT_PARAMS = {
	"otp": ("otp",),
	"enquiry_received_buyer": ("buyer_name", "ref", "items", "pcs"),
	"enquiry_alert_sales": ("ref", "buyer_name", "mobile", "items", "pcs"),
	"price_sent": (
		"buyer_name",
		"ref",
		"version",
		"items",
		"pcs",
		"your_price",
		"listed",
		"saved",
		"available",
		"partial",
		"not_available",
		"valid_till",
		"url",
	),
	"accepted": ("buyer_name", "ref", "version", "sales_order"),
	"changes_requested": ("ref", "buyer_name", "version", "url"),
	"version_outdated": ("buyer_name", "ref", "version", "current_version", "url"),
}


def can_send(event: str) -> bool:
	return bool(_template_name(event)) and bool(
		frappe.db.get_value("WhatsApp Account", {"is_default_outgoing": 1})
	)


def queue_otp(mobile: str, code: str) -> None:
	# ponytail: the code sits in the RQ payload until the job runs (≤ seconds); Redis is trusted infra
	frappe.enqueue(
		"quoteshop.quoteshop_enquiry.whatsapp.send_otp_message",
		queue="short",
		enqueue_after_commit=True,
		job_id=f"qs-wa-otp-{mobile}-{hash_token(code)[:12]}",
		mobile=mobile,
		code=code,
	)


def send_otp_message(mobile: str, code: str) -> None:
	_insert_message(mobile, "otp", {"otp": code})


def queue_message(
	enquiry: str, event: str, version: int | None = None, url: str | None = None, resend: bool = False
) -> None:
	"""Enqueue `send_message` after commit, at most once per (enquiry, version, event) unless `resend`."""
	if version is None:
		version = frappe.db.get_value("QS Enquiry", enquiry, "current_version") or 0
	frappe.enqueue(
		"quoteshop.quoteshop_enquiry.whatsapp.send_message",
		queue="short",
		enqueue_after_commit=True,
		job_id=f"qs-wa-{enquiry}-{version}-{event}" + ("-resend" if resend else ""),
		deduplicate=True,
		enquiry=enquiry,
		event=event,
		version=version,
		url=url,
		resend=resend,
	)


def send_message(
	enquiry: str, event: str, version: int, url: str | None = None, resend: bool = False
) -> None:
	"""Job: send the event's template once (again if `resend`) and log its message_id. Not retried (§4.1)."""
	if not _template_name(event):
		frappe.log_error(
			title=f"QuoteShop: no WhatsApp template for {event}",
			message=_("Set {0} in QS Enquiry Settings to send this message.").format(f"{event}_template"),
			reference_doctype="QS Enquiry",
			reference_name=enquiry,
		)
		return
	if not resend and frappe.db.exists(
		"QS Enquiry Message",
		{
			"parenttype": "QS Enquiry",
			"parent": enquiry,
			"version": version,
			"event": event,
			"direction": "Outgoing",
		},
	):
		return

	doc = frappe.get_doc("QS Enquiry", enquiry)
	to = _recipient(doc, event)
	if not to:
		frappe.log_error(
			title=f"QuoteShop: no WhatsApp number for {event}",
			message=_("Set the assignee's mobile number or the store WhatsApp number."),
			reference_doctype="QS Enquiry",
			reference_name=enquiry,
		)
		return
	attach = (
		_quote_pdf(doc, version) if event == "price_sent" and _template_header(event) == "DOCUMENT" else None
	)
	message = _insert_message(to, event, _params(doc, event, version, url), attach, doc.crm_deal)
	log_message(enquiry, version, event, "Outgoing", message)


def on_whatsapp_message(doc: Document, method: str | None = None) -> None:
	"""WhatsApp Message after_insert: queue quick-reply handling for replies to QS messages. Never raises."""
	try:
		if (
			doc.type != "Incoming"
			or doc.content_type != "button"
			or not doc.reply_to_message_id
			or not frappe.db.exists("QS Enquiry Message", {"message_id": doc.reply_to_message_id})
		):
			return
		frappe.enqueue(
			"quoteshop.quoteshop_enquiry.whatsapp.handle_reply",
			queue="short",
			enqueue_after_commit=True,
			job_id=f"qs-wa-in-{doc.message_id}",
			deduplicate=True,
			message=doc.name,
		)
	except Exception:
		frappe.log_error(
			title="QuoteShop: could not queue WhatsApp reply", reference_doctype="WhatsApp Message"
		)


def handle_reply(message: str) -> None:
	"""Job: Accept / Request changes quick reply from the registered number (CONTRACTS §4.3, §9.1)."""
	from quoteshop.quoteshop_enquiry import crm, orders, versions

	msg = frappe.db.get_value(
		"WhatsApp Message",
		message,
		["name", "message_id", "reply_to_message_id", "from", "message"],
		as_dict=True,
	)
	sent = msg and frappe.db.get_value(
		"QS Enquiry Message",
		{"parenttype": "QS Enquiry", "message_id": msg.reply_to_message_id, "direction": "Outgoing"},
		["parent", "version", "event"],
		as_dict=True,
	)
	if not sent or frappe.db.exists(
		"QS Enquiry Message", {"message_id": msg.message_id, "direction": "Incoming"}
	):
		return  # not ours, or a duplicate Meta delivery

	doc = frappe.get_doc("QS Enquiry", sent.parent, for_update=True)
	if "+" + (msg["from"] or "").lstrip("+") != doc.mobile:
		frappe.log_error(
			title="QuoteShop: WhatsApp reply from an unregistered number",
			message=f"{msg['from']} replied to {sent.event} v{sent.version}",
			reference_doctype="QS Enquiry",
			reference_name=doc.name,
		)
		return
	log_message(doc.name, sent.version, sent.event, "Incoming", msg)

	action = _action(msg.message)
	if sent.event != "price_sent" or not action:
		return
	if action == "accept":
		if not orders.accept(doc, sent.version, "WhatsApp"):
			queue_message(doc.name, "version_outdated", sent.version)
		return
	latest = versions.latest_version(doc)
	if doc.status == "Price Sent" and latest.version == sent.version and versions.is_open(doc, latest):
		versions.set_items_from_version(doc, latest)
		doc.status = "Changes Requested"
		doc.flags.qs_status_change = True
		doc.save(ignore_permissions=True)
		crm.sync_deal_status(doc)
		queue_message(doc.name, "changes_requested", sent.version)
	elif doc.status != "Changes Requested":
		queue_message(doc.name, "version_outdated", sent.version)


def log_message(enquiry: str, version: int, event: str, direction: str, message) -> None:
	"""Append a QS Enquiry Message row without saving the parent (works on Accepted enquiries)."""
	frappe.get_doc(
		{
			"doctype": "QS Enquiry Message",
			"parenttype": "QS Enquiry",
			"parentfield": "messages",
			"parent": enquiry,
			"idx": frappe.db.count("QS Enquiry Message", {"parenttype": "QS Enquiry", "parent": enquiry}) + 1,
			"version": version,
			"event": event,
			"direction": direction,
			"message_id": message.message_id,
			"whatsapp_message": message.name,
			"sent_on": now_datetime(),
		}
	).db_insert()


def _insert_message(to: str, event: str, params: dict, attach: str | None = None, deal: str | None = None):
	template = frappe.get_cached_doc("WhatsApp Templates", _template_name(event))
	keys = [k.strip() for k in (template.field_names or "").split(",") if k.strip()] or DEFAULT_PARAMS[event]
	message = frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"to": to,
			"content_type": "document" if attach else "text",
			"use_template": 1,
			"template": template.name,
			"body_param": json.dumps({k: str(params.get(k, "")) for k in keys}),
			"attach": attach,
			"reference_doctype": "CRM Deal" if deal else None,
			"reference_name": deal,
		}
	)
	message.insert(ignore_permissions=True)
	return message


def _params(doc, event: str, version: int, url: str | None) -> dict:
	from quoteshop.quoteshop_enquiry import versions

	row = next((v for v in doc.versions if v.version == version), None)
	totals = {**doc.as_dict(), **versions.snapshot(row)["totals"]} if row else doc.as_dict()
	currency = _currency()
	return {
		"buyer_name": doc.buyer_name,
		"ref": doc.name,
		"version": str(version),
		"current_version": str(doc.current_version),
		"mobile": doc.mobile,
		"items": str(totals["line_count"]),
		"pcs": f"{totals['unit_count']:g}",
		"your_price": fmt_money(totals["total_offered"], currency=currency),
		"listed": fmt_money(totals["total_listed"], currency=currency),
		"saved": fmt_money(totals["total_saved"], currency=currency) if totals["total_saved"] > 0 else "-",
		"available": str(totals["available_count"]),
		"partial": str(totals["partial_count"]),
		"not_available": str(totals["not_available_count"]),
		"valid_till": formatdate(totals["valid_till"]) if totals.get("valid_till") else "",
		# sales get the desk link; tokenised buyer links are passed in, else the sign-in link
		"url": url
		or (
			get_url(f"/app/qs-enquiry/{doc.name}") if event in SALES_EVENTS else versions.login_url(doc.name)
		),
		"sales_order": doc.sales_order or "",
	}


def _recipient(doc, event: str) -> str | None:
	if event not in SALES_EVENTS:
		return doc.mobile
	number = (
		doc.assigned_to and frappe.db.get_value("User", doc.assigned_to, "mobile_no")
	) or frappe.get_cached_doc("QS Store Settings").whatsapp_number
	from quoteshop.quoteshop_enquiry.otp import normalize_mobile

	try:
		return normalize_mobile(number) if number else None
	except frappe.ValidationError:
		return None


def stored_quote_pdf(enquiry: str, version: int) -> str | None:
	"""Name of the File already rendered for this version by `_quote_pdf`, if any."""
	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "QS Enquiry",
			"attached_to_name": enquiry,
			"file_name": ("like", f"{enquiry}-v{version}-%.pdf"),
		},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	return files[0] if files else None


def _quote_pdf(doc, version: int) -> str:
	"""Public PDF of the version (unguessable file name, CONTRACTS §5.6), rendered once per version."""
	from quoteshop.quoteshop_enquiry.quote_view import render_pdf

	if stored := stored_quote_pdf(doc.name, version):
		return frappe.db.get_value("File", stored, "file_url")
	row = next(v for v in doc.versions if v.version == version)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}-v{version}-{frappe.generate_hash(length=16)}.pdf",
			"attached_to_doctype": "QS Enquiry",
			"attached_to_name": doc.name,
			"is_private": 0,
			"content": render_pdf(doc, row),
		}
	).insert(ignore_permissions=True)
	return file.file_url


def _action(label: str | None) -> str | None:
	# ponytail: keyword match on the button label ("Accept quote" / "Request changes"); per-label settings if templates get localised
	label = (label or "").casefold()
	if "accept" in label:
		return "accept"
	if "change" in label:
		return "changes"
	return None


def _template_name(event: str) -> str | None:
	return frappe.get_cached_doc("QS Enquiry Settings").get(f"{event}_template")


def _template_header(event: str) -> str | None:
	return frappe.get_cached_value("WhatsApp Templates", _template_name(event), "header_type")


def _currency() -> str:
	company = frappe.get_cached_doc("QS Store Settings").default_company
	return (company and frappe.get_cached_value("Company", company, "default_currency")) or "INR"
