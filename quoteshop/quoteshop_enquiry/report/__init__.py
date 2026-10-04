"""Shared helpers for the QuoteShop Enquiry script reports (CONTRACTS §7.2, decision §9.7)."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Count, IfNull, NullIf, Sum
from frappe.utils import add_days, getdate


def permitted(doctype: str):
	"""Sub-query of names the session user may read.

	frappe.qb alone skips permissions; get_query(ignore_permissions=False) applies role perms,
	user permissions, shares and permission_query_conditions (QS Enquiry: own/assigned for Sales User).
	"""
	return frappe.qb.get_query(doctype, fields=["name"], ignore_permissions=False)


def in_date_range(field, filters):
	"""Date/Datetime `field` within [from_date, to_date] (inclusive, index friendly)."""
	cond = field >= getdate(filters.from_date)
	return cond & (field < add_days(getdate(filters.to_date), 1))


def in_item_group(field, item_group: str):
	"""`field` (Link Item Group) is `item_group` or one of its descendants."""
	lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (0, -1)
	ig = frappe.qb.DocType("Item Group")
	return field.isin(frappe.qb.from_(ig).select(ig.name).where((ig.lft >= lft) & (ig.rgt <= rgt)))


def pct(part, whole):
	"""part / whole * 100 in SQL; 0 when whole is 0."""
	return IfNull(part * 100 / NullIf(whole, 0), 0)


def money(fieldname: str, label: str, width: int = 140, **extra) -> dict:
	return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": width, **extra}


def discount_pct_column() -> dict:
	# Frappe totals average a Percent column; the weighted figure is in report_summary instead.
	return {
		"fieldname": "discount_pct",
		"label": _("Discount %"),
		"fieldtype": "Percent",
		"width": 110,
		"disable_total": 1,
	}


def discount_summary(data: list[dict], listed: str, sold: str, discount: str, **money_opts) -> list[dict]:
	"""Overall (weighted) totals as report_summary cards. `data` is already aggregated in SQL (one row per group)."""
	total_listed = sum(r[listed] or 0 for r in data)
	total_sold = sum(r[sold] or 0 for r in data)
	total_discount = sum(r[discount] or 0 for r in data)
	return [
		{"label": _("Listed"), "value": total_listed, "datatype": "Currency", **money_opts},
		{"label": _("Sold / Offered"), "value": total_sold, "datatype": "Currency", **money_opts},
		{
			"label": _("Discount"),
			"value": total_discount,
			"datatype": "Currency",
			"indicator": "Red",
			**money_opts,
		},
		{
			"label": _("Discount %"),
			"value": total_discount * 100 / total_listed if total_listed else 0,
			"datatype": "Percent",
			"indicator": "Red",
		},
	]


def accepted_enquiry_discount(filters, *keys):
	"""Accepted QS Enquiries aggregated by `keys` (aliased terms): count, listed, offered, saved, discount %.

	Callers add any joins their keys need.
	"""
	e = frappe.qb.DocType("QS Enquiry")
	saved, listed = Sum(e.total_saved), Sum(e.total_listed)
	q = (
		frappe.qb.from_(e)
		.select(
			*keys,
			Count(e.name).as_("enquiries"),
			listed.as_("total_listed"),
			Sum(e.total_offered).as_("total_offered"),
			saved.as_("total_saved"),
			pct(saved, listed).as_("discount_pct"),
		)
		.where(e.status == "Accepted")
		.where(in_date_range(e.creation, filters))
		.where(e.name.isin(permitted("QS Enquiry")))
		.groupby(*keys)
		.orderby(saved, order=frappe.qb.desc)
	)
	if filters.get("company"):
		# QS Enquiry has no company; the accepted order carries it.
		so = frappe.qb.DocType("Sales Order")
		q = q.join(so).on(so.name == e.sales_order).where(so.company == filters.company)
	return q


def enquiry_discount_columns() -> list[dict]:
	return [
		{"fieldname": "enquiries", "label": _("Accepted Enquiries"), "fieldtype": "Int", "width": 140},
		money("total_listed", _("Listed")),
		money("total_offered", _("Offered")),
		money("total_saved", _("Discount")),
		discount_pct_column(),
	]


def bar_chart(
	data: list[dict], label: str, value: str, name: str, fieldtype: str = "Currency", top: int = 10
):
	rows = sorted(data, key=lambda r: r[value] or 0, reverse=True)[:top]
	return {
		"data": {
			"labels": [r[label] for r in rows],
			"datasets": [{"name": name, "values": [r[value] for r in rows]}],
		},
		"type": "bar",
		"fieldtype": fieldtype,
		"colors": ["#146B47"],
	}


def label_or(term, fallback: str):
	"""SQL: term, or `fallback` when NULL/empty."""
	return Coalesce(NullIf(term, ""), fallback)
