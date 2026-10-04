"""CONTRACTS §6.6 / §9.13 / LAYOUT_MAP §B, §C - after_install seeds once; idempotent; never overwrites."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.install import after_install
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_company,
	make_customer_group,
	make_territory,
	make_user,
	make_warehouse,
)

PRICE_LIST = "Website Starting Price"
ROLE = "Catalog Manager"
USD_COMPANY = "_QS Test Company USD"
SETTINGS = ("QS Store Settings", "QS Enquiry Settings", "QS Homepage Settings")
TEMPLATE_FIELDS = (
	"otp_template",
	"enquiry_received_buyer_template",
	"enquiry_alert_sales_template",
	"price_sent_template",
	"accepted_template",
	"changes_requested_template",
	"version_outdated_template",
)
SITE_SOURCE_FIELDS = ("default_company", "default_customer_group", "default_territory", "default_warehouse")
CATALOG_USER = "qs-test-catalog@example.com"
WA_TEMPLATE_POST = (
	"frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.make_post_request"
)


def reset_single(*doctypes):
	"""Simulate a first install: the Single has no stored values."""
	for doctype in doctypes:
		frappe.db.delete("Singles", {"doctype": doctype})
		frappe.clear_document_cache(doctype, doctype)


def settings(doctype):
	frappe.clear_document_cache(doctype, doctype)
	return frappe.get_doc(doctype)


def pick(doc, fields):
	return {f: doc.get(f) for f in fields}


def custom_docperms():
	return frappe.get_all(
		"Custom DocPerm",
		filters={"role": ROLE},
		fields=["parent", "permlevel", "read", "write", "create", "delete"],
		order_by="parent, permlevel",
	)


class TestAfterInstall(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Price List", {"name": PRICE_LIST})

	@contextmanager
	def site_sources(self, company="", customer_group="", territory="", warehouse=""):
		"""Site defaults read by after_install (CONTRACTS §6.6); "" = absent."""
		with (
			self.change_settings("Global Defaults", default_company=company),
			self.change_settings("Selling Settings", customer_group=customer_group, territory=territory),
			self.change_settings("Stock Settings", default_warehouse=warehouse),
		):
			yield

	# Price list

	def test_creates_starting_price_list(self):
		with self.site_sources():
			after_install()
		pl = frappe.get_doc("Price List", PRICE_LIST)
		self.assertEqual((pl.selling, pl.enabled, pl.currency), (1, 1, "INR"))

	def test_price_list_currency_from_default_company(self):
		company = make_company(USD_COMPANY, abbr="_QSU", currency="USD", country="United States")
		with self.site_sources(company=company):
			after_install()
		self.assertEqual(frappe.db.get_value("Price List", PRICE_LIST, "currency"), "USD")

	# Role and permissions (LAYOUT_MAP §C)

	def test_catalog_manager_role(self):
		after_install()
		self.assertEqual(frappe.db.get_value("Role", ROLE, "desk_access"), 1)

	def test_catalog_manager_custom_docperms(self):
		"""Standard DocTypes get Custom DocPerms via add_permission; QS DocTypes keep perms in JSON."""
		after_install()
		self.assertEqual(
			custom_docperms(),
			[
				{"parent": "Item", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 0},
				{"parent": "Item Group", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 0},
				{"parent": "Item Price", "permlevel": 0, "read": 1, "write": 1, "create": 1, "delete": 1},
			],
		)

	def test_catalog_manager_permissions(self):
		after_install()
		make_user(CATALOG_USER, [ROLE])
		expected = {
			"Item": {"read": True, "write": True, "create": True, "delete": False},
			"Item Group": {"read": True, "write": True, "create": True, "delete": False},
			"Item Price": {"read": True, "write": True, "create": True, "delete": True},
			"QS Store Settings": {"read": True, "write": True},
			"QS Homepage Settings": {"read": True, "write": True},
			"QS Enquiry Settings": {"read": False},
			"QS Enquiry": {"read": False, "write": False, "create": False},
		}
		actual = {
			dt: {p: bool(frappe.has_permission(dt, p, user=CATALOG_USER)) for p in perms}
			for dt, perms in expected.items()
		}
		self.assertEqual(actual, expected)

	def test_standard_perms_preserved(self):
		"""Custom DocPerms replace standard ones for a DocType - standard roles must keep access."""
		after_install()
		sales_user = make_user("qs-test-sales-std@example.com", ["Sales User"])
		item_manager = make_user("qs-test-item-std@example.com", ["Item Manager"])
		price_manager = make_user("qs-test-price-std@example.com", ["Sales Master Manager"])
		self.assertTrue(frappe.has_permission("Item", "read", user=sales_user))
		self.assertTrue(frappe.has_permission("Item Group", "read", user=sales_user))
		self.assertTrue(frappe.has_permission("Item", "write", user=item_manager))
		self.assertTrue(frappe.has_permission("Item Group", "write", user=item_manager))
		self.assertTrue(frappe.has_permission("Item Price", "write", user=price_manager))

	# Settings seed (first install only)

	def test_store_settings_defaults(self):
		reset_single("QS Store Settings")
		with self.site_sources():
			after_install()
		self.assertEqual(
			pick(
				settings("QS Store Settings"),
				(
					"starting_price_list",
					"quote_button_label",
					"price_suffix",
					"products_per_page",
					"default_theme",
					"allow_theme_switch",
					"show_starting_prices",
					"show_savings_to_buyer",
				),
			),
			{
				"starting_price_list": PRICE_LIST,
				"quote_button_label": "Quote",
				"price_suffix": "per piece",
				"products_per_page": 24,
				"default_theme": "Auto",
				"allow_theme_switch": 1,
				"show_starting_prices": 1,
				"show_savings_to_buyer": 1,
			},
		)

	def test_store_settings_site_sources_present(self):
		company = make_company()
		values = {
			"default_company": company,
			"default_customer_group": make_customer_group(),
			"default_territory": make_territory(),
			"default_warehouse": make_warehouse(company),
		}
		reset_single("QS Store Settings")
		with self.site_sources(
			company=company,
			customer_group=values["default_customer_group"],
			territory=values["default_territory"],
			warehouse=values["default_warehouse"],
		):
			after_install()
		self.assertEqual(pick(settings("QS Store Settings"), SITE_SOURCE_FIELDS), values)

	def test_store_settings_site_sources_absent(self):
		reset_single("QS Store Settings")
		with self.site_sources():
			after_install()
		doc = settings("QS Store Settings")
		self.assertEqual(
			{f: doc.get(f) or None for f in SITE_SOURCE_FIELDS}, dict.fromkeys(SITE_SOURCE_FIELDS)
		)

	def test_enquiry_settings_defaults(self):
		reset_single("QS Enquiry Settings")
		after_install()
		self.assertEqual(
			pick(
				settings("QS Enquiry Settings"),
				(
					"login_mode",
					"otp_required",
					"show_business_name",
					"show_notes",
					"quote_validity_days",
					"bulk_tier_2",
					"bulk_tier_3",
				),
			),
			{
				"login_mode": "Not required",
				"otp_required": 1,
				"show_business_name": 1,
				"show_notes": 1,
				"quote_validity_days": 15,
				"bulk_tier_2": 2,
				"bulk_tier_3": 5,
			},
		)

	def test_homepage_settings_defaults(self):
		reset_single("QS Homepage Settings")
		after_install()
		self.assertEqual(settings("QS Homepage Settings").show_how_it_works, 1)

	def test_whatsapp_template_links_left_empty(self):
		reset_single("QS Enquiry Settings")
		after_install()
		doc = settings("QS Enquiry Settings")
		self.assertEqual({f: doc.get(f) or None for f in TEMPLATE_FIELDS}, dict.fromkeys(TEMPLATE_FIELDS))

	def test_no_whatsapp_templates_inserted(self):
		before = frappe.db.count("WhatsApp Templates")
		with patch(WA_TEMPLATE_POST) as post:
			after_install()
			after_install()
		post.assert_not_called()
		self.assertEqual(frappe.db.count("WhatsApp Templates"), before)

	def test_rerun_leaves_settings_untouched(self):
		"""Once a Single has stored values, later runs never re-seed (an unchecked box stays unchecked)."""
		reset_single(*SETTINGS)
		with self.site_sources():
			after_install()

		enquiry = frappe.get_doc("QS Enquiry Settings")
		enquiry.show_notes = 0  # admin unchecks a default-1 box and saves
		enquiry.save(ignore_permissions=True)
		store_edits = {"show_savings_to_buyer": 0, "quote_button_label": "Get price", "price_suffix": ""}
		for field, value in store_edits.items():
			frappe.db.set_single_value("QS Store Settings", field, value)
		frappe.db.set_single_value("QS Homepage Settings", "show_how_it_works", 0)

		company = make_company()
		with self.site_sources(company=company, warehouse=make_warehouse(company)):
			after_install()  # site sources now present: still no backfill

		self.assertEqual(settings("QS Enquiry Settings").show_notes, 0)
		store = settings("QS Store Settings")
		self.assertEqual(
			(store.show_savings_to_buyer, store.quote_button_label, store.price_suffix or ""),
			(0, "Get price", ""),
		)
		self.assertIsNone(store.default_company or None)
		self.assertIsNone(store.default_warehouse or None)
		self.assertEqual(settings("QS Homepage Settings").show_how_it_works, 0)

	def test_after_install_idempotent(self):
		after_install()
		first = self.install_snapshot()
		after_install()  # must not raise
		second = self.install_snapshot()
		self.assertEqual(first[:2], (1, 1))
		self.assertEqual(len(first[2]), 3, "Custom DocPerm rows for Catalog Manager")
		self.assertEqual(second, first)

	def install_snapshot(self):
		return (
			frappe.db.count("Price List", {"name": PRICE_LIST}),
			frappe.db.count("Role", {"name": ROLE}),
			custom_docperms(),
			*(settings(dt).as_dict(no_default_fields=True) for dt in SETTINGS),
		)
