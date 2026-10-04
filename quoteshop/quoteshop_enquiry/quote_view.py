"""Phase 6: buyer view of a quote via its tokenised link (CONTRACTS §7.2)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.rate_limiter import rate_limit
from frappe.utils import flt
from frappe.utils.xlsxutils import make_xlsx

from quoteshop.quoteshop_enquiry import crm, orders, versions, whatsapp
from quoteshop.quoteshop_enquiry.tokens import is_valid_token

VIEW_LINE_FIELDS = (
	"item_code",
	"item_name",
	"colour",
	"uom",
	"requested_qty",
	"offered_qty",
	"offered_rate",
	"amount",
	"availability",
	"availability_note",
	"lead_time_days",
	"alternative_item",
	"change_flag",
)
CHANGEABLE_STATUSES = ("Price Sent", "Changes Requested")


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=300, seconds=3600)
def get_quote_view(name: str, token: str | None = None) -> dict:
	"""Latest version for /q; an old or expired link returns {"outdated": True}."""
	return quote_view(name, token)


def quote_view(name: str, token: str | None = None) -> dict:
	"""get_quote_view without the rate limit (the /q page render must not count against it)."""
	doc, row, current = resolve(name, token)
	if not current:
		return _outdated(doc)
	return view_data(doc, row)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def request_changes(name: str, token: str | None, items: list | str) -> dict:
	"""Buyer changes quantities / colours / removes / adds published items (never prices) → new Buyer version.

	`items` = [{item_code, qty, colour?}]; a line is an (item_code, colour) pair, so a colour switch is a
	Removed line plus an Added line."""
	from quoteshop.quoteshop_enquiry.api import build_lines, parse_json_arg

	doc, row, current = resolve(name, token, for_update=True)
	if not current:
		return _outdated(doc)
	if doc.status not in CHANGEABLE_STATUSES:
		frappe.throw(_("This quote can no longer be changed."))
	items = parse_json_arg(items)

	versions.set_items_from_version(doc, row)
	quoted = {
		(line.item_code, line.colour or ""): {f: line.get(f) for f in versions.LINE_FIELDS}
		| {"change_flag": ""}
		for line in doc.items
	}
	lines = build_lines(items, existing=quoted)
	wanted = {(line["item_code"], line.get("colour") or "") for line in lines}
	lines += [{**line, "change_flag": "Removed"} for key, line in quoted.items() if key not in wanted]
	doc.set("items", lines)
	doc.status = "Changes Requested"
	doc.flags.qs_status_change = True
	raw = versions.create_version(doc, "Buyer")
	doc.save(ignore_permissions=True)
	crm.sync_deal_status(doc)
	whatsapp.queue_message(doc.name, "changes_requested", doc.current_version)
	return {"url": versions.quote_url(doc.name, raw)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def accept_quote(name: str, token: str | None = None) -> dict:
	"""Accept the latest unexpired version; the Sales Order is created by a job."""
	doc, row, current = resolve(name, token, for_update=True)
	if not current:
		return _outdated(doc)
	if not orders.accept(doc, row.version, "Website"):
		frappe.throw(_("This version can't be accepted. Please wait for an updated price."))
	return {"accepted": True}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=3600)
def download_quote(name: str, token: str | None = None, format: str = "pdf") -> None:
	doc, row, current = resolve(name, token)
	if not current:
		frappe.throw(_("This link is outdated. Please open the latest quote."))
	if format == "pdf":
		stored = whatsapp.stored_quote_pdf(doc.name, row.version)
		content = frappe.get_doc("File", stored).get_content(encodings=[]) if stored else render_pdf(doc, row)
		extension = "pdf"
	elif format == "xlsx":
		content, extension = render_xlsx(doc, row), "xlsx"
	else:
		frappe.throw(_("Format must be pdf or xlsx."))
	frappe.local.response.update(
		{"type": "download", "filename": f"{doc.name}-v{row.version}.{extension}", "filecontent": content}
	)


def resolve(name: str, token: str | None, for_update: bool = False) -> tuple[Document, Document, bool]:
	"""(enquiry, version matched by token, is it the open latest version). Invalid link → PermissionError."""
	if not isinstance(name, str) or not frappe.db.exists("QS Enquiry", name):
		_deny()
	doc = frappe.get_doc("QS Enquiry", name, for_update=for_update)
	latest = versions.latest_version(doc)
	if not latest:
		_deny()

	if not token:
		if not _is_buyer(doc):
			_deny()
		row = latest
	else:
		row = next(
			(v for v in doc.versions if isinstance(token, str) and is_valid_token(token, v.token_hash, None)),
			None,
		)
		if not row:
			_deny()
	current = row is latest and (doc.status == "Accepted" or versions.is_open(doc, row))
	return doc, row, current


def view_data(doc: Document, row: Document) -> dict:
	data = versions.snapshot(row)
	totals = data["totals"]
	show_savings = frappe.get_cached_doc("QS Store Settings").show_savings_to_buyer
	lines = [{f: line.get(f) for f in VIEW_LINE_FIELDS} for line in data["lines"]]
	codes = {line["item_code"] for line in lines} | {
		line["alternative_item"] for line in lines if line["alternative_item"]
	}
	items = (
		{
			item.name: item
			for item in frappe.get_all(
				"Item",
				filters={"name": ("in", list(codes))},
				fields=["name", "item_name", "item_group", "qs_route", "qs_published"],
			)
		}
		if codes
		else {}
	)
	thumbs = {}  # (item, photo colour) -> first thumb; colour "" = general photos
	for photo in (
		frappe.get_all(
			"QS Item Photo",
			filters={"parenttype": "Item", "parentfield": "qs_photos", "parent": ("in", list(codes))},
			fields=["parent", "thumb", "image", "colour"],
			order_by="idx asc",
		)
		if codes
		else []
	):
		thumbs.setdefault((photo.parent, photo.colour or ""), photo.thumb or photo.image)
		thumbs.setdefault((photo.parent, None), photo.thumb or photo.image)  # any photo, last resort
	for line, source in zip(lines, data["lines"], strict=True):
		item = items.get(line["item_code"]) or {}
		line["item_group"] = item.get("item_group")
		line["route"] = item.get("qs_route") if item.get("qs_published") else None
		code = line["item_code"]
		line["image"] = (
			thumbs.get((code, line["colour"] or ""))  # the line's colour, else general, else any photo
			or thumbs.get((code, ""))
			or thumbs.get((code, None))
		)
		if line["alternative_item"]:
			line["alternative_item_name"] = (items.get(line["alternative_item"]) or {}).get("item_name")
		if show_savings:
			line["listed_rate"] = source.get("listed_rate")

	return {
		"name": doc.name,
		"status": doc.status,
		"version": row.version,
		"valid_till": totals.get("valid_till"),
		"buyer_name": doc.buyer_name,
		"business_name": doc.business_name,
		"currency": whatsapp._currency(),
		"show_savings": bool(show_savings),
		"totals": {
			k: totals.get(k)
			for k in (
				"total_offered",
				"line_count",
				"unit_count",
				"available_count",
				"partial_count",
				"not_available_count",
			)
		}
		| (
			{k: totals.get(k) for k in ("total_listed", "total_saved", "saved_pct")}
			if show_savings and flt(totals.get("total_saved")) > 0
			else {}
		),
		"lines": lines,
		"history": [
			{
				"version": v.version,
				"created_by_type": v.created_by_type,
				"created_on": v.created_on,
				"summary": v.summary,
				"accepted_on": v.accepted_on,
			}
			for v in sorted(doc.versions, key=lambda v: v.version, reverse=True)
		],
		"can_accept": doc.status == "Price Sent",
		"can_change": doc.status in CHANGEABLE_STATUSES,
		"accepted": doc.status == "Accepted",
		"sales_order": doc.sales_order,
	}


def render_pdf(doc, row) -> bytes:
	print_format = "QS Quote" if frappe.db.exists("Print Format", "QS Quote") else "Standard"
	frappe.flags.ignore_print_permissions = True  # access was checked through the token
	try:
		return frappe.get_print(
			"QS Enquiry",
			doc.name,
			print_format=print_format,
			doc=versions.doc_at_version(doc, row),
			as_pdf=True,
		)
	finally:
		frappe.flags.ignore_print_permissions = False


def render_xlsx(doc, row) -> bytes:
	data = versions.snapshot(row)
	rows = [
		[
			_("Item code"),
			_("Item"),
			_("Colour"),
			_("UOM"),
			_("Requested qty"),
			_("Offered qty"),
			_("Rate"),
			_("Amount"),
			_("Availability"),
			_("Note"),
		]
	]
	for line in data["lines"]:
		if line.get("change_flag") == "Removed":
			continue
		rows.append(
			[
				line["item_code"],
				line.get("item_name"),
				line.get("colour"),
				line.get("uom"),
				line.get("requested_qty"),
				line.get("offered_qty"),
				line.get("offered_rate"),
				line.get("amount"),
				line.get("availability"),
				line.get("availability_note"),
			]
		)
	rows.append(
		[
			"",
			_("Total"),
			"",
			"",
			"",
			data["totals"].get("unit_count"),
			"",
			data["totals"].get("total_offered"),
			"",
			"",
		]
	)
	return make_xlsx(rows, f"{doc.name} v{row.version}"[:31]).getvalue()


def _is_buyer(doc) -> bool:
	user = frappe.session.user
	return (
		user != "Guest" and bool(doc.contact) and frappe.db.get_value("Contact", doc.contact, "user") == user
	)


def _outdated(doc) -> dict:
	# raw tokens are never stored, so the current tokenised link can't be rebuilt; offer sign-in instead
	return {
		"outdated": True,
		"url": versions.login_url(doc.name),
		"current_version": doc.current_version,
		"status": doc.status,
	}


def _deny():
	frappe.throw(_("This quote link is not valid."), frappe.PermissionError)
