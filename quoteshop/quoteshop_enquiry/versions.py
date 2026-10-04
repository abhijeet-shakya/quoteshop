"""Phase 5: desk pricing actions and quote versions (CONTRACTS §7.2)."""

import json
from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, get_url, now_datetime, nowdate

from quoteshop.quoteshop_enquiry import crm, whatsapp
from quoteshop.quoteshop_enquiry.diff import diff_lines
from quoteshop.quoteshop_enquiry.tokens import new_token

EDITABLE_STATUSES = ("Requested", "Changes Requested", "Price Sent", "Expired")
LINE_FIELDS = (
	"item_code",
	"item_name",
	"uom",
	"requested_qty",
	"offered_qty",
	"listed_rate",
	"offered_rate",
	"amount",
	"availability",
	"availability_note",
	"lead_time_days",
	"alternative_item",
	"change_flag",
)
TOTAL_FIELDS = (
	"total_listed",
	"total_offered",
	"total_saved",
	"saved_pct",
	"line_count",
	"unit_count",
	"available_count",
	"partial_count",
	"not_available_count",
	"valid_till",
)
FLAG_LABELS = {
	"Added": "{0} added",
	"Removed": "{0} removed",
	"Price changed": "{0} price changed",
	"Qty changed": "{0} qty changed",
	"Alternative": "{0} alternative",
}


@frappe.whitelist(methods=["POST"])
def apply_discount(
	name: str, percent: float, scope: str, rows: list | str | None = None, item_group: str | None = None
) -> dict:
	"""offered_rate = listed_rate × (1 − percent/100) on all / selected / one category's lines."""
	doc = _get_for_edit(name)
	percent = flt(percent)
	if not 0 <= percent < 100:
		frappe.throw(_("Discount must be at least 0% and below 100%."))
	if scope == "all":
		targets = list(doc.items)
	elif scope == "selected":
		targets = _rows(doc, rows)
	elif scope == "category":
		targets = _rows_in_group(doc, item_group)
	else:
		frappe.throw(_("Scope must be all, selected or category."))

	precision = doc.precision("offered_rate", "items")
	updated = 0
	for row in targets:
		if flt(row.listed_rate) > 0:
			row.offered_rate = flt(row.listed_rate * (1 - percent / 100), precision)
			updated += 1
	doc.save()
	return {"updated": updated}


@frappe.whitelist(methods=["POST"])
def set_availability(
	name: str,
	rows: list | str,
	availability: str,
	note: str | None = None,
	lead_time_days: int | None = None,
	offered_qty: float | None = None,
) -> dict:
	doc = _get_for_edit(name)
	options = frappe.get_meta("QS Enquiry Item").get_options("availability").split("\n")
	if availability not in options:
		frappe.throw(_("Invalid availability."))
	if (
		lead_time_days is not None
		and cint(lead_time_days) < 0
		or offered_qty is not None
		and flt(offered_qty) < 0
	):
		frappe.throw(_("Lead time and quantity cannot be negative."))
	targets = _rows(doc, rows)
	for row in targets:
		row.availability = availability
		if note is not None:
			row.availability_note = (note or "").strip()[:140]
		if lead_time_days is not None:
			row.lead_time_days = cint(lead_time_days)
		if offered_qty is not None:
			row.offered_qty = flt(offered_qty)
	doc.save()
	return {"updated": len(targets)}


@frappe.whitelist(methods=["POST"])
def copy_from_last_order(name: str) -> dict:
	"""Offered rates from the buyer's last submitted Sales Order lines."""
	from quoteshop.quoteshop_enquiry.api import customer_of_contact

	doc = _get_for_edit(name)
	customer = doc.customer or (doc.contact and customer_of_contact(doc.contact))
	order = customer and frappe.get_all(
		"Sales Order",
		filters={"customer": customer, "docstatus": 1},
		order_by="transaction_date desc, creation desc",
		limit=1,
		pluck="name",
	)
	if not order:
		frappe.throw(_("This buyer has no submitted Sales Order yet."))
	rates = {
		row.item_code: row.rate
		for row in frappe.get_all(
			"Sales Order Item", filters={"parent": order[0]}, fields=["item_code", "rate"], order_by="idx asc"
		)
	}
	updated = 0
	for row in doc.items:
		if row.item_code in rates:
			row.offered_rate = rates[row.item_code]
			updated += 1
	doc.save()
	return {"updated": updated, "sales_order": order[0]}


@frappe.whitelist(methods=["POST"])
def send_price(name: str) -> dict:
	"""New Sales version, status Price Sent, PDF + price_sent WhatsApp enqueued."""
	doc = _get_for_edit(name)
	doc.status = "Price Sent"
	raw = create_version(doc, "Sales")
	doc.save()
	crm.sync_deal_status(doc)
	url = quote_url(doc.name, raw)
	whatsapp.queue_message(doc.name, "price_sent", doc.current_version, url=url)
	return {"version": doc.current_version, "url": url}


