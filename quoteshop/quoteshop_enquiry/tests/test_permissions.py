"""CONTRACTS §6.5 / LAYOUT_MAP §C - Sales User sees own/assigned only; Sales Manager sees all."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.permissions import enquiry_query_conditions, has_enquiry_permission
from quoteshop.quoteshop_enquiry.tests.factories import make_enquiry, make_user

SALES_1 = "qs-test-sales-1@example.com"
SALES_2 = "qs-test-sales-2@example.com"
LOOKALIKE = "xqs-test-sales-1@example.com"  # contains SALES_1 as a substring
MANAGER = "qs-test-manager@example.com"
LINES = [{"item_code": "_QS Test Item P", "requested_qty": 1, "listed_rate": 10}]


class TestEnquiryPermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(SALES_1, ["Sales User"])
		make_user(SALES_2, ["Sales User"])
		make_user(LOOKALIKE, ["Sales User"])
		make_user(MANAGER, ["Sales User", "Sales Manager"])

		def enquiry(**db_values):
			name = make_enquiry(LINES).name
			if db_values:
				frappe.db.set_value("QS Enquiry", name, db_values, update_modified=False)
			return name

		cls.owned = enquiry(owner=SALES_1)
		cls.assigned = enquiry(assigned_to=SALES_1)
		cls.todo_assigned = enquiry(_assign=json.dumps([SALES_1]))
		cls.other = enquiry(owner=SALES_2, _assign=json.dumps([LOOKALIKE]))
		cls.all = {cls.owned, cls.assigned, cls.todo_assigned, cls.other}

	def visible(self, user):
		with self.set_user(user):
			return set(frappe.get_list("QS Enquiry", filters={"name": ["in", list(self.all)]}, pluck="name"))

	def test_sales_user_list_own_assigned(self):
		self.assertEqual(self.visible(SALES_1), {self.owned, self.assigned, self.todo_assigned})
		self.assertEqual(self.visible(SALES_2), {self.other})

	def test_assign_match_is_exact_not_substring(self):
		self.assertEqual(self.visible(LOOKALIKE), {self.other})
		self.assertNotIn(self.other, self.visible(SALES_1))

	def test_sales_manager_sees_all(self):
		self.assertEqual(self.visible(MANAGER), self.all)
		for name in self.all:
			self.assertTrue(frappe.has_permission("QS Enquiry", "read", doc=name, user=MANAGER))

	def test_sales_user_has_permission_own_assigned(self):
		for name in (self.owned, self.assigned, self.todo_assigned):
			for ptype in ("read", "write"):
				self.assertTrue(
					frappe.has_permission("QS Enquiry", ptype, doc=name, user=SALES_1), (name, ptype)
				)

	def test_sales_user_doc_denied(self):
		self.assertFalse(frappe.has_permission("QS Enquiry", "read", doc=self.other, user=SALES_1))
		self.assertFalse(frappe.has_permission("QS Enquiry", "write", doc=self.other, user=SALES_1))
		with self.set_user(SALES_1), self.assertRaises(frappe.PermissionError):
			frappe.get_doc("QS Enquiry", self.other).check_permission("read")

	def test_query_conditions_empty_for_managers(self):
		self.assertEqual(enquiry_query_conditions(MANAGER), "")
		self.assertEqual(enquiry_query_conditions("Administrator"), "")

	def test_has_enquiry_permission_hook(self):
		doc = frappe.get_doc("QS Enquiry", self.other)
		self.assertFalse(has_enquiry_permission(doc, "read", SALES_1))
		self.assertTrue(has_enquiry_permission(doc, "read", SALES_2))
		self.assertTrue(has_enquiry_permission(doc, "read", MANAGER))
