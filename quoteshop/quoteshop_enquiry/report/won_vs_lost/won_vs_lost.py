"""Won vs Lost: Accepted vs Lost QS Enquiries (count, offered value) with the lost-reason breakdown."""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Count, Sum
from pypika.functions import Trim

from quoteshop.quoteshop_enquiry.report import in_date_range, label_or, money, permitted


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	won = [r for r in data if r.status == "Accepted"]  # data = a handful of grouped rows
	lost = [r for r in data if r.status == "Lost"]
	won_count, lost_count = sum(r.enquiries for r in won), sum(r.enquiries for r in lost)
	decided = won_count + lost_count

	chart = {
		"data": {
			"labels": [_("Won"), _("Lost")],
			"datasets": [{"name": _("Enquiries"), "values": [won_count, lost_count]}],
		},
		"type": "donut",
		"colors": ["#28a745", "#e24c4c"],
	}
	summary = [
		{"label": _("Won"), "value": won_count, "datatype": "Int", "indicator": "Green"},
		{"label": _("Lost"), "value": lost_count, "datatype": "Int", "indicator": "Red"},
		{
			"label": _("Win Rate"),
			"value": won_count * 100 / decided if decided else 0,
			"datatype": "Percent",
			"indicator": "Blue",
		},
		{
			"label": _("Won Value"),
			"value": sum(r.total_offered or 0 for r in won),
			"datatype": "Currency",
			"indicator": "Green",
		},
		{
			"label": _("Lost Value"),
			"value": sum(r.total_offered or 0 for r in lost),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
	return get_columns(), data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "lost_reason", "label": _("Lost Reason"), "fieldtype": "Data", "width": 280},
		{"fieldname": "enquiries", "label": _("Enquiries"), "fieldtype": "Int", "width": 110},
		money("total_offered", _("Offered Value"), 160),
	]


def get_data(filters):
	e = frappe.qb.DocType("QS Enquiry")
	reason = (
		Case()
		.when(e.status == "Lost", label_or(Trim(e.lost_reason), _("Not specified")))
		.else_("")
		.as_("lost_reason")
	)
	q = (
		frappe.qb.from_(e)
		.select(e.status, reason, Count(e.name).as_("enquiries"), Sum(e.total_offered).as_("total_offered"))
		.where(e.status.isin(["Accepted", "Lost"]))
		.where(in_date_range(e.creation, filters))
		.where(e.name.isin(permitted("QS Enquiry")))
		.groupby(e.status, reason)
		.orderby(e.status)
		.orderby(Count(e.name), order=frappe.qb.desc)
	)
	if filters.get("salesperson"):
		q = q.where(e.assigned_to == filters.salesperson)
	if filters.get("buyer_type"):
		q = q.where(e.buyer_type == filters.buyer_type)
	return q.run(as_dict=True)
