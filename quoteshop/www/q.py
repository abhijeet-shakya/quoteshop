from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate, getdate

from quoteshop.quoteshop_website.context import setup

no_cache = 1

LINES_SHOWN = 10
GROUPS_OPEN = 3
STATUS_TONE = {"Requested": "warn", "Changes Requested": "warn", "Price Sent": "accent", "Accepted": "accent"}


def status_label(status):
	return {
		"Requested": _("Waiting for price"),
		"Price Sent": _("Price sent"),
		"Changes Requested": _("Changes requested"),
		"Accepted": _("Accepted"),
		"Expired": _("Expired"),
		"Lost": _("Closed"),
	}.get(status, status or "")


def money(value, currency):
	value = flt(value)
	return fmt_money(value, precision=0 if value == int(value) else 2, currency=currency).replace(" ", "", 1)


def short_date(value):
	return formatdate(getdate(value), "d MMM") if value else ""


def get_context(context):
	name, token = frappe.form_dict.name, frappe.form_dict.t or ""
	setup(context, "quote_view", title=name)
	context.update(name=name, token=token)

	try:
		get_quote_view = frappe.get_attr("quoteshop.quoteshop_enquiry.quote_view.get_quote_view")
	except (ImportError, AttributeError):
		context.unavailable = True  # ponytail: backend phase 6 not deployed yet
		return context

	view = frappe._dict(get_quote_view(name, token))
	if view.outdated:
		context.outdated = view
		return context

	cur = view.currency or "INR"
	totals = frappe._dict(view.totals or {})
	view.history = sorted(view.history or [], key=lambda h: h.get("version") or 0)
	lines = [frappe._dict(l) for l in view.lines or [] if l.get("change_flag") != "Removed"]
	groups, counts = {}, {"ok": 0, "partial": 0, "none": 0}
	for l in lines:
		requested, offered = flt(l.requested_qty), flt(l.offered_qty)
		l.state = {"Partial": "partial", "Not Available": "none"}.get(l.availability, "ok")
		counts[l.state] += 1
		l.changed = l.availability not in (None, "", "Available") or l.change_flag in (
			"Qty changed",
			"Added",
			"Alternative",
		)
		l.note = line_note(l, requested, offered)
		l.tone = "bad" if l.state == "none" else "warn"
		l.qty_text = f"{requested:g} → {offered:g}" if offered != requested else f"{requested:g}"
		l.amount = 0 if l.state == "none" else flt(l.amount)
		l.total_text = money(l.amount, cur) if l.amount else "—"
		l.listed_text = money(l.listed_rate, cur) if flt(l.listed_rate) else ""
		l.price_text = money(l.offered_rate, cur) if flt(l.offered_rate) else "—"
		groups.setdefault(l.item_group or _("Items"), []).append(l)

	n = len(lines) or 1
	saved = flt(totals.total_saved)
	context.update(
		view=view,
		currency=cur,
		lines=lines,
		groups=[
			{
				"name": g,
				"lines": ls,
				"subtotal": money(sum(l.amount for l in ls), cur),
				"open": i < GROUPS_OPEN,
			}
			for i, (g, ls) in enumerate(groups.items())
		],
		shown=LINES_SHOWN,
		counts=counts,
		pct={k: f"{v / n * 100:.1f}%" for k, v in counts.items()},
		changes=sum(1 for l in lines if l.changed),
		unit_text=fmt_money(sum(flt(l.requested_qty) for l in lines), precision=0),
		offer_total=money(totals.total_offered, cur),
		list_total=money(totals.total_listed, cur),
		saved=money(saved, cur) if saved > 0 and view.show_savings else None,
		status_label=status_label(view.status),
		status_tone=STATUS_TONE.get(view.status, "plain"),
		subtitle=subtitle(view),
		can_accept=view.can_accept,
		can_change=view.can_change,
		accepted=view.status == "Accepted",
		history=[
			" · ".join(
				filter(None, (f"v{h.get('version')}", short_date(h.get("created_on")), h.get("summary")))
			)
			for h in view.history
		],
		change_items=[{"item_code": l.item_code, "qty": flt(l.requested_qty)} for l in lines],
		pdf_url=download_url(name, token, "pdf"),
		xlsx_url=download_url(name, token, "xlsx"),
	)
	return context


def line_note(l, requested, offered):
	extra = l.availability_note
	if l.availability == "Partial":
		return extra or _("{0} of {1} available").format(f"{offered:g}", f"{requested:g}")
	if l.availability == "Not Available":
		return " · ".join(filter(None, (_("Not available"), extra)))
	if l.availability == "Made to Order":
		days = _("{0} days").format(l.lead_time_days) if l.lead_time_days else None
		return " · ".join(filter(None, (_("Made to order"), days, extra)))
	if l.availability == "Alternative":
		alt = l.alternative_item_name or l.alternative_item
		alt = _("alternative {0} offered").format(alt) if alt else None
		return " · ".join(filter(None, (_("Alternative"), alt, extra)))
	return extra or ""


def subtitle(view):
	last = view.history[-1].get("created_on") if view.history else None
	parts = [f"{status_label(view.status)} {short_date(last)}".strip()]
	if view.valid_till and view.status == "Price Sent":
		parts.append(_("valid till {0}").format(short_date(view.valid_till)))
	return " · ".join(p for p in parts if p)


def download_url(name, token, fmt):
	query = urlencode({"name": name, "token": token, "format": fmt})
	return f"/api/method/quoteshop.quoteshop_enquiry.quote_view.download_quote?{query}"
