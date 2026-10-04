"""Idempotent Desk/CRM seeds (CONTRACTS §3.4, §5.7, §9.10): Kanban, saved filters, CRM side panel, CRM form script.

Existing records are left untouched so admin changes survive re-runs.
"""

import json

import frappe
from frappe.desk.doctype.kanban_board.kanban_board import quick_kanban_board

ENQUIRY = "QS Enquiry"
KANBAN = "Enquiry Pipeline"
# SPEC §5 status colours mapped to Kanban's indicator options (no darkgrey there → Gray).
KANBAN_COLOURS = {
	"Draft": "Gray",
	"Requested": "Blue",
	"Price Sent": "Orange",
	"Changes Requested": "Yellow",
	"Accepted": "Green",
	"Lost": "Red",
	"Expired": "Gray",
}
KANBAN_CARD_FIELDS = ["buyer_name", "total_offered", "assigned_to"]

# ponytail: List Filters are static JSON. "Assigned to me" comes from permissions for Sales Users
# (own/assigned only); the exact per-user and "expiring in 3 days" views are workspace shortcuts.
LIST_FILTERS = {
	"Needs pricing": [[ENQUIRY, "status", "in", ["Requested", "Changes Requested"]]],
	"Waiting for buyer": [[ENQUIRY, "status", "=", "Price Sent"]],
}

ENQUIRY_SECTION = {
	"label": "Enquiry",
	"name": "qs_enquiry_section",
	"opened": True,
	"columns": [{"name": "qs_col", "fields": ["qs_enquiry", "qs_buyer_type", "qs_version", "qs_open_quote"]}],
}

FORM_SCRIPT = "QS Open Quote"
OPEN_QUOTE_SCRIPT = """function setupForm({ doc }) {
	return {
		actions: doc.qs_enquiry
			? [
					{
						label: __("Open quote"),
						onClick: () => window.open("/app/qs-enquiry/" + encodeURIComponent(doc.qs_enquiry), "_blank"),
					},
				]
			: [],
	}
}
"""


def execute() -> None:
	seed_kanban()
	seed_list_filters()
	seed_crm_side_panel()
	seed_crm_form_script()


def seed_kanban() -> None:
	if frappe.db.exists("Kanban Board", KANBAN):
		return
	board = quick_kanban_board(ENQUIRY, KANBAN, "status")
	for column in board.columns:
		column.indicator = KANBAN_COLOURS.get(column.column_name, "Gray")
	board.fields = json.dumps(KANBAN_CARD_FIELDS)
	board.save(ignore_permissions=True)


def seed_list_filters() -> None:
	for name, filters in LIST_FILTERS.items():
		if frappe.db.exists(
			"List Filter", {"reference_doctype": ENQUIRY, "filter_name": name, "for_user": ("is", "not set")}
		):
			continue
		frappe.get_doc(
			{
				"doctype": "List Filter",
				"reference_doctype": ENQUIRY,
				"filter_name": name,
				"for_user": "",
				"filters": json.dumps(filters),
			}
		).insert(ignore_permissions=True)


def seed_crm_side_panel() -> None:
	"""Append the Enquiry section to CRM's deal side panel; merge, never overwrite."""
	name = frappe.db.get_value("CRM Fields Layout", {"dt": "CRM Deal", "type": "Side Panel"})
	if not name:  # CRM creates it on install; nothing to merge into otherwise
		return
	doc = frappe.get_doc("CRM Fields Layout", name)
	layout = json.loads(doc.layout or "[]")
	if any(section.get("name") == ENQUIRY_SECTION["name"] for section in layout):
		return
	layout.append(ENQUIRY_SECTION)
	doc.layout = json.dumps(layout)
	doc.save(ignore_permissions=True)


def seed_crm_form_script() -> None:
	if frappe.db.exists("CRM Form Script", FORM_SCRIPT):
		return
	frappe.get_doc(
		{
			"doctype": "CRM Form Script",
			"dt": "CRM Deal",
			"view": "Form",
			"enabled": 1,
			"script": OPEN_QUOTE_SCRIPT,
		}
	).insert(ignore_permissions=True, set_name=FORM_SCRIPT)
