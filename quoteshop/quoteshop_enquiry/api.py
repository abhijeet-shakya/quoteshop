"""Phase 3 guest APIs: quote list, paste import, OTP and enquiry submission (CONTRACTS §7.2)."""

import math
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, getdate, nowdate, validate_email_address

from quoteshop.quoteshop_enquiry import crm, whatsapp
from quoteshop.quoteshop_enquiry import otp as otp_service

MAX_LINES = 500
MAX_QTY = 100_000
MAX_PASTE_BYTES = 50 * 1024
MAX_PASTE_LINE = 200
# split, never backtrack: a "name<sep>qty" regex was quadratic on long separator runs (ReDoS)
PASTE_SEPARATORS = re.compile(r"[\t,; ]+")


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=600, seconds=3600)
def get_quote_items(item_codes: list[str | dict] | str) -> list[dict]:
	"""Cards (CONTRACTS §7.1) for the published items among `item_codes`, in the given order.

	Entries are item codes or `{item_code, colour?}`; one card per (item, colour), each with `colour`
	("" when none) and `swatch` ("#RRGGBB" of that colour, "" when none). A colour that is not one of
	the item's colours (e.g. removed since it was added) resolves to colour "" instead of failing."""
	entries = parse_json_arg(item_codes)
	if not isinstance(entries, list) or len(entries) > MAX_LINES:
		frappe.throw(_("item_codes must be a list of at most {0} items.").format(MAX_LINES))
	keys = []
	for entry in entries:
		if isinstance(entry, str):
			entry = {"item_code": entry}
		if not isinstance(entry, dict) or not isinstance(entry.get("item_code"), str):
			frappe.throw(_("item_codes must be a list of item codes."))
		keys.append((entry["item_code"], _colour_arg(entry.get("colour"))))
	codes = list({code for code, _colour in keys})
	cards = {card["item_code"]: card for card in get_cards(codes)}
	colours = colour_swatches(codes)
	result = {}
	for code, colour in keys:
		if code in cards:
			colour = colour if colour in colours.get(code, {}) else ""  # display path: drop a stale colour
			result.setdefault(
				(code, colour),
				{**cards[code], "colour": colour, "swatch": colours.get(code, {}).get(colour, "")},
			)
	return list(result.values())


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=120, seconds=3600)
def parse_quote_paste(text: str) -> dict:
	"""Match "<code or exact name><tab|,|;|space><qty>" lines against published items."""
	if not isinstance(text, str):
		frappe.throw(_("Paste text is required."))
	if len(text.encode()) > MAX_PASTE_BYTES:
		frappe.throw(_("Paste at most {0} KB of text.").format(MAX_PASTE_BYTES // 1024))
	lines = [line for line in text.splitlines() if line.strip()]
	if len(lines) > MAX_LINES:
		frappe.throw(_("Paste at most {0} lines.").format(MAX_LINES))

	parsed, unmatched = [], []
	for line in lines:
		if len(line) > MAX_PASTE_LINE:
			unmatched.append({"line": line[:MAX_PASTE_LINE] + "…", "reason": _("Line too long")})
			continue
		*name, qty = PASTE_SEPARATORS.split(line.strip())
		qty = _paste_qty(qty)
		key = " ".join(name).strip("\"'")
		if not key or not qty:
			unmatched.append({"line": line, "reason": _("Expected item code or name followed by a quantity")})
		else:
			parsed.append((line, key, qty))

	keys = list({key for _line, key, _qty in parsed})
	found = (
		frappe.get_all(
			"Item",
			filters={"qs_published": 1, "disabled": 0, "has_variants": 0},
			or_filters={"name": ("in", keys), "item_name": ("in", keys)},
			fields=["name", "item_name", "qs_min_qty"],
		)
		if keys
		else []
	)
	lookup = {}
	for item in found:
		lookup.setdefault(item.item_name.casefold(), item)
	for item in found:  # an exact code wins over a name
		lookup[item.name.casefold()] = item

	matched: dict[str, dict] = {}
	for line, key, qty in parsed:
		item = lookup.get(key.casefold())
		if not item:
			unmatched.append({"line": line, "reason": _("No published item with this code or name")})
			continue
		row = matched.setdefault(item.name, {"item_code": item.name, "item_name": item.item_name, "qty": 0})
		row["qty"] = max(row["qty"] + qty, _min_qty(item.qs_min_qty))
	return {"matched": list(matched.values()), "unmatched": unmatched}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="mobile", ip_based=False, limit=5, seconds=3600)
@rate_limit(limit=20, seconds=3600)
def send_otp(mobile: str) -> dict:
	"""Send a 6-digit WhatsApp code to `mobile`."""
	otp_service.issue(otp_service.normalize_mobile(mobile))
	return {"sent": True, "expires_in": otp_service.OTP_TTL}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="mobile", ip_based=False, limit=10, seconds=3600)
