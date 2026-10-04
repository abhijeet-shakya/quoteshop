import frappe

from quoteshop.quoteshop_website.context import DEFAULT_SECTIONS, home_rows, setup


def get_context(context):
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

	qs.overlay = bool(blocks) and blocks[0]["kind"] == "bento" and blocks[0]["hero"]  # header floats over the hero

	# Private files return 403 to visitors; fall back to the built-in illustration instead of a broken image.
	hero_image = "" if (hp.hero_image or "").startswith("/private/") else hp.hero_image
	# older settings point the buttons at the on-page catalog anchor; Browse now opens All products
	for field in ("hero_primary_link", "hero_secondary_link"):
		if (hp.get(field) or "").strip() in ("#products", "#catalog", "/#products", "/#catalog"):
			hp.set(field, "/search")
	context.hp = hp
	context.hero_image = hero_image
	context.tiles = tiles
	context.blocks = blocks
	context.rows = home_rows() if any(b["kind"] == "rows" for b in blocks) else []


def _blocks(sections: list[str], hp, tiles: list) -> list[dict]:
	"""Configured sections as render blocks; Hero+Promo tiles share one block, Categories+Products become the category rows."""
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
		elif section in ("Categories", "Products") and not any(b["kind"] == "rows" for b in blocks):
			blocks.append({"kind": "rows"})  # category chips live in the header now; one row per category
	return blocks
