"""Shared context for the QuoteShop website pages (settings → template values)."""

import re

import frappe
from frappe.utils import cint, get_url, strip_html_tags

DEFAULT_ACCENT = "#146B47"
DEFAULT_SECTIONS = ("Hero", "Promo tiles", "Trust line", "How it works", "Categories", "Products")
# Exact soft/ink tints from the design for its palette: (light soft, light ink, dark soft, dark ink).
DESIGN_TINTS = {
	"#146B47": ("#E4F1EA", "#0E5236", "#173A2C", "#8FDDB8"),
	"#2F5FC4": ("#E6EDFB", "#1E438F", "#1C2B4A", "#A9C2F5"),
	"#B4372A": ("#F8E7E4", "#8A2A20", "#3D211D", "#F2A79C"),
	"#121413": ("#F0F0EC", "#121413", "#2C312E", "#EEF0EC"),
}


def setup(context, page: str, title: str | None = None, description: str | None = None) -> dict:
	"""Fill `context.qs` with everything qs_base.html and the partials need; returns it."""
	s = frappe.get_cached_doc("QS Store Settings")
	name = s.business_name or "QuoteShop"
	accent = _hex(s.brand_color) or DEFAULT_ACCENT
	default_theme = (s.default_theme or "Auto").lower()
	digits = re.sub(r"\D", "", s.whatsapp_number or "")
	path = (frappe.local.request.path if getattr(frappe.local, "request", None) else "/") or "/"
	context.no_breadcrumbs = 1
	context.qs = frappe._dict(
		page=page,
		title=f"{title} · {name}" if title else name,
		description=_plain(description) or name,
		canonical=get_url(path),
		lang=getattr(frappe.local, "lang", None) or "en",
		name=name,
		short_name=s.short_name or "".join(w[0] for w in name.split()[:3]).upper(),
		logo=s.logo,
		favicon=s.favicon,
		accent=accent,
		tints=DESIGN_TINTS.get(accent) or _tints(accent),
		theme="dark" if default_theme == "dark" else "light",
		default_theme=default_theme,
		allow_switch=cint(s.allow_theme_switch),
		search_placeholder=s.search_placeholder or "Search products",
		quote_label=s.quote_button_label or "Quote",
		price_suffix=s.price_suffix or "per piece",
		show_prices=cint(s.show_starting_prices),
		response_time=s.response_time_text,
		whatsapp_number=s.whatsapp_number,
		whatsapp_url=f"https://wa.me/{digits}" if digits else None,
		email=s.email,
		address=" ".join((s.address or "").split()),
		q=(frappe.form_dict.get("q") or "").strip()[:100],
	)
	return context.qs


def with_prices(cards: list[dict]) -> list[dict]:
	"""Copy catalog cards adding `price` (formatted starting price or None)."""
	from quoteshop.quoteshop_catalog.catalog import format_price

	return [
		{
			**c,
			"price": format_price(c["starting_price"], c["currency"])
			if c["starting_price"] is not None
			else None,
		}
		for c in cards
	]


def listing(context, *, category: str | None = None, q: str | None = None) -> dict:
	"""Catalog listing for the grid pages (page from ?page=N); unknown category → 404."""
	from quoteshop.quoteshop_catalog.catalog import get_categories, list_products

	try:
		result = list_products(category=category, q=q, page=cint(frappe.form_dict.get("page")) or 1)
	except frappe.DoesNotExistError:
		raise frappe.PageDoesNotExistError
	page = result["page"]
	base = {"q": q} if q else {}
	return frappe._dict(
		items=with_prices(result["items"]),
		total=result["total"],
		prev_url=_page_url(base, page - 1) if page > 1 else None,
		next_url=_page_url(base, page + 1) if result["has_more"] else None,
		categories=get_categories(),
	)


def _page_url(params: dict, page: int) -> str:
	from urllib.parse import urlencode

	query = urlencode({**params, **({"page": page} if page > 1 else {})})
	return f"{frappe.local.request.path}?{query}" if query else frappe.local.request.path


def _plain(text: str | None) -> str:
	return " ".join(strip_html_tags(text or "").split())[:160]


def _hex(value: str | None) -> str | None:
	value = (value or "").strip()
	if re.fullmatch(r"#[0-9A-Fa-f]{3}", value):
		value = "#" + "".join(ch * 2 for ch in value[1:])
	return value.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else None


def _mix(a: str, b: str, weight: float) -> str:
	"""`weight` of colour a mixed with colour b (sRGB, like CSS color-mix)."""
	pa = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
	pb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
	return "#" + "".join(f"{round(x * weight + y * (1 - weight)):02X}" for x, y in zip(pa, pb, strict=True))


def _tints(accent: str) -> tuple[str, str, str, str]:
	# ponytail: fixed mix ratios fitted to the design palette; tune here if a brand colour reads poorly.
	return (
		_mix(accent, "#FFFFFF", 0.12),
		_mix(accent, "#000000", 0.72),
		_mix(accent, "#171A18", 0.4),
		_mix(accent, "#FFFFFF", 0.4),
	)
