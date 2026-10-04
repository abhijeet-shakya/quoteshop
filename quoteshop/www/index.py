import frappe

from quoteshop.quoteshop_website.context import DEFAULT_SECTIONS, listing, setup


def get_context(context):
	from quoteshop.quoteshop_catalog.catalog import categories, get_image_size

	hp = frappe.get_cached_doc("QS Homepage Settings")
	qs = setup(context, "home", description=hp.hero_subtitle)
	qs.headline = hp.hero_title
	sections = (
		[row.section for row in hp.section_order if row.enabled]
		if hp.section_order
		else list(DEFAULT_SECTIONS)
	)
	tiles = [t for t in hp.promo_tiles if t.title and (t.show_on_desktop or t.show_on_mobile)]
	blocks = _blocks(sections, hp, tiles)

	data = frappe._dict(categories=[])
	if any(b["kind"] == "catalog" and b["grid"] for b in blocks):
		data = listing(context)
	elif any(b["kind"] == "catalog" for b in blocks):
		data.categories = categories()

	hero_size = get_image_size(hp.hero_image) or (1200, 800)
	context.hp = hp
	context.tiles = tiles
	context.blocks = blocks
	context.data = data
	context.hero_size = hero_size


def _blocks(sections: list[str], hp, tiles: list) -> list[dict]:
	"""Configured sections as render blocks; Hero+Promo tiles share the bento row, Categories+Products one catalog."""
	blocks: list[dict] = []
	for section in sections:
		prev = blocks[-1] if blocks else {}
		if section == "Hero" and hp.hero_title:
			blocks.append({"kind": "bento", "hero": True, "promos": False})
		elif section == "Promo tiles" and tiles:
			if prev.get("kind") == "bento" and not prev["promos"]:
				prev["promos"] = True
			else:
				blocks.append({"kind": "bento", "hero": False, "promos": True})
		elif section == "Trust line" and hp.trust_points:
			blocks.append({"kind": "trust"})
		elif section == "How it works" and hp.show_how_it_works and hp.how_it_works:
			blocks.append({"kind": "how"})
		elif section == "Categories":
			blocks.append({"kind": "catalog", "chips": True, "grid": False})
		elif section == "Products":
			if prev.get("kind") == "catalog" and not prev["grid"]:
				prev["grid"] = True
			else:
				blocks.append({"kind": "catalog", "chips": False, "grid": True})
	return blocks
