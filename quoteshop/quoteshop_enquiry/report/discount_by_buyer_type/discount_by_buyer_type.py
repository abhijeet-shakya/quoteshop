"""Discount by Buyer Type: accepted QS Enquiries grouped by buyer_type."""

import frappe
from frappe import _

from quoteshop.quoteshop_enquiry.report import (
	accepted_enquiry_discount,
	bar_chart,
	discount_summary,
	enquiry_discount_columns,
	label_or,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	e = frappe.qb.DocType("QS Enquiry")
	data = accepted_enquiry_discount(
		filters, label_or(e.buyer_type, _("Not specified")).as_("buyer_type")
	).run(as_dict=True)
	columns = [
		{"fieldname": "buyer_type", "label": _("Buyer Type"), "fieldtype": "Data", "width": 200},
		*enquiry_discount_columns(),
	]
	return (
		columns,
		data,
		None,
		bar_chart(data, "buyer_type", "total_saved", _("Discount")),
		discount_summary(data, "total_listed", "total_offered", "total_saved"),
	)
