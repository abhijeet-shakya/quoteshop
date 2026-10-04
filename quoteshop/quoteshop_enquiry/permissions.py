"""QS Enquiry row-level access (hooks permission_query_conditions / has_permission, CONTRACTS §6.5)."""

import frappe
from frappe.model.document import Document

FULL_ACCESS_ROLES = frozenset({"System Manager", "Sales Manager"})


def enquiry_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	name = frappe.db.escape(user)
	assigned = frappe.db.escape(f'%"{_escape_like(user)}"%')
	return (
		f"(`tabQS Enquiry`.assigned_to = {name} or `tabQS Enquiry`.owner = {name}"
		f" or `tabQS Enquiry`._assign like {assigned})"
	)


def has_enquiry_permission(doc: Document, ptype: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	return (
		_has_full_access(user)
		or user in (doc.get("assigned_to"), doc.get("owner"))
		or user in frappe.parse_json(doc.get("_assign") or "[]")
	)


def _has_full_access(user: str) -> bool:
	return not FULL_ACCESS_ROLES.isdisjoint(frappe.get_roles(user))


def _escape_like(value: str) -> str:
	return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
