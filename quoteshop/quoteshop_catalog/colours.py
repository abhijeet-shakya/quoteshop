import re

import frappe
from frappe import _
from frappe.model.document import Document

MAX_COLOURS = 12
SWATCH = re.compile(r"^#[0-9A-Fa-f]{6}$")


def validate_item_colours(doc: Document, method: str | None = None) -> None:
	"""doc_event validate (Item): colour rows are sane and every photo colour tag is one of the item's colour labels."""
	rows = doc.get("qs_colours") or []
	if len(rows) > MAX_COLOURS:
		frappe.throw(_("An item can have at most {0} colours.").format(MAX_COLOURS))

	seen = set()
	for row in rows:
		row.label = (row.label or "").strip()
		if not row.label:
			frappe.throw(_("Row {0}: Colour label is required.").format(row.idx))
		if row.label.casefold() in seen:
			frappe.throw(
				_("Row {0}: Colour label {1} is used more than once.").format(row.idx, frappe.bold(row.label))
			)
		seen.add(row.label.casefold())

		if not SWATCH.match(row.swatch or ""):
			frappe.throw(_("Row {0}: Swatch must be a hex colour like #AABBCC.").format(row.idx))
		row.swatch = row.swatch.upper()

	labels = {row.label for row in rows}
	for photo in doc.get("qs_photos") or []:
		if photo.colour and photo.colour not in labels:
			msg = (
				_("Photo row {0}: Colour {1} is not one of this item's colours.")
				if labels
				else _("Photo row {0}: Colour {1} cannot be set because this item has no colours.")
			)
			frappe.throw(msg.format(photo.idx, frappe.bold(photo.colour)))
