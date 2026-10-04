"""Phase 4 CRM (CONTRACTS §3.1-3.4, §7.2; TEST_MATRIX CRM-01..07, DSK-04, DSK-05).

One CRM Deal per enquiry (qs_enquiry, deal_value = total_offered, primary contact, no products), assignment
priority buyer-type assignee → Customer.account_manager → Assignment Rule, status sync incl. Won / Lost,
QS deal statuses and the CRM side panel / form script seeds.
"""

import json
from unittest.mock import patch

import frappe
from frappe.cache_manager import clear_doctype_map

from quoteshop.patches.v1_0 import seed_crm_statuses, seed_desk
from quoteshop.quoteshop_enquiry import crm
from quoteshop.quoteshop_enquiry.tests.factories import (
	EnquiryTestCase,
	call_api,
	make_buyer_contact,
	make_enquiry_settings,
	make_otp_token,
	make_published_item,
	make_qs_customer,
	make_quote,
	make_user,
)

MOBILE = "+919811400001"
A, B = "_QS CRM-A", "_QS CRM-B"
SUBMIT = "quoteshop.quoteshop_enquiry.api.submit_enquiry"
LINES = [
	{"item_code": A, "requested_qty": 2, "listed_rate": 100, "offered_rate": 90},
	{"item_code": B, "requested_qty": 1, "listed_rate": 50},
]


def deals_of(enquiry):
	return frappe.get_all("CRM Deal", filters={"qs_enquiry": enquiry}, pluck="name")


class TestDealCreation(EnquiryTestCase):
	def test_one_deal_per_enquiry(self):
		"""CRM-01"""
		doc = make_quote(LINES, mobile=MOBILE)
		name = crm.create_deal(doc)
		self.assertEqual(deals_of(doc.name), [name])
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, "crm_deal"), name)

	def test_deal_fields(self):
		doc = make_quote(LINES, mobile=MOBILE, buyer_type="Retailer")
		deal = frappe.get_doc("CRM Deal", crm.create_deal(doc))
		self.assertEqual(
			(deal.qs_enquiry, deal.qs_buyer_type, deal.qs_version, deal.status),
			(doc.name, "Retailer", 0, "Requested"),
		)
		self.assertEqual([(c.contact, c.is_primary) for c in deal.contacts], [(doc.contact, 1)])
		self.assertEqual(deal.mobile_no, MOBILE)  # copied by CRM from the primary contact

	def test_deal_value_equals_total_offered(self):
		"""CRM-03"""
		doc = make_quote(LINES, mobile=MOBILE)
		self.assertEqual(doc.total_offered, 230.0)
		self.assertEqual(frappe.db.get_value("CRM Deal", crm.create_deal(doc), "deal_value"), 230.0)

	def test_products_table_not_filled(self):
		"""CRM-03 / CONTRACTS §9.12"""
		deal = crm.create_deal(make_quote(LINES, mobile=MOBILE))
		self.assertEqual(frappe.db.count("CRM Products", {"parent": deal, "parenttype": "CRM Deal"}), 0)

	def test_deal_creation_idempotent(self):
		"""CRM-02: creating the deal again for the same enquiry keeps exactly one Deal."""
		doc = make_quote(LINES, mobile=MOBILE)
		first = crm.create_deal(doc)
		doc.reload()
		self.assertEqual(crm.create_deal(doc), first)
		self.assertEqual(deals_of(doc.name), [first])

	def test_submit_creates_exactly_one_deal(self):
		make_published_item(A, rate=100)
		with patch("frappe.enqueue"):
			name = call_api(
				SUBMIT,
				data={
					"items": [{"item_code": A, "qty": 3}],
					"buyer_name": "_QS CRM Buyer",
					"mobile": MOBILE,
					"otp_token": make_otp_token(MOBILE),
				},
			)["name"]
		doc = frappe.get_doc("QS Enquiry", name)
		self.assertEqual(deals_of(name), [doc.crm_deal])
		self.assertEqual(frappe.db.get_value("CRM Deal", doc.crm_deal, "deal_value"), 300.0)


