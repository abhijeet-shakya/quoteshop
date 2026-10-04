"""Idempotent seeds (CONTRACTS §6.6). Runs on install and via patch v1_0.seed_defaults."""

import frappe
from frappe.permissions import add_permission, update_permission_property

PRICE_LIST = "Website Starting Price"
CATALOG_MANAGER = "Catalog Manager"
CATALOG_PERMS = {
	"Item": ("read", "write", "create"),
	"Item Group": ("read", "write", "create"),
	"Item Price": ("read", "write", "create", "delete"),
}


def before_install() -> None:
	# Frappe initialises every Single (QS Store Settings links to this list by default) before after_install.
	make_starting_price_list(frappe.db.get_single_value("Global Defaults", "default_company"))


def after_install() -> None:
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	make_starting_price_list(company)
	make_catalog_manager()
	seed_settings(
		{
			"default_company": company,
			"default_customer_group": frappe.db.get_single_value("Selling Settings", "customer_group"),
			"default_territory": frappe.db.get_single_value("Selling Settings", "territory"),
			"default_warehouse": frappe.db.get_single_value("Stock Settings", "default_warehouse"),
		}
	)
	# The Property Setter (custom/contact.json) keeps search_index in meta; syncing it does not alter the table.
	frappe.db.add_index("Contact", ["mobile_no"])

	# A fresh install marks patches as done without running them.
	from quoteshop.patches.v1_0 import seed_crm_statuses, seed_desk

	seed_crm_statuses.execute()
	seed_desk.execute()

	from quoteshop.quoteshop_settings.doctype.qs_store_settings.qs_store_settings import (
		warn_crm_auto_customer,
	)

	warn_crm_auto_customer()


def make_starting_price_list(company: str | None) -> None:
	if frappe.db.exists("Price List", PRICE_LIST):
		return
	currency = (company and frappe.db.get_value("Company", company, "default_currency")) or "INR"
	had_default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": PRICE_LIST,
			"currency": currency,
			"selling": 1,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	# ERPNext makes the first selling Price List the site default; this one is not the business default.
	if not had_default and frappe.db.get_single_value("Selling Settings", "selling_price_list") == PRICE_LIST:
		frappe.db.set_single_value("Selling Settings", "selling_price_list", None)


def make_catalog_manager() -> None:
	if not frappe.db.exists("Role", CATALOG_MANAGER):
		frappe.get_doc({"doctype": "Role", "role_name": CATALOG_MANAGER, "desk_access": 1}).insert(
			ignore_permissions=True
		)
	for doctype, ptypes in CATALOG_PERMS.items():
		# add_permission/update_permission_property copy the standard DocPerms first (setup_custom_perms).
		perm = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": doctype, "role": CATALOG_MANAGER, "permlevel": 0, "if_owner": 0},
			ptypes,
			as_dict=True,
		)
		if not perm:
			add_permission(doctype, CATALOG_MANAGER, 0)
		for ptype in ptypes:
			if not (perm or {}).get(ptype):
				update_permission_property(doctype, CATALOG_MANAGER, 0, ptype, 1)


def seed_settings(site_defaults: dict) -> None:
	"""Save each Single once with its DocType defaults (+ site defaults for the store); never re-seed."""
	for doctype, values in (
		("QS Store Settings", {k: v or None for k, v in site_defaults.items()}),
		("QS Enquiry Settings", {}),
		("QS Homepage Settings", {}),
	):
		if frappe.db.get_singles_dict(doctype):
			continue
		doc = frappe.get_doc(doctype)
		doc.update(values)
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
