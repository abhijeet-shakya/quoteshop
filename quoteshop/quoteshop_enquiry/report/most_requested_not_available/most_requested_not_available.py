"""Most-requested Not Available: QS Enquiry lines marked Not Available, grouped by item."""

import frappe
from frappe import _
from frappe.query_builder.functions import Count, IfNull, Max, Sum

from quoteshop.quoteshop_enquiry.report import bar_chart, in_date_range, in_item_group, permitted


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	chart = bar_chart(data, "item_code", "times_requested", _("Times Requested"), fieldtype="Int")
	return get_columns(), data, None, chart


def get_columns():
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 220},
		{
			"fieldname": "item_group",
			"label": _("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 150,
		},
		{"fieldname": "times_requested", "label": _("Times Requested"), "fieldtype": "Int", "width": 130},
		{"fieldname": "requested_qty", "label": _("Total Requested Qty"), "fieldtype": "Float", "width": 150},
		{"fieldname": "last_requested", "label": _("Last Requested"), "fieldtype": "Datetime", "width": 170},
	]


def get_data(filters):
	e = frappe.qb.DocType("QS Enquiry")
	line = frappe.qb.DocType("QS Enquiry Item")
	item = frappe.qb.DocType("Item")
	times = Count(e.name).distinct()
	q = (
		frappe.qb.from_(line)
		.join(e)
		.on(e.name == line.parent)
		.join(item)
		.on(item.name == line.item_code)
		.select(
			line.item_code,
			item.item_name,
			item.item_group,
			times.as_("times_requested"),
			Sum(line.requested_qty).as_("requested_qty"),
			Max(e.creation).as_("last_requested"),
		)
		.where(line.parenttype == "QS Enquiry")
		.where(line.parentfield == "items")
		.where(line.availability == "Not Available")
		.where(IfNull(line.change_flag, "") != "Removed")
		.where(in_date_range(e.creation, filters))
		.where(e.name.isin(permitted("QS Enquiry")))
		.groupby(line.item_code, item.item_name, item.item_group)
		.orderby(times, order=frappe.qb.desc)
		.orderby(Sum(line.requested_qty), order=frappe.qb.desc)
	)
	if filters.get("item_group"):
		q = q.where(in_item_group(item.item_group, filters.item_group))
	return q.run(as_dict=True)