@frappe.whitelist(methods=["POST"])
def mark_lost(name: str, reason: str) -> None:
	doc = frappe.get_doc("QS Enquiry", name)
	doc.check_permission("write")
	if doc.status in ("Accepted", "Lost"):
		frappe.throw(_("Enquiry is already {0}.").format(_(doc.status)))
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Please enter a reason."))
	doc.status = "Lost"
	doc.lost_reason = reason[:1000]
	doc.save()
	crm.sync_deal_status(doc)


def create_version(doc, by: str) -> str:
	"""Snapshot the current lines as version N+1 (diff flags, new token, validity reset). Returns the raw token."""
	if by not in ("Buyer", "Sales"):
		frappe.throw(_("Version must be by Buyer or Sales."))
	previous = latest_version(doc)
	prev_lines = snapshot(previous)["lines"] if previous else []
	prev_removed = {line["item_code"] for line in prev_lines if line.get("change_flag") == "Removed"}

	# a line shows as Removed in one version only, then drops out
	doc.set(
		"items", [r for r in doc.items if not (r.change_flag == "Removed" and r.item_code in prev_removed)]
	)
	active = [r for r in doc.items if r.change_flag != "Removed"]
	flags = (
		diff_lines(
			[line for line in prev_lines if line.get("change_flag") != "Removed"],
			[r.as_dict() for r in active],
			rate_precision=doc.precision("offered_rate", "items") or 2,
			qty_precision=doc.precision("offered_qty", "items") or 3,
		)
		if previous
		else {}
	)
	for row in active:
		row.change_flag = flags.get(row.item_code, "")

	days = cint(frappe.get_cached_doc("QS Enquiry Settings").quote_validity_days) or 15
	doc.valid_till = add_days(nowdate(), days)
	doc.set_totals()
	raw, token_hash = new_token()
	doc.current_version = cint(doc.current_version) + 1
	counts = Counter(flag for flag in flags.values() if flag)
	doc.append(
		"versions",
		{
			"version": doc.current_version,
			"created_by_type": by,
			"created_by": frappe.session.user if frappe.session.user != "Guest" else doc.buyer_name,
			"created_on": now_datetime(),
			"summary": ", ".join(_(FLAG_LABELS[flag]).format(n) for flag, n in counts.items())
			or (_("First quote") if not previous else _("No changes")),
			"snapshot": json.dumps(
				{
					"lines": [{f: row.get(f) for f in LINE_FIELDS} for row in doc.items],
					"totals": {f: doc.get(f) for f in TOTAL_FIELDS},
				},
				default=str,
			),
			"token_hash": token_hash,
			"token_expires": get_datetime(add_days(doc.valid_till, 1)),  # valid through valid_till
		},
	)
	return raw


def latest_version(doc):
	return max(doc.versions, key=lambda row: row.version, default=None)


def snapshot(version_row) -> dict:
	return (
		json.loads(version_row.snapshot)
		if version_row and version_row.snapshot
		else {"lines": [], "totals": {}}
	)


def is_open(doc, version_row) -> bool:
	"""Latest version whose token has not expired."""
	return (
		version_row is not None
		and version_row is latest_version(doc)
		and (not version_row.token_expires or now_datetime() < get_datetime(version_row.token_expires))
	)


def set_items_from_version(doc, version_row) -> None:
	"""Reset the lines to what the buyer saw in `version_row` (drops unsent desk edits)."""
	data = snapshot(version_row)
	doc.set("items", [{f: line.get(f) for f in LINE_FIELDS} for line in data["lines"]])


def doc_at_version(doc, version_row):
	"""In-memory copy of the enquiry as sent in `version_row` (for print/PDF)."""
	copy = frappe.get_doc(doc.as_dict())
	set_items_from_version(copy, version_row)
	copy.update({k: v for k, v in snapshot(version_row)["totals"].items()})
	copy.current_version = version_row.version
	return copy


def quote_url(name: str, raw_token: str) -> str:
	return get_url(f"/q/{name}?t={raw_token}")


def _get_for_edit(name: str):
	doc = frappe.get_doc("QS Enquiry", name)
	doc.check_permission("write")
	if doc.status not in EDITABLE_STATUSES:
		frappe.throw(_("A {0} enquiry cannot be priced.").format(_(doc.status)))
	return doc


def _rows(doc, rows) -> list:
	names = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(names, list) or not names:
		frappe.throw(_("Select at least one line."))
	targets = [row for row in doc.items if row.name in set(names)]
	if len(targets) != len(set(names)):
		frappe.throw(_("Some selected lines do not belong to this enquiry."))
	return targets


def _rows_in_group(doc, item_group: str | None) -> list:
	bounds = item_group and frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not bounds:
		frappe.throw(_("Select a valid item group."))
	groups = set(
		frappe.get_all(
			"Item Group", filters={"lft": (">=", bounds.lft), "rgt": ("<=", bounds.rgt)}, pluck="name"
		)
	)
	codes = [row.item_code for row in doc.items]
	in_group = set(
		frappe.get_all(
			"Item", filters={"name": ("in", codes), "item_group": ("in", list(groups))}, pluck="name"
		)
	)
	return [row for row in doc.items if row.item_code in in_group]
