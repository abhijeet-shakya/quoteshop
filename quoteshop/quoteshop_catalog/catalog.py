import hashlib
import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urlsplit

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, fmt_money, get_files_path, nowdate

from quoteshop.quoteshop_catalog.cache import PREFIX

TTL = 86400
SIZES = ("thumb", "medium", "large")
MAX_QUERY = 100
VISIBLE = "qs_published = 1 and disabled = 0 and has_variants = 0"

# One statement: the page of items (with the full count via a window function) joined to the starting
# Item Price (CONTRACTS §2.4, newest valid_from) and the first photo; correlated lookups run per page row.
CARDS_SQL = """
select i.name, i.item_name, i.qs_route, i.item_group, g.qs_route as group_route,
	i.qs_short_description, i.qs_min_qty, i.qs_hide_price, i.qs_lead_time, i.stock_uom, i.description,
	i.total, ip.price_list_rate, coalesce(ip.currency, pl.currency) as currency,
	p.image, p.thumb, p.medium, p.large, p.alt_text
from (
	select name, item_name, qs_route, item_group, qs_short_description, qs_min_qty, qs_hide_price,
		qs_lead_time, stock_uom, description, qs_display_order, count(*) over () as total
	from `tabItem`
	where {where}
	order by qs_display_order, item_name, name
	{limit}
) i
left join `tabItem Group` g on g.name = i.item_group
left join `tabPrice List` pl on pl.name = %(price_list)s
left join `tabItem Price` ip on ip.name = (
	select x.name from `tabItem Price` x
	where x.item_code = i.name and x.price_list = %(price_list)s and x.selling = 1
		and ifnull(x.customer, '') = '' and x.uom = i.stock_uom
		and ifnull(x.valid_from, '1900-01-01') <= %(today)s
		and (x.valid_upto is null or x.valid_upto >= %(today)s)
	order by ifnull(x.valid_from, '1900-01-01') desc, x.creation desc
	limit 1
)
left join `tabQS Item Photo` p on p.name = (
	select y.name from `tabQS Item Photo` y
	where y.parent = i.name and y.parenttype = 'Item' and y.parentfield = 'qs_photos'
	order by y.idx
	limit 1
)
order by i.qs_display_order, i.item_name, i.name
"""


# Guest GET APIs are rate limited per IP. rate_limit counts every call made during a web request,
# page renders included, so the www pages call the undecorated products/product/categories below.
@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=600, seconds=3600)
def list_products(category: str | None = None, q: str | None = None, page: int | str = 1) -> dict:
	"""Published product cards, filtered by category route (incl. descendants) and search text, paginated."""
	return products(category, q, page)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=600, seconds=3600)
def get_product(route: str) -> dict:
	"""Product page payload: card fields plus description, photos, specs, related cards, lead time, UOM."""
	return product(route)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=600, seconds=3600)
def get_categories() -> list[dict]:
	"""Published Item Groups, flat, ordered by display order then name."""
	return categories()


def products(category: str | None = None, q: str | None = None, page: int | str = 1) -> dict:
	"""list_products without the rate limit (for page renders)."""
	q = (q or "").strip()[:MAX_QUERY]
	page = max(cint(page), 1)
	params = {"category": category or None, "q": q, "page": page}
	if q:
		# ponytail: searches are never cached (free text = unbounded keys); add a short-TTL cache if
		# search load ever shows up in the slow log.
		return _list_products(**params)
	key = f"{PREFIX}list:{hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()}"
	# empty pages (past the end, empty category) are not cached, so ?page=N can't fill redis
	return _cached(key, lambda: _list_products(**params), keep=lambda result: bool(result["items"]))


def _list_products(category: str | None, q: str, page: int) -> dict:
	settings = _settings()
	page_size = cint(settings.products_per_page) or 24
	where, values = [VISIBLE], {}
	if category:
		group = frappe.db.get_value(
			"Item Group", {"qs_route": category, "qs_published": 1}, ["lft", "rgt"], as_dict=True
		)
		if not group:
			raise frappe.DoesNotExistError(_("Category not found"))
		where.append(
			"item_group in (select name from `tabItem Group` where lft >= %(lft)s and rgt <= %(rgt)s)"
		)
		values.update(group)
	if q:
		where.append("(item_name like %(q)s or name like %(q)s or qs_short_description like %(q)s)")
		values["q"] = f"%{escape_like(q)}%"

	offset = (page - 1) * page_size
	rows = _card_rows(" and ".join(where), values, settings, limit=page_size, offset=offset)
	if rows:
		total = rows[0].total
	elif page > 1:
		total = frappe.db.sql(f"select count(*) from `tabItem` where {' and '.join(where)}", values)[0][0]
	else:
		total = 0
	return {
		"items": [_card(row, settings) for row in rows],
		"total": total,
		"page": page,
		"page_size": page_size,
		"has_more": offset + len(rows) < total,
	}


