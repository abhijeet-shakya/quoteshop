"""QS deal statuses in Frappe CRM (CONTRACTS §3.2, §9.5). Idempotent; never overwrites admin edits."""

import frappe

STATUSES = (
	("Requested", "Open", "blue"),
	("Price Sent", "Ongoing", "orange"),
	("Changes Requested", "Ongoing", "yellow"),
	("Expired", "On Hold", "gray"),  # not "Lost": Lost-type statuses require a lost_reason
)


def execute() -> None:
	position = max(frappe.get_all("CRM Deal Status", pluck="position") or [0])
	for name, status_type, color in STATUSES:
		if frappe.db.exists("CRM Deal Status", name):
			continue
		position += 1
		frappe.get_doc(
			{
				"doctype": "CRM Deal Status",
				"deal_status": name,
				"type": status_type,
				"color": color,
				"position": position,
			}
		).insert(ignore_permissions=True)
