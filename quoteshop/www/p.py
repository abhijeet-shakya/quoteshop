from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, strip_html_tags
from frappe.utils.html_utils import sanitize_html

from quoteshop.quoteshop_website.context import setup, with_prices


def get_context(context):
	from quoteshop.quoteshop_catalog import catalog

	try:
		product = catalog.product(frappe.form_dict.get("route") or "")
	except frappe.DoesNotExistError:
		raise frappe.PageDoesNotExistError
	qs = setup(
		context,
		"product",
		title=product["item_name"],
		description=product["short_description"] or product["description"] or product["item_name"],
	)
	enquiry = frappe.get_cached_doc("QS Enquiry Settings")
	published = {c["route"] for c in catalog.categories()}
	p = with_prices([product])[0]
	p["related"] = with_prices(product["related"])
	text = strip_html_tags(p["description"] or "").strip()
	# ERPNext copies item_name into an empty description: show the short description instead.
	p["description_html"] = (
		sanitize_html(p["description"])
		if text and text != p["item_name"]
		else frappe.utils.escape_html(p["short_description"] or "")
	)
	context.p = p
	context.group_url = f"/c/{p['group_route']}" if p["group_route"] in published else None
	context.tier2 = cint(enquiry.bulk_tier_2) or 2
	context.tier3 = cint(enquiry.bulk_tier_3) or 5
	context.ask_url = (
		qs.whatsapp_url
		+ "?text="
		+ quote(_("Hi, I have a question about {0} ({1})").format(p["item_name"], p["item_code"]))
		if qs.whatsapp_url
		else None
	)
