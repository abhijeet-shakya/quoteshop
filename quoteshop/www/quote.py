import frappe
from frappe import _

from quoteshop.quoteshop_website.context import setup


def get_context(context):
	setup(context, "quote", title=_("Your quote list"))
	form = frappe.get_cached_doc("QS Enquiry Settings")
	context.form = form
	context.buyer_types = [b.label for b in form.buyer_types if b.label]
	context.questions = [
		{
			"id": f"qs-qn-{i}",
			"label": q.label,
			"fieldtype": q.fieldtype or "Data",
			"options": [o.strip() for o in (q.options or "").split("\n") if o.strip()],
			"required": q.required,
		}
		for i, q in enumerate(form.questions)
		if q.label
	]
	# Same for every guest, so the page stays cacheable; the list itself lives in localStorage.
	context.must_login = form.login_mode == "Required" and frappe.session.user == "Guest"