def product(route: str) -> dict:
	"""get_product without the rate limit; unknown routes raise (never cached)."""
	return _cached(f"{PREFIX}product:{route}", lambda: _get_product(route))


def _get_product(route: str) -> dict:
	settings = _settings()
	rows = _card_rows(f"{VISIBLE} and qs_route = %(route)s", {"route": route}, settings)
	if not rows:
		raise frappe.DoesNotExistError(_("Product not found"))
	row = rows[0]
	child = "where parent = %s and parenttype = 'Item' and parentfield = %s order by idx"
	photos = frappe.db.sql(
		f"select image, thumb, medium, large, alt_text from `tabQS Item Photo` {child}",
		(row.name, "qs_photos"),
		as_dict=True,
	)
	specs = frappe.db.sql(
		f"select label, value from `tabQS Item Spec` {child}", (row.name, "qs_specs"), as_dict=True
	)
	related = _card_rows(
		f"{VISIBLE} and name in (select item from `tabQS Related Item`"
		" where parent = %(item)s and parenttype = 'Item' and parentfield = 'qs_related')",
		{"item": row.name},
		settings,
	)
	return {
		**_card(row, settings),
		"description": row.description,
		"photos": [_photo(photo, row.item_name) for photo in photos if photo.image],
		"specs": [{"label": spec.label, "value": spec.value} for spec in specs],
		"related": [_card(r, settings) for r in related],
		"lead_time": cint(row.qs_lead_time),
		"uom": row.stock_uom,
	}


def categories() -> list[dict]:
	"""get_categories without the rate limit."""
	return _cached(
		f"{PREFIX}categories",
		lambda: frappe.get_all(
			"Item Group",
			filters={"qs_published": 1},
			fields=["name", "qs_route as route", "qs_image as image", "qs_display_order as display_order"],
			order_by="qs_display_order asc, name asc",
		),
	)


def format_price(amount: float, currency: str | None = None) -> str:
	"""Website money: system number format, no decimals for whole amounts, symbol without a space."""
	amount = flt(amount, 2)
	number = fmt_money(amount, precision=0 if amount.is_integer() else 2)
	if not currency:
		return number
	symbol, on_right = frappe.get_cached_value("Currency", currency, ["symbol", "symbol_on_right"]) or (
		None,
		0,
	)
	return f"{number} {symbol or currency}" if on_right else f"{symbol or currency}{number}"


def get_image_size(url: str | None) -> tuple[int, int] | None:
	"""(width, height) of a local public/private file URL, cached with the catalog cache."""
	if not url:
		return None
	key = f"{PREFIX}imgsize:{hashlib.sha1(url.encode()).hexdigest()}"
	size = _cached(key, lambda: list(_read_image_size(url) or ()))
	return tuple(size) if size else None


def _read_image_size(url: str) -> tuple[int, int] | None:
	from PIL import Image

	path = file_path(url)
	if not path:
		return None
	try:
		with Image.open(path) as image:
			return image.size
	except OSError:
		return None


def file_path(url: str | None) -> str | None:
	"""Disk path of a site file URL (/files/… or /private/files/…), None for remote or missing files."""
	path = unquote(urlsplit(url or "").path)
	for prefix, is_private in (("/files/", False), ("/private/files/", True)):
		if path.startswith(prefix):
			name = os.path.basename(path)
			full = get_files_path(name, is_private=is_private)
			return full if name and os.path.isfile(full) else None
	return None


def escape_like(text: str) -> str:
	return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _settings():
	return frappe.get_cached_doc("QS Store Settings")


def _cached(key: str, build: Callable[[], Any], keep: Callable[[Any], bool] | None = None) -> Any:
	value = frappe.cache.get_value(key, expires=True)
	if value is None:
		value = build()
		if keep is None or keep(value):
			frappe.cache.set_value(key, value, expires_in_sec=TTL)
	return value


def _card_rows(where: str, values: dict, settings, limit: int | None = None, offset: int = 0) -> list:
	limit_sql = "limit %(limit)s offset %(offset)s" if limit else ""
	return frappe.db.sql(
		CARDS_SQL.format(where=where, limit=limit_sql),
		{
			**values,
			"price_list": settings.starting_price_list,
			"today": nowdate(),
			"limit": limit,
			"offset": offset,
		},
		as_dict=True,
	)


def _card(row, settings) -> dict:
	show_price = settings.show_starting_prices and not row.qs_hide_price and row.price_list_rate is not None
	return {
		"item_code": row.name,
		"item_name": row.item_name,
		"route": row.qs_route,
		"item_group": row.item_group,
		"group_route": row.group_route,
		"short_description": row.qs_short_description,
		"min_qty": max(cint(row.qs_min_qty), 1),
		"image": _photo(row, row.item_name) if row.image else None,
		"starting_price": flt(row.price_list_rate) if show_price else None,
		"currency": row.currency,
	}


def _photo(row, item_name: str) -> dict:
	return {**{size: row.get(size) or row.image for size in SIZES}, "alt": row.alt_text or item_name}
