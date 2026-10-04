from quoteshop.quoteshop_website.context import listing, setup


def get_context(context):
	qs = setup(context, "search", title=None)
	qs.title = f"{qs.q} · {qs.name}" if qs.q else f"All products · {qs.name}"
	qs.description = f"Search results for {qs.q}" if qs.q else f"All products from {qs.name}"
	context.data = listing(context, q=qs.q or None)
	context.heading = f"Results for “{qs.q}”" if qs.q else "All products"