class TestAssignment(EnquiryTestCase):
	"""CRM-04..07, through submit_enquiry (CONTRACTS §3.3)."""

	def setUp(self):
		super().setUp()
		make_published_item(A, rate=100)
		self.type_user = make_user("_qs_type_assignee@example.com", ("Sales User",))
		self.manager = make_user("_qs_account_manager@example.com", ("Sales User",))
		self.rule_user = make_user("_qs_rule_assignee@example.com", ("Sales User",))
		make_enquiry_settings(
			buyer_types=[
				{"label": "Club owner", "default_assignee": self.type_user},
				{"label": "Retailer"},
			]
		)

	def submit(self, buyer_type=None):
		with patch("frappe.enqueue"):
			name = call_api(
				SUBMIT,
				data={
					"items": [{"item_code": A, "qty": 1}],
					"buyer_name": "_QS CRM Buyer",
					"mobile": MOBILE,
					"otp_token": make_otp_token(MOBILE),
					"buyer_type": buyer_type,
				},
			)["name"]
		doc = frappe.get_doc("QS Enquiry", name)
		deal = frappe.db.get_value("CRM Deal", doc.crm_deal, ["deal_owner", "_assign"], as_dict=True)
		return doc, deal

	def repeat_buyer(self):
		make_qs_customer("_QS CRM Customer", contact=make_buyer_contact(MOBILE), account_manager=self.manager)

	def assignment_rule(self):
		rule = frappe.get_doc(
			{
				"doctype": "Assignment Rule",
				"name": "_QS Test Deal Rule",
				"document_type": "CRM Deal",
				"description": "_QS Test",
				"assign_condition": "1 == 1",
				"rule": "Round Robin",
				"users": [{"user": self.rule_user}],
				"assignment_days": [
					{"day": d}
					for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
				],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(clear_doctype_map, "Assignment Rule", "CRM Deal")
		return rule

	def test_buyer_type_assignee_wins(self):
		"""CRM-04: beats the account manager of a repeat buyer."""
		self.repeat_buyer()
		doc, deal = self.submit("Club owner")
		self.assertEqual((doc.assigned_to, deal.deal_owner), (self.type_user, self.type_user))

	def test_account_manager_fallback(self):
		"""CRM-05: no buyer-type assignee → the Customer's account manager."""
		self.repeat_buyer()
		for buyer_type in (None, "Retailer"):
			with self.subTest(buyer_type=buyer_type):
				doc, deal = self.submit(buyer_type)
				self.assertEqual((doc.assigned_to, deal.deal_owner), (self.manager, self.manager))

	def test_assignment_rule_fallback(self):
		"""CRM-06: nobody resolved by QS → the CRM Deal Assignment Rule assigns."""
		self.assignment_rule()
		doc, deal = self.submit()
		self.assertEqual(json.loads(deal._assign or "[]"), [self.rule_user])
		self.assertEqual(doc.assigned_to, self.rule_user)

	def test_no_double_assignment_when_qs_resolves(self):
		"""deal_owner is set only when QS resolves someone; the rule then adds nobody else."""
		self.assignment_rule()
		_doc, deal = self.submit("Club owner")
		self.assertEqual(json.loads(deal._assign or "[]"), [self.type_user])

	def test_enquiry_assigned_to_synced(self):
		"""CRM-07"""
		doc, deal = self.submit("Club owner")
		self.assertEqual(doc.assigned_to, deal.deal_owner)
		self.assertIn(self.type_user, json.loads(deal._assign or "[]"))

	def test_unassigned_without_any_source(self):
		doc, deal = self.submit()
		self.assertFalse(doc.assigned_to)
		self.assertFalse(deal.deal_owner)


class TestStatusSync(EnquiryTestCase):
	def setUp(self):
		super().setUp()
		self.doc = make_quote(LINES, mobile=MOBILE, deal=True)

	def sync(self, status, **fields):
		self.doc.update({"status": status, **fields})
		crm.sync_deal_status(self.doc)
		return frappe.get_doc("CRM Deal", self.doc.crm_deal)

	def test_same_name_statuses(self):
		for status in ("Requested", "Price Sent", "Changes Requested", "Expired"):
			with self.subTest(status=status):
				self.assertEqual(self.sync(status).status, status)

	def test_accepted_is_won(self):
		deal = self.sync("Accepted")
		self.assertEqual(frappe.db.get_value("CRM Deal Status", deal.status, "type"), "Won")
		self.assertTrue(deal.closed_date)

	def test_lost_sets_reason_other_and_notes(self):
		deal = self.sync("Lost", lost_reason="Bought elsewhere")
		self.assertEqual(
			(frappe.db.get_value("CRM Deal Status", deal.status, "type"), deal.lost_reason, deal.lost_notes),
			("Lost", "Other", "Bought elsewhere"),
		)

	def test_lost_without_reason_still_valid(self):
		self.assertEqual(self.sync("Lost", lost_reason=None).lost_reason, "Other")

	def test_value_and_version_follow(self):
		deal = self.sync("Price Sent", total_offered=1234.5, current_version=3)
		self.assertEqual((deal.deal_value, deal.qs_version), (1234.5, 3))

	def test_unmapped_status_leaves_deal(self):
		self.assertEqual(self.sync("Draft").status, "Requested")

	def test_no_deal_is_a_noop(self):
		doc = make_quote(LINES, mobile="+919811400002")
		doc.status = "Lost"
		crm.sync_deal_status(doc)  # must not raise


class TestCRMSetup(EnquiryTestCase):
	def test_status_colours(self):
		"""DSK-04 / CONTRACTS §9.5"""
		seed_crm_statuses.execute()
		expected = {
			"Requested": ("Open", "blue"),
			"Price Sent": ("Ongoing", "orange"),
			"Changes Requested": ("Ongoing", "yellow"),
			"Expired": ("On Hold", "gray"),
		}
		for name, value in expected.items():
			self.assertEqual(frappe.db.get_value("CRM Deal Status", name, ["type", "color"]), value)
		self.assertTrue(frappe.db.exists("CRM Deal Status", {"type": "Won"}))
		self.assertTrue(frappe.db.exists("CRM Deal Status", {"type": "Lost"}))

	def test_statuses_idempotent_and_keep_admin_edits(self):
		frappe.db.set_value("CRM Deal Status", "Requested", "color", "teal")
		count = frappe.db.count("CRM Deal Status")
		seed_crm_statuses.execute()
		seed_crm_statuses.execute()
		self.assertEqual(frappe.db.count("CRM Deal Status"), count)
		self.assertEqual(frappe.db.get_value("CRM Deal Status", "Requested", "color"), "teal")

	def side_panel(self):
		name = frappe.db.get_value("CRM Fields Layout", {"dt": "CRM Deal", "type": "Side Panel"})
		if not name:
			name = (
				frappe.get_doc(
					{
						"doctype": "CRM Fields Layout",
						"dt": "CRM Deal",
						"type": "Side Panel",
						"layout": json.dumps([{"name": "contacts_section", "label": "Contacts"}]),
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		return name

	def test_enquiry_section_idempotent(self):
		"""DSK-05: merged once, CRM's own sections kept."""
		name = self.side_panel()
		before = json.loads(frappe.db.get_value("CRM Fields Layout", name, "layout") or "[]")
		before = [s for s in before if s.get("name") != "qs_enquiry_section"]
		frappe.db.set_value("CRM Fields Layout", name, "layout", json.dumps(before))
		seed_desk.seed_crm_side_panel()
		seed_desk.seed_crm_side_panel()
		layout = json.loads(frappe.db.get_value("CRM Fields Layout", name, "layout"))
		ours = [s for s in layout if s.get("name") == "qs_enquiry_section"]
		self.assertEqual(len(ours), 1)
		self.assertEqual(
			ours[0]["columns"][0]["fields"], ["qs_enquiry", "qs_buyer_type", "qs_version", "qs_open_quote"]
		)
		self.assertEqual(layout[: len(before)], before)

	def test_open_quote_form_script(self):
		"""CONTRACTS §6.6: the CRM 'Open quote' action replaces the HTML link."""
		seed_desk.seed_crm_form_script()
		seed_desk.seed_crm_form_script()
		scripts = frappe.get_all(
			"CRM Form Script", filters={"name": seed_desk.FORM_SCRIPT}, fields=["dt", "view", "enabled", "script"]
		)
		self.assertEqual(len(scripts), 1)
		self.assertEqual((scripts[0].dt, scripts[0].view, scripts[0].enabled), ("CRM Deal", "Form", 1))
		self.assertIn("/app/qs-enquiry/", scripts[0].script)
