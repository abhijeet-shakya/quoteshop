"""CONTRACTS §6.4 - settings read via get_cached_doc; saving any of the 3 settings clears "qs:catalog:" keys."""

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.tests.factories import (
	make_company,
	make_customer_group,
	make_price_list,
	make_territory,
)

CATALOG_KEY = "qs:catalog:_qs_test_dummy"
OTHER_KEY = "qs:other:_qs_test_dummy"


def read_redis(key):
	return frappe.cache.get_value(key, expires=True, use_local_cache=False)


class TestSettingsCache(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.store_required = {
			"business_name": "_QS Test Shop",
			"starting_price_list": make_price_list(),
			"brand_color": "#1F4E79",
			"default_company": make_company(),
			"default_customer_group": make_customer_group(),
			"default_territory": make_territory(),
		}

	def setUp(self):
		frappe.cache.set_value(CATALOG_KEY, {"x": 1})
		frappe.cache.set_value(OTHER_KEY, 1)
		self.addCleanup(frappe.cache.delete_value, [CATALOG_KEY, OTHER_KEY])

	def save(self, doctype, **values):
		doc = frappe.get_doc(doctype)
		doc.update(values)
		doc.save(ignore_permissions=True)

	def assert_cached_reflects_save(self, doctype, fieldname, first, second, required=None):
		frappe.get_cached_doc(doctype)  # warm the cache
		self.save(doctype, **{**(required or {}), fieldname: first})
		self.assertEqual(frappe.get_cached_doc(doctype).get(fieldname), first)
		self.save(doctype, **{fieldname: second})
		self.assertEqual(frappe.get_cached_doc(doctype).get(fieldname), second)

	def assert_catalog_keys_cleared(self):
		self.assertIsNone(read_redis(CATALOG_KEY))
		self.assertEqual(read_redis(OTHER_KEY), 1)  # only the qs:catalog: prefix is deleted

	def test_store_settings_cache_cleared_on_save(self):
		self.assert_cached_reflects_save(
			"QS Store Settings", "business_name", "_QS Test Shop A", "_QS Test Shop B", self.store_required
		)
		self.assert_catalog_keys_cleared()

	def test_homepage_settings_cache_cleared_on_save(self):
		self.assert_cached_reflects_save(
			"QS Homepage Settings", "hero_title", "_QS Test Hero A", "_QS Test Hero B"
		)
		self.assert_catalog_keys_cleared()

	def test_enquiry_settings_cache_cleared_on_save(self):
		self.assert_cached_reflects_save("QS Enquiry Settings", "quote_validity_days", 21, 30)
		self.assert_catalog_keys_cleared()

	def test_each_save_clears_catalog_keys(self):
		"""Key set right before a single save is gone after it (not only after the first save)."""
		self.save("QS Store Settings", **self.store_required)
		frappe.cache.set_value(CATALOG_KEY, {"x": 2})
		self.save("QS Store Settings", business_name="_QS Test Shop C")
		self.assert_catalog_keys_cleared()