@rate_limit(limit=30, seconds=3600)
def verify_otp(mobile: str, otp: str) -> dict:
	"""Verify the code; the returned otp_token proves the number for 30 minutes."""
	return {"verified": True, "otp_token": otp_service.verify(otp_service.normalize_mobile(mobile), otp)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def submit_enquiry(data: dict | str) -> dict:
	"""Create a QS Enquiry (+ Contact, CRM Deal) from the website quote form in one transaction."""
	data = parse_json_arg(data)
	if not isinstance(data, dict):
		frappe.throw(_("Invalid enquiry data."))
	settings = frappe.get_cached_doc("QS Enquiry Settings")

	if settings.login_mode == "Required" and frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to send an enquiry."), frappe.PermissionError)
	mobile = otp_service.normalize_mobile(data.get("mobile"))
	if settings.otp_required and not is_mobile_verified(mobile, data.get("otp_token")):
		frappe.throw(_("Please verify your mobile number."), frappe.PermissionError)

	buyer = _validate_buyer(data, settings)
	lines = build_lines(data.get("items"))
	contact = find_or_create_contact(mobile, buyer["buyer_name"], buyer["email"], buyer["business_name"])
	customer = customer_of_contact(contact)

	doc = frappe.get_doc(
		{
			"doctype": "QS Enquiry",
			"status": "Requested",
			"mobile": mobile,
			**buyer,
			"answers": _validate_answers(data.get("answers"), settings),
			"items": lines,
			"contact": contact,
			"customer": customer,
			"assigned_to": _default_assignee(buyer["buyer_type"], customer, settings),
		}
	)
	# items/contact/customer are validated above; link validation would add one query per line
	doc.flags.ignore_links = True
	doc.insert(ignore_permissions=True)
	crm.create_deal(doc)
	whatsapp.queue_message(doc.name, "enquiry_received_buyer", 0)
	whatsapp.queue_message(doc.name, "enquiry_alert_sales", 0)
	return {"name": doc.name}


def is_mobile_verified(mobile: str, otp_token: str | None) -> bool:
	if otp_service.verified_mobile(otp_token) == mobile:
		return True
	# a signed-in buyer (portal) has already proven the number linked to their Contact
	user = frappe.session.user
	return user != "Guest" and frappe.db.exists("Contact", {"user": user, "mobile_no": mobile}) is not None


def build_lines(items, existing: dict | None = None) -> list[dict]:
	"""Validated QS Enquiry Item rows for [{item_code, qty, colour?}] (duplicates merged, listed_rate snapshot).

	A line is an (item_code, colour) pair; colour must be one of the item's colour labels or empty.
	`existing` ((item_code, colour) -> row dict) keeps already-quoted rows and only updates their quantity."""
	if not isinstance(items, list) or not items:
		frappe.throw(_("Add at least one item."))
	if len(items) > MAX_LINES:
		frappe.throw(_("A quote can have at most {0} items.").format(MAX_LINES))
	qty_by_key: dict[tuple[str, str], float] = {}
	for row in items:
		if not isinstance(row, dict) or set(row) - {"item_code", "qty", "colour"}:
			frappe.throw(_("Each item may only have an item code, a quantity and a colour."))
		code = row.get("item_code")
		if not isinstance(code, str) or not code:
			frappe.throw(_("Item code is required."))
		key = (code, _colour_arg(row.get("colour")))
		qty = qty_by_key.get(key, 0) + flt(row.get("qty"))
		if not math.isfinite(qty) or qty > MAX_QTY:
			frappe.throw(_("Quantity for {0} must be a number up to {1}.").format(code, MAX_QTY))
		qty_by_key[key] = qty
	codes = list({code for code, _colour in qty_by_key})

	existing = existing or {}
	items_meta = {
		item.name: item
		for item in frappe.get_all(
			"Item",
			filters={"name": ("in", codes)},
			fields=[
				"name",
				"item_name",
				"stock_uom",
				"qs_min_qty",
				"qs_published",
				"disabled",
				"has_variants",
			],
		)
	}
	# already-quoted lines stay even if the item was unpublished since; new lines must be published
	missing = [
		code
		for code, colour in qty_by_key
		if (code, colour) not in existing
		and not (
			(item := items_meta.get(code))
			and item.qs_published
			and not item.disabled
			and not item.has_variants
		)
	]
	if missing:
		frappe.throw(_("These items are not available: {0}").format(", ".join(dict.fromkeys(missing[:20]))))
	new_codes = [code for code, colour in qty_by_key if (code, colour) not in existing]
	colours = colour_swatches(new_codes)
	for code, colour in qty_by_key:
		if (code, colour) not in existing and colour and colour not in colours.get(code, {}):
			frappe.throw(_("{0} is not available in {1}.").format(items_meta[code].item_name, colour))
	prices = starting_prices(new_codes)

	lines = []
	for (code, colour), qty in qty_by_key.items():
		key = (code, colour)
		if key in existing and qty == flt(existing[key]["requested_qty"]):
			lines.append(existing[key])  # unchanged: keeps the salesperson's offered qty (e.g. partial)
			continue
		item = items_meta.get(code)
		minimum = _min_qty(item.qs_min_qty if item else 1)
		if qty < minimum:
			frappe.throw(_("Minimum quantity for {0} is {1}.").format(code, minimum))
		if key in existing:
			lines.append({**existing[key], "requested_qty": qty, "offered_qty": qty})
			continue
		lines.append(
			{
				"item_code": code,
				"item_name": item.item_name,
				"colour": colour,
				"uom": item.stock_uom,
				"requested_qty": qty,
				"offered_qty": qty,
				"listed_rate": prices.get(code, {}).get("rate", 0.0),
				"availability": "Available",
			}
		)
	return lines


def colour_swatches(item_codes: list[str]) -> dict[str, dict[str, str]]:
	"""{item_code: {colour label: swatch}} from the items' QS Item Colour rows — one query."""
	result: dict[str, dict[str, str]] = {}
	if not item_codes:
		return result
	for row in frappe.get_all(
		"QS Item Colour",
		filters={"parenttype": "Item", "parentfield": "qs_colours", "parent": ("in", item_codes)},
		fields=["parent", "label", "swatch"],
		order_by="idx asc",
	):
		result.setdefault(row.parent, {})[row.label] = row.swatch
	return result


def find_or_create_contact(
	mobile: str, name: str, email: str | None = None, business_name: str | None = None
) -> str:
	"""Contact by exact E.164 `mobile_no` (CONTRACTS §2.5), else a new one."""
	if contact := frappe.db.get_value("Contact", {"mobile_no": mobile}):
		return contact
	contact = frappe.new_doc("Contact")
	contact.first_name = name
	contact.company_name = business_name
	contact.add_phone(mobile, is_primary_mobile_no=1)
	if email:
		contact.add_email(email, is_primary=1)
	contact.insert(ignore_permissions=True)
	return contact.name


def customer_of_contact(contact: str) -> str | None:
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


def starting_prices(item_codes: list[str]) -> dict[str, dict]:
	"""{item_code: {"rate", "currency"}} from the starting price list (CONTRACTS §2.4, newest valid_from)."""
	if not item_codes:
		return {}
	price_list = frappe.get_cached_doc("QS Store Settings").starting_price_list
	today = nowdate()
	rows = frappe.db.sql(
		"""
		select ip.item_code, ip.price_list_rate as rate, ip.currency
		from `tabItem Price` ip
		join `tabItem` i on i.name = ip.item_code and ip.uom = i.stock_uom
		where ip.price_list = %(price_list)s and ip.selling = 1 and ifnull(ip.customer, '') = ''
			and ifnull(ip.valid_from, '1900-01-01') <= %(today)s
			and (ip.valid_upto is null or ip.valid_upto >= %(today)s)
			and ip.item_code in %(codes)s
		order by ip.valid_from desc, ip.modified desc
		""",
		{"price_list": price_list, "today": today, "codes": tuple(item_codes)},
		as_dict=True,
	)
	prices: dict[str, dict] = {}
	for row in rows:
		prices.setdefault(row.item_code, {"rate": flt(row.rate), "currency": row.currency})
	return prices


def get_cards(item_codes: list[str]) -> list[dict]:
	"""Catalog cards (CONTRACTS §7.1) for the published items among `item_codes` — one query."""
	from quoteshop.quoteshop_catalog.catalog import VISIBLE, _card, _card_rows

	if not item_codes:
		return []
	store = frappe.get_cached_doc("QS Store Settings")
	rows = _card_rows(f"{VISIBLE} and name in %(codes)s", {"codes": tuple(item_codes)}, store)
	return [_card(row, store) for row in rows]


def _validate_buyer(data: dict, settings) -> dict:
	buyer_name = _text(data.get("buyer_name"), 140)
	if not buyer_name:
		frappe.throw(_("Please enter your name."))
	email = _text(data.get("email"), 140)
	if email:
		validate_email_address(email, throw=True)
	pincode = _text(data.get("pincode"), 12) if settings.show_pincode else None
	if settings.show_pincode and settings.require_pincode and not pincode:
		frappe.throw(_("Please enter your pincode."))
	buyer_type = _text(data.get("buyer_type"), 140)
	if buyer_type and buyer_type not in {row.label for row in settings.buyer_types}:
		frappe.throw(_("Unknown buyer type."))
	return {
		"buyer_name": buyer_name,
		"email": email,
		"business_name": _text(data.get("business_name"), 140) if settings.show_business_name else None,
		"pincode": pincode,
		"buyer_type": buyer_type,
		"notes": _text(data.get("notes"), 2000) if settings.show_notes else None,
	}


def _validate_answers(answers, settings) -> list[dict]:
	given = {}
	for row in answers if isinstance(answers, list) else []:
		if isinstance(row, dict) and isinstance(row.get("question"), str):
			given[row["question"]] = row.get("value")

	rows = []
	for question in settings.questions:
		value = given.get(question.label)
		value = "" if value is None else str(value).strip()[:2000]
		if question.fieldtype == "Check":
			value = "1" if value in ("1", "true", "True", "on") else "0"
		if question.required and (not value or (question.fieldtype == "Check" and value == "0")):
			frappe.throw(_("Please answer: {0}").format(question.label))
		if value and question.fieldtype == "Select":
			options = [opt.strip() for opt in (question.options or "").splitlines() if opt.strip()]
			if value not in options:
				frappe.throw(_("Invalid answer for: {0}").format(question.label))
		if value and question.fieldtype == "Date":
			try:
				value = str(getdate(value))
			except Exception:
				frappe.throw(_("Invalid date for: {0}").format(question.label))
		if value:
			rows.append({"question": question.label, "value": value})
	return rows


def _default_assignee(buyer_type: str | None, customer: str | None, settings) -> str | None:
	"""Buyer type default_assignee → Customer.account_manager → None (CRM Assignment Rule decides)."""
	for row in settings.buyer_types:
		if buyer_type and row.label == buyer_type and row.default_assignee:
			return row.default_assignee
	return frappe.db.get_value("Customer", customer, "account_manager") if customer else None


def parse_json_arg(value):
	"""Decode a JSON string argument; malformed input is a ValidationError, not an HTTP 500."""
	if not isinstance(value, str):
		return value
	try:
		return frappe.parse_json(value)
	except ValueError:  # orjson.JSONDecodeError subclasses ValueError
		frappe.throw(_("Invalid JSON."))


def _colour_arg(value) -> str:
	if value is not None and not isinstance(value, str):
		frappe.throw(_("Invalid colour."))
	return value or ""


def _text(value, max_length: int) -> str | None:
	if value is None:
		return None
	if not isinstance(value, str | int | float):
		frappe.throw(_("Invalid value."))
	return str(value).strip()[:max_length] or None


def _paste_qty(value: str) -> float | None:
	"""A positive, finite quantity up to MAX_QTY, else None."""
	try:
		qty = float(value)
	except ValueError:
		return None
	return qty if math.isfinite(qty) and 0 < qty <= MAX_QTY else None


def _min_qty(value) -> int:
	return max(1, cint(value))
