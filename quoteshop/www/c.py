import frappe

from quoteshop.quoteshop_website.context import listing, setup


def get_context(context):
	route = frappe.form_dict.get("route")
	data = listing(context, category=route)  # unknown / unpublished category → 404
	name = next((c["name"] for c in data.categories if c["route"] == route), None)
	if not name:
		raise frappe.PageDoesNotExistError
	setup(context, "category", title=name, description=f"{name}: {data.total} products")
	context.data = data
	context.group = {"name": name, "route": route}
