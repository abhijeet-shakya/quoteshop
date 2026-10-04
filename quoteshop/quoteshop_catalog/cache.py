import frappe


def clear_catalog_cache(*args, **kwargs) -> None:
	"""Delete every cached catalog payload. Accepts doc_events arguments so it can be hooked directly."""
	frappe.cache.delete_keys("qs:catalog:")
