"""Phase 7: passwordless buyer portal (CONTRACTS §7.2)."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt

from quoteshop.quoteshop_enquiry import otp
from quoteshop.quoteshop_enquiry.api import colour_swatches, find_or_create_contact

BUYER_DOMAIN = "@buyers.invalid"  # users QuoteShop creates for OTP login
REQUEST_FIELDS = [
	"name",
	"status",
	"creation",
	"current_version",
	"valid_till",
	"total_listed",
	"total_offered",
	"total_saved",
	"saved_pct",
	"line_count",
	"unit_count",
	"sales_order",
]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def portal_login(mobile: str, otp_token: str) -> dict:
	"""Log in the Website User of the number proven by `otp_token` (created on first login)."""
	mobile = otp.normalize_mobile(mobile)
	if otp.verified_mobile(otp_token) != mobile:
		frappe.throw(_("Please verify your mobile number again."), frappe.AuthenticationError)

	contact = frappe.get_doc("Contact", find_or_create_contact(mobile, mobile))
	if contact.user and not contact.user.endswith(BUYER_DOMAIN):
		# an account QuoteShop didn't create (e.g. an ERPNext portal user) keeps its own sign-in
		frappe.throw(
			_("This number belongs to an existing account. Please sign in with your email and password."),
			frappe.AuthenticationError,
		)
	user = contact.user or f"{mobile.lstrip('+')}{BUYER_DOMAIN}"
	user_type = frappe.db.get_value("User", user, "user_type")
	if user_type is None:
		# frappe's User.on_update creates a Contact for any user without a Contact Email row
		# of that address, which would leave two Contacts on one user; give ours the email first
		contact.add_email(user)
		contact.save(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": contact.first_name or mobile,
				"user_type": "Website User",
				"send_welcome_email": 0,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	elif user_type != "Website User" or not frappe.db.get_value("User", user, "enabled"):
		# never hand a desk (or disabled) account to an OTP login
		frappe.throw(_("This number can't be used to sign in here."), frappe.AuthenticationError)
	if contact.user != user:
		contact.reload()  # frappe's create_contact may have just saved it
		contact.user = user
		contact.save(ignore_permissions=True)

	frappe.local.login_manager.login_as(user)
	return {"redirect": "/account"}


@frappe.whitelist(methods=["GET", "POST"])
def get_account_data() -> dict:
	"""The signed-in buyer's own orders and requests (via Contact → Customer)."""
	contact = _buyer_contact()
	customers = _customers(contact)
	requests = frappe.get_all(
		"QS Enquiry", filters={"contact": contact}, fields=REQUEST_FIELDS, order_by="creation desc", limit=200
	)
	orders = (
		frappe.get_all(
			"Sales Order",
			filters={"customer": ("in", customers), "docstatus": ("<", 2)},
			fields=[
				"name",
				"transaction_date",
				"status",
				"currency",
				"net_total",
				"grand_total",
				"qs_enquiry",
				"qs_version",
			],
			order_by="transaction_date desc, creation desc",
			limit=200,
		)
		if customers
		else []
	)
	lines_by_order: dict[str, list] = {}
	for line in (
		frappe.get_all(
			"Sales Order Item",
			filters={"parenttype": "Sales Order", "parent": ("in", [o.name for o in orders])},
			fields=[
				"parent",
				"item_code",
				"item_name",
				"qty",
				"uom",
				"price_list_rate",
				"rate",
				"amount",
				"qs_requested_qty",
				"qs_colour",
			],
			order_by="idx asc",
		)
		if orders
		else []
	):
		line["colour"] = line.pop("qs_colour") or ""
		lines_by_order.setdefault(line.pop("parent"), []).append(line)

	total_listed = total_final = 0.0
	for order in orders:
		order["lines"] = lines_by_order.get(order.name, [])
		order["listed"] = sum(flt(line.price_list_rate) * flt(line.qty) for line in order["lines"])
		order["saved"] = order["listed"] - flt(order.net_total)
		order["saved_pct"] = flt(order["saved"] / order["listed"] * 100, 2) if order["listed"] else 0
		total_listed += order["listed"]
		total_final += flt(order.net_total)

	return {
		"orders": orders,
		"requests": requests,
		"totals": {
			"orders": len(orders),
			"requests": len(requests),
			"open_requests": sum(
				r.status in ("Requested", "Price Sent", "Changes Requested") for r in requests
			),
			"listed": total_listed,
			"final": total_final,
			"saved": total_listed - total_final,
			"saved_pct": flt((total_listed - total_final) / total_listed * 100, 2) if total_listed else 0,
		},
	}


@frappe.whitelist(methods=["POST"])
def reorder(sales_order: str) -> dict:
	"""Lines of one of the buyer's own orders that are still published, for the quote list.

	A line keeps its colour only while the item still has that colour, else the colour is ""."""
	customers = _customers(_buyer_contact())
	if not frappe.db.exists("Sales Order", {"name": sales_order, "customer": ("in", customers or [""])}):
		frappe.throw(_("Order not found."), frappe.PermissionError)
	qty: dict[tuple[str, str], float] = {}
	for line in frappe.get_all(
		"Sales Order Item",
		filters={"parenttype": "Sales Order", "parent": sales_order},
		fields=["item_code", "qty", "qs_colour"],
	):
		key = (line.item_code, line.qs_colour or "")
		qty[key] = qty.get(key, 0) + flt(line.qty)
	codes = list({code for code, _colour in qty})
	published = set(
		frappe.get_all(
			"Item",
			filters={"name": ("in", codes or [""]), "qs_published": 1, "disabled": 0, "has_variants": 0},
			pluck="name",
		)
	)
	colours = colour_swatches(codes)
	merged: dict[tuple[str, str], float] = {}
	for (code, colour), q in qty.items():
		if code in published:
			key = (code, colour if colour in colours.get(code, {}) else "")
			merged[key] = merged.get(key, 0) + q
	return {
		"items": [{"item_code": code, "qty": q, "colour": colour} for (code, colour), q in merged.items()]
	}


def _buyer_contact() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	contact = frappe.db.get_value("Contact", {"user": frappe.session.user})
	if not contact:
		frappe.throw(_("No buyer account is linked to this user."), frappe.PermissionError)
	return contact


def _customers(contact: str) -> list[str]:
	return frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		pluck="link_name",
	)
