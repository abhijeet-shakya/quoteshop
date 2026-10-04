import frappe
from frappe.model.document import Document
from frappe.website.utils import clear_website_cache

PREFIX = "qs:catalog:"


def delete_catalog_keys(*args, **kwargs) -> None:
	"""Hook `website_clear_cache`: drop catalog payloads only (must not call clear_website_cache again)."""
	frappe.cache.delete_keys(PREFIX)


def _clear() -> None:
	delete_catalog_keys()
	clear_website_cache()


def clear_catalog_cache(*args, **kwargs) -> None:
	"""Delete every cached catalog payload and the website page cache, now and again after commit.

	The second pass drops anything a concurrent request cached from pre-commit data.
	"""
	_clear()
	frappe.db.after_commit.add(_clear)


def on_catalog_change(doc: Document, method: str | None = None, *args) -> None:
	"""doc_events on Item, Item Group, Item Price (on_update, on_trash, after_rename)."""
	clear_catalog_cache()
