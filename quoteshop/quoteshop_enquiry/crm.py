"""CRM Deal per enquiry (CONTRACTS §3)."""

import frappe
from frappe import _


def create_deal(enquiry_doc) -> str:
	"""Insert the CRM Deal for a new enquiry; store `crm_deal` and the resolved assignee on the enquiry."""
	deal = frappe.new_doc("CRM Deal")
	deal.update(
		{
			"contacts": [{"contact": enquiry_doc.contact, "is_primary": 1}],
			"qs_enquiry": enquiry_doc.name,
			"qs_buyer_type": enquiry_doc.buyer_type,
			"qs_version": enquiry_doc.current_version,
			"deal_value": enquiry_doc.total_offered,
		}
	)
	if status := deal_status(enquiry_doc.status):
		deal.status = status
	if enquiry_doc.assigned_to:  # only when QS resolved someone, else the Assignment Rule assigns (§3.3)
		deal.deal_owner = enquiry_doc.assigned_to
	deal.insert(ignore_permissions=True)

	assignee = frappe.db.get_value("CRM Deal", deal.name, "deal_owner") or next(
		iter(frappe.parse_json(frappe.db.get_value("CRM Deal", deal.name, "_assign") or "[]")), None
	)
	enquiry_doc.db_set({"crm_deal": deal.name, "assigned_to": assignee or enquiry_doc.assigned_to})
	return deal.name


def sync_deal_status(enquiry_doc) -> None:
	"""Mirror the enquiry status/version/value onto its deal. Accepted → Won-type status; Lost → reason "Other"."""
	if not enquiry_doc.crm_deal:
		return
	status = deal_status(enquiry_doc.status)
	if not status:
		return
	deal = frappe.get_doc("CRM Deal", enquiry_doc.crm_deal)
	deal.status = status
	deal.qs_version = enquiry_doc.current_version
	deal.deal_value = enquiry_doc.total_offered
	if frappe.get_cached_value("CRM Deal Status", status, "type") == "Lost":
		deal.lost_reason = "Other"
		deal.lost_notes = enquiry_doc.lost_reason or _("Lost in QuoteShop")
	deal.save(ignore_permissions=True)


def deal_status(qs_status: str) -> str | None:
	if qs_status == "Accepted":
		return frappe.db.get_value("CRM Deal Status", {"type": "Won"})
	if frappe.db.exists("CRM Deal Status", qs_status):
		return qs_status
	return frappe.db.get_value("CRM Deal Status", {"type": "Lost"}) if qs_status == "Lost" else None
