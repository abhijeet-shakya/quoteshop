import re
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate, get_fullname, getdate

from quoteshop.quoteshop_enquiry.portal import get_account_data
from quoteshop.quoteshop_website.context import setup

no_cache = 1
# Only these internal pages may follow sign-in; fullmatch rules out schemes, hosts, backslashes,
# control characters and trailing newlines. Keep in sync with SAFE_NEXT in public/js/qs/account.js.
SAFE_NEXT = re.compile(r"/quote|/account|/q/[A-Za-z0-9-]+(\?t=[A-Za-z0-9_-]+)?")


def money(value, currency="INR"):
	value = flt(value)
	return fmt_money(value, precision=0 if value == int(value) else 2, currency=currency).replace(" ", "", 1)


def date(value):
	return formatdate(getdate(value), "d MMM yyyy") if value else ""


def safe_next(url: str | None) -> str:
	"""`?next=` target after sign-in: an allow-listed internal path, else /account."""
	return url if isinstance(url, str) and SAFE_NEXT.fullmatch(url) else "/account"


def get_context(context: dict) -> dict:
	qs = setup(context, "account", title=_("My account"))
	context.guest = frappe.session.user == "Guest"
	context.next_url = safe_next(frappe.form_dict.get("next"))
	if context.guest:
		return context

	data = frappe._dict(get_account_data())
	show_savings = cint(frappe.get_cached_doc("QS Store Settings").show_savings_to_buyer)

	orders = [order_view(frappe._dict(o), show_savings) for o in data.orders or []]
	requests = [request_view(frappe._dict(r), qs) for r in data.requests or []]
	buyer = frappe._dict(
		frappe.db.get_value(
			"Contact",
			{"user": frappe.session.user},
			["first_name", "company_name", "mobile_no"],
			as_dict=True,
		)
		or {}
	)
	total_saved = sum(o.saved_value for o in orders if o.known)
	context.update(
		buyer_name=buyer.first_name or get_fullname(frappe.session.user),
		buyer_meta=" · ".join(filter(None, (buyer.company_name, buyer.mobile_no))),
		orders=orders,
		requests=requests,
		open_count=sum(1 for r in requests if r.open),
		show_savings=show_savings and total_saved > 0,
		total_saved=money(total_saved, orders[0].currency if orders else "INR"),
	)
	return context


def order_view(o, show_savings):
	cur = o.currency or "INR"
	lines = [frappe._dict(l, listed_rate=l.get("price_list_rate")) for l in o.lines or []]
	listed = flt(o.listed) or sum(flt(l.listed_rate) * flt(l.qty) for l in lines)
	sold = flt(o.net_total) or sum(flt(l.amount) for l in lines)
	known = bool(lines) and all(flt(l.listed_rate) > 0 for l in lines)
	saved = listed - sold
	done = o.status in ("Completed", "Closed", "Cancelled")
	return frappe._dict(
		name=o.name,
		date=date(o.transaction_date),
		status=_(o.status) if done else _("Confirmed"),
		tone="plain" if done else "accent",
		currency=cur,
		line_count=len(lines),
		units=f"{sum(flt(l.qty) for l in lines):g}",
		listed=money(listed, cur) if known else "—",
		sold=money(sold, cur),
		known=known,
		saved_value=saved,
		saved=money(saved, cur) if known and show_savings and saved > 0 else None,
		pct=f"{saved / listed * 100:.1f}%" if known and listed else "",
		lines=[
			frappe._dict(
				name=l.item_name or l.item_code,
				qty=f"{flt(l.qty):g}",
				listed=money(l.listed_rate, cur) if flt(l.listed_rate) else "",
				sold=money(l.rate, cur),
			)
			for l in lines
		],
		pdf_url="/api/method/frappe.utils.print_format.download_pdf?"
		+ urlencode({"doctype": "Sales Order", "name": o.name}),
	)


def request_view(r, qs):
	status = r.status or "Requested"
	note = {
		"Price Sent": _("Your price is ready.")
		+ (" " + _("Valid till {0}.").format(date(r.valid_till)) if r.valid_till else ""),
		"Requested": _("Our team will WhatsApp you within {0}.").format(qs.response_time)
		if qs.response_time
		else _("Our team will WhatsApp you soon."),
		"Changes Requested": _("We're updating your price."),
		"Accepted": _("Became order {0}.").format(r.sales_order) if r.sales_order else _("Accepted."),
		"Expired": _("This price has expired."),
		"Lost": _("Closed."),
	}.get(status, "")
	label, tone = {
		"Requested": (_("Waiting for price"), "warn"),
		"Changes Requested": (_("Waiting for price"), "warn"),
		"Price Sent": (_("Price sent"), "accent"),
		"Accepted": (_("Ordered"), "plain"),
		"Expired": (_("Expired"), "plain"),
		"Lost": (_("Closed"), "plain"),
	}.get(status, (_(status), "plain"))
	n, units = cint(r.line_count), flt(r.unit_count)
	return frappe._dict(
		name=r.name,
		date=date(r.creation),
		summary=f"{n} {_('item') if n == 1 else _('items')} · {units:g} {_('pcs')}",
		status=label,
		tone=tone,
		note=note,
		priced=status == "Price Sent",
		open=status in ("Requested", "Changes Requested", "Price Sent"),
		url=f"/q/{r.name}",  # signed-in buyer: /q works without a token for own enquiries
	)
