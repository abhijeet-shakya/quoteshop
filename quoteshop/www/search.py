from frappe import _

from quoteshop.quoteshop_website.context import listing, setup


def get_context(context):
	qs = setup(context, "search", title=None)
	qs.title = f"{qs.q} · {qs.name}" if qs.q else f"{_('All products')} · {qs.name}"
	qs.description = (
		_("Search results for {0}").format(qs.q) if qs.q else _("All products from {0}").format(qs.name)
	)
	context.data = listing(context, q=qs.q or None)
	context.heading = _("Results for “{0}”").format(qs.q) if qs.q else _("All products")
