import re
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
	# Gallery label = the photo's own alt text; a photo that only inherited the item name (CONTRACTS §7.1b) is "Photo n".
	# With several photos alt = label, so a screen reader tells them apart.
	many = len(p["photos"]) > 1
	p["photos"] = [
		{
			**ph,
			"label": (
				label := ph["alt"] if ph["alt"] and ph["alt"] != p["item_name"] else _("Photo {0}").format(i)
			),
			"alt": label if many else ph["alt"],
		}
		for i, ph in enumerate(p["photos"], 1)
	]
	# Colours (CONTRACTS §11): ?colour=<label> (case-insensitive) else the first; that colour's photos first,
	# then general ones; photos of other colours stay in the page, hidden (public/js/qs/gallery.js re-orders).
	for c in p["colours"]:
		c["swatch"] = c["swatch"] if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", c["swatch"] or "") else "#9AA09B"
	wanted = (frappe.form_dict.get("colour") or "").strip().lower()
	p["colour"] = next(
		(c["label"] for c in p["colours"] if c["label"].lower() == wanted),
		p["colours"][0]["label"] if p["colours"] else "",
	)
	own = [ph for ph in p["photos"] if p["colour"] and ph["colour"] == p["colour"]]
	general = [ph for ph in p["photos"] if not ph["colour"] or not p["colour"]]
	if not (own or general):  # every photo is for another colour: show them all rather than none
		general = p["photos"]
	shown = own + general
	for ph in p["photos"]:
		ph["hide"] = not any(ph is s for s in shown)
	p["shown"] = shown
	p["photos"] = shown + [ph for ph in p["photos"] if ph["hide"]]
	for i, ph in enumerate(p["photos"]):
		ph["key"] = i  # the gallery's id for the photo = its place in the page
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
