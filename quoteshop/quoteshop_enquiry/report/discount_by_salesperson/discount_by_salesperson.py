"""Discount by Salesperson: accepted QS Enquiries grouped by assigned_to."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce

from quoteshop.quoteshop_enquiry.report import (
	accepted_enquiry_discount,
	bar_chart,
	discount_summary,
	enquiry_discount_columns,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return (
		get_columns(),
		data,
		None,
		bar_chart(data, "salesperson_name", "total_saved", _("Discount")),
		discount_summary(data, "total_listed", "total_offered", "total_saved"),
	)


def get_columns():
	return [
		{
			"fieldname": "salesperson",
			"label": _("Salesperson"),
			"fieldtype": "Link",
			"options": "User",
			"width": 200,
		},
		{"fieldname": "salesperson_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		*enquiry_discount_columns(),
	]


def get_data(filters):
	e = frappe.qb.DocType("QS Enquiry")
	user = frappe.qb.DocType("User")
	q = accepted_enquiry_discount(
		filters,
		e.assigned_to.as_("salesperson"),
		Coalesce(user.full_name, e.assigned_to, _("Unassigned")).as_("salesperson_name"),
	)
	return q.left_join(user).on(user.name == e.assigned_to).run(as_dict=True)
