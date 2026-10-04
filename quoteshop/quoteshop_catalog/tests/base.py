"""Shared base for phase 2 catalog/website tests.

Each test runs inside a DB savepoint (rolled back afterwards) so published items never leak between
tests: totals such as `list_products()["total"]` are exact. Redis is not transactional, so the catalog
keys and the cached settings docs are cleared before and after every test.
"""

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.tests.factories import make_homepage_settings, make_store_settings

SETTINGS = ("QS Store Settings", "QS Homepage Settings", "QS Enquiry Settings")
SAVEPOINT = "qs_test"


def clear_redis():
	frappe.cache.delete_keys("qs:catalog:")
	frappe.cache.delete_keys("website_page::")
	for doctype in SETTINGS:
		frappe.clear_document_cache(doctype)


class CatalogTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_store_settings()
		make_homepage_settings()

	def setUp(self):
		super().setUp()
		frappe.local.request = None  # a request left by an earlier test would switch rate limits on
		frappe.db.savepoint(SAVEPOINT)
		clear_redis()
		self.addCleanup(self._reset)

	def _reset(self):
		frappe.db.rollback(save_point=SAVEPOINT)
		clear_redis()

	def set_settings(self, **values):
		"""Save QS Store Settings fields (rolled back with the test)."""
		doc = frappe.get_doc("QS Store Settings")
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc


# The catalog service does not exist until catalog-web builds it: import lazily so every test fails on
# its own (RED) instead of one collection error hiding all of them.
def list_products(*args, **kwargs):
	from quoteshop.quoteshop_catalog.catalog import list_products as fn

	return fn(*args, **kwargs)


def get_product(*args, **kwargs):
	from quoteshop.quoteshop_catalog.catalog import get_product as fn

	return fn(*args, **kwargs)


def get_categories(*args, **kwargs):
	from quoteshop.quoteshop_catalog.catalog import get_categories as fn

	return fn(*args, **kwargs)


def codes(result):
	"""item_code list of a list_products() result."""
	return [card["item_code"] for card in result["items"]]


def route_of(doctype, name):
	return frappe.db.get_value(doctype, name, "qs_route")
