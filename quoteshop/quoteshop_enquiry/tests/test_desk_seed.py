"""Desk/CRM seeds are idempotent and correct (CONTRACTS §3.2, §3.4, §5.7, §9.5, §9.10; TESTING §3 Desk)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.patches.v1_0 import seed_crm_statuses, seed_desk
from quoteshop.quoteshop_enquiry.tests.factories import make_enquiry

KANBAN = "Enquiry Pipeline"
SECTION = "qs_enquiry_section"
FORM_SCRIPT = "QS Open Quote"
KANBAN_COLOURS = {  # SPEC §5 / LAYOUT_MAP D (darkgrey → Gray: Kanban has no darkgrey)
	"Draft": "Gray",
	"Requested": "Blue",
	"Price Sent": "Orange",
	"Changes Requested": "Yellow",
	"Accepted": "Green",
	"Lost": "Red",
	"Expired": "Gray",
}
QS_DEAL_STATUSES = {  # name: (type, colour) - CONTRACTS §7.2 phase 4, §9.5
	"Requested": ("Open", "blue"),
	"Price Sent": ("Ongoing", "orange"),
	"Changes Requested": ("Ongoing", "yellow"),
	"Expired": ("On Hold", "gray"),
}


def side_panel():
	name = frappe.db.get_value("CRM Fields Layout", {"dt": "CRM Deal", "type": "Side Panel"})
	return name, json.loads(frappe.db.get_value("CRM Fields Layout", name, "layout") or "[]")


class TestDeskSeed(IntegrationTestCase):
	def test_kanban_created_once(self):
		if frappe.db.exists("Kanban Board", KANBAN):
			frappe.delete_doc("Kanban Board", KANBAN, force=1, ignore_permissions=True)
		seed_desk.seed_kanban()
		seed_desk.seed_kanban()
		self.assertEqual(frappe.db.count("Kanban Board", {"name": KANBAN}), 1)
		board = frappe.get_doc("Kanban Board", KANBAN)
		self.assertEqual((board.reference_doctype, board.field_name), ("QS Enquiry", "status"))
		self.assertEqual({c.column_name: c.indicator for c in board.columns}, KANBAN_COLOURS)
		self.assertEqual(json.loads(board.fields), ["buyer_name", "total_offered", "assigned_to"])

	def test_kanban_admin_edits_survive(self):
		seed_desk.seed_kanban()
		board = frappe.get_doc("Kanban Board", KANBAN)
		board.columns[0].indicator = "Pink"
		board.save(ignore_permissions=True)
		seed_desk.execute()
		self.assertEqual(frappe.get_doc("Kanban Board", KANBAN).columns[0].indicator, "Pink")

	def test_list_filters_once_and_correct(self):
		frappe.db.delete("List Filter", {"reference_doctype": "QS Enquiry"})
		seed_desk.seed_list_filters()
		seed_desk.seed_list_filters()
		filters = {
			f.filter_name: json.loads(f.filters)
			for f in frappe.get_all(
				"List Filter", filters={"reference_doctype": "QS Enquiry"}, fields=["filter_name", "filters"]
			)
		}
		self.assertEqual(sorted(filters), ["Needs pricing", "Waiting for buyer"])

		lines = [{"item_code": "_QS-DS-1", "requested_qty": 1, "listed_rate": 10}]
		names = {}
		for status in ("Requested", "Changes Requested", "Price Sent", "Lost", "Accepted"):
			names[status] = make_enquiry(lines).name
			frappe.db.set_value("QS Enquiry", names[status], "status", status)
		mine = ["QS Enquiry", "name", "in", list(names.values())]
		got = {
			name: set(frappe.get_all("QS Enquiry", filters=[*f, mine], pluck="name"))
			for name, f in filters.items()
		}
		self.assertEqual(got["Needs pricing"], {names["Requested"], names["Changes Requested"]})
		self.assertEqual(got["Waiting for buyer"], {names["Price Sent"]})

	def test_crm_side_panel_section_once(self):
		name, layout = side_panel()
		self.assertTrue(name, "CRM Deal side panel layout missing (CRM install)")
		others = [s for s in layout if s.get("name") != SECTION]
		frappe.db.set_value("CRM Fields Layout", name, "layout", json.dumps(others))
		seed_desk.seed_crm_side_panel()
		seed_desk.seed_crm_side_panel()
		_name, layout = side_panel()
		ours = [s for s in layout if s.get("name") == SECTION]
		self.assertEqual(len(ours), 1)
		self.assertEqual(ours[0]["label"], "Enquiry")
		self.assertEqual(
			ours[0]["columns"][0]["fields"], ["qs_enquiry", "qs_buyer_type", "qs_version", "qs_open_quote"]
		)
		self.assertEqual([s for s in layout if s.get("name") != SECTION], others)  # merged, never overwritten

	def test_crm_form_script_once(self):
		if frappe.db.exists("CRM Form Script", FORM_SCRIPT):
			frappe.delete_doc("CRM Form Script", FORM_SCRIPT, force=1, ignore_permissions=True)
		seed_desk.seed_crm_form_script()
		seed_desk.seed_crm_form_script()
		self.assertEqual(frappe.db.count("CRM Form Script", {"name": FORM_SCRIPT}), 1)
		script = frappe.get_doc("CRM Form Script", FORM_SCRIPT)
		self.assertEqual((script.dt, script.view, script.enabled), ("CRM Deal", "Form", 1))
		self.assertIn("/app/qs-enquiry/", script.script)

	def test_execute_twice(self):
		seed_desk.execute()
		before = {
			dt: frappe.db.count(dt, flt)
			for dt, flt in (
				("Kanban Board", {"reference_doctype": "QS Enquiry"}),
				("List Filter", {"reference_doctype": "QS Enquiry"}),
				("CRM Form Script", {"name": FORM_SCRIPT}),
			)
		}
		seed_desk.execute()
		for dt, count in before.items():
			flt = {"reference_doctype": "QS Enquiry"} if dt != "CRM Form Script" else {"name": FORM_SCRIPT}
			self.assertEqual(frappe.db.count(dt, flt), count, dt)
		self.assertEqual(sum(s.get("name") == SECTION for s in side_panel()[1]), 1)


class TestCRMStatusSeed(IntegrationTestCase):
	def test_seed_crm_statuses_idempotent(self):
		for name in QS_DEAL_STATUSES:
			if frappe.db.exists("CRM Deal Status", name):
				frappe.delete_doc("CRM Deal Status", name, force=1, ignore_permissions=True)
		seed_crm_statuses.execute()
		seed_crm_statuses.execute()
		for name, (status_type, colour) in QS_DEAL_STATUSES.items():
			self.assertEqual(frappe.db.count("CRM Deal Status", {"name": name}), 1, name)
			self.assertEqual(
				tuple(frappe.db.get_value("CRM Deal Status", name, ["type", "color"])),
				(status_type, colour),
				name,
			)
		self.assertTrue(frappe.db.exists("CRM Deal Status", {"type": "Won"}))
		self.assertTrue(frappe.db.exists("CRM Deal Status", {"type": "Lost"}))

	def test_admin_colour_kept(self):
		seed_crm_statuses.execute()
		frappe.db.set_value("CRM Deal Status", "Requested", "color", "pink")
		seed_crm_statuses.execute()
		self.assertEqual(frappe.db.get_value("CRM Deal Status", "Requested", "color"), "pink")
