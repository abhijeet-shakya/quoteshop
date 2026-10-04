import re
import unicodedata

import frappe
from frappe.model.document import Document

TITLE_FIELD = {"Item": "item_name", "Item Group": "item_group_name"}


def set_route(doc: Document, method: str | None = None) -> None:
	"""doc_event validate (Item, Item Group): give a published doc a unique `qs_route` once; never change it."""
	if not doc.qs_published or doc.qs_route:
		return
	base = slugify(doc.get(TITLE_FIELD[doc.doctype])) or slugify(doc.name) or "item"
	taken = set(
		frappe.get_all(
			doc.doctype,
			filters={"qs_route": ("like", f"{base}%"), "name": ("!=", doc.name or "")},
			pluck="qs_route",
		)
	)
	route, n = base, 1
	while route in taken:
		n += 1
		route = f"{base}-{n}"
	doc.qs_route = route


def slugify(text: str | None) -> str:
	ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
	return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower())[:120].strip("-")
