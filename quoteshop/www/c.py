import frappe
from frappe import _

from quoteshop.quoteshop_website.context import listing, setup


def get_context(context):
	route = frappe.form_dict.get("route")
	data = listing(context, category=route)  # unknown / unpublished category → 404
	name = next((c["name"] for c in data.categories if c["route"] == route), None)
	if not name:
		raise frappe.PageDoesNotExistError
	setup(context, "category", title=name, description=_("{0}: {1} products").format(name, data.total))
	context.data = data
	context.group = {"name": name, "route": route}
	context.qs.active_group = data.top["name"] if data.top else None
	context.trail = f"{data.top['name']} / {name}" if data.top and data.top["name"] != name else name
