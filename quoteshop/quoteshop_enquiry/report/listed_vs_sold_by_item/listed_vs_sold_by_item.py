"""Listed vs Sold by Item: submitted QuoteShop Sales Orders (qs_enquiry set), per item."""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from pypika.terms import ValueWrapper

from quoteshop.quoteshop_enquiry.report import (
	bar_chart,
	discount_pct_column,
	discount_summary,
	in_date_range,
	in_item_group,
	money,
	pct,
	permitted,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data = get_data(filters, currency)
	return (
		get_columns(),
		data,
		None,
		bar_chart(data, "item_code", "discount_amount", _("Discount")),
		discount_summary(data, "listed_value", "sold_value", "discount_amount", currency=currency),
	)


def get_columns():
	cur = {"options": "currency"}
	return [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "item_group",
			"label": _("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 140,
		},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		money("listed_value", _("Listed Value"), **cur),
		money("sold_value", _("Sold Value"), **cur),
		money("discount_amount", _("Discount"), **cur),
		discount_pct_column(),
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]


def get_data(filters, currency):
	so = frappe.qb.DocType("Sales Order")
	soi = frappe.qb.DocType("Sales Order Item")
	item = frappe.qb.DocType("Item")

	# Lines without a listed price ("price on request") count as listed = sold, not as a negative discount.
	line_listed = (
		Case().when(soi.base_price_list_rate > 0, soi.base_price_list_rate * soi.qty).else_(soi.base_amount)
	)
	listed, sold = Sum(line_listed), Sum(soi.base_amount)

	q = (
		frappe.qb.from_(soi)
		.join(so)
		.on(so.name == soi.parent)
		.join(item)
		.on(item.name == soi.item_code)
		.select(
			soi.item_code,
			item.item_name,
			item.item_group,
			Sum(soi.stock_qty).as_("qty"),
			item.stock_uom,
			listed.as_("listed_value"),
			sold.as_("sold_value"),
			(listed - sold).as_("discount_amount"),
			pct(listed - sold, listed).as_("discount_pct"),
			ValueWrapper(currency).as_("currency"),
		)
		.where(soi.parenttype == "Sales Order")
		.where(so.docstatus == 1)
		.where(so.qs_enquiry != "")
		.where(so.company == filters.company)
		.where(in_date_range(so.transaction_date, filters))
		.where(so.name.isin(permitted("Sales Order")))
		.groupby(soi.item_code, item.item_name, item.item_group, item.stock_uom)
		.orderby(listed - sold, order=frappe.qb.desc)
	)
	if filters.get("item_group"):
		q = q.where(in_item_group(item.item_group, filters.item_group))
	return q.run(as_dict=True)
