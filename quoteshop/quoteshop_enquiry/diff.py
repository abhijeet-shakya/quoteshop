from frappe.utils import flt


def line_key(row) -> str:
	"""Identity of a quote line: item code + colour ("" when none). `row` is a dict or a doc row."""
	return f"{row.get('item_code')}\x1f{row.get('colour') or ''}"


def diff_lines(
	previous: list[dict], current: list[dict], *, rate_precision: int = 2, qty_precision: int = 3
) -> dict[str, str]:
	"""{line_key: change flag} between two versions' lines (dicts or doc rows).

	A colour change is a Removed line plus an Added line."""
	before = {line_key(row): row for row in previous}
	flags = dict.fromkeys(before, "Removed")
	for row in current:
		key = line_key(row)
		flags[key] = _change_flag(before.get(key), row, rate_precision, qty_precision)
	return flags


def _change_flag(old: dict | None, new: dict, rate_precision: int, qty_precision: int) -> str:
	if old is None:
		return "Added"
	if new.get("availability") == "Alternative" and (
		old.get("availability") != "Alternative"
		or (old.get("alternative_item") or "") != (new.get("alternative_item") or "")
	):
		return "Alternative"
	if flt(old.get("offered_rate"), rate_precision) != flt(new.get("offered_rate"), rate_precision):
		return "Price changed"
	if flt(old.get("offered_qty"), qty_precision) != flt(new.get("offered_qty"), qty_precision):
		return "Qty changed"
	return ""
