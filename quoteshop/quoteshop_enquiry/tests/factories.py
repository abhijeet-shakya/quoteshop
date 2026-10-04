"""QuoteShop test factories. Tests never rely on site data (CONTRACTS §1).

Every helper is get-or-create with deterministic "_QS Test" names, so it is safe to call
repeatedly inside one IntegrationTestCase class (data is rolled back at class end).
"""

import hashlib
import io

import frappe
from frappe.utils import add_days, getdate, today

STARTING_PRICE_LIST = "Website Starting Price"
COMPANY = "_QS Test Company"
ITEM_GROUP = "_QS Test Item Group"
CUSTOMER_GROUP = "_QS Test Customer Group"
TERRITORY = "_QS Test Territory"
DEFAULT_MOBILE = "+919800000001"


def make_company(name=COMPANY, abbr="_QST", currency="INR", country="India"):
	if not frappe.db.exists("Company", name):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": abbr,
				"default_currency": currency,
				"country": country,
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
			}
		).insert(ignore_permissions=True)
	return name


def make_warehouse(company, name="_QS Test Warehouse"):
	"""Non-group Warehouse in an existing `company` (see make_company); returns its full name."""
	full_name = f"{name} - {frappe.db.get_value('Company', company, 'abbr')}"
	if not frappe.db.exists("Warehouse", full_name):
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": name, "company": company}).insert(
			ignore_permissions=True
		)
	return full_name


def make_fiscal_year(date="2026-06-15"):
	"""Ensure a Fiscal Year covers `date` (frozen dates must fall inside it)."""
	d = getdate(date)
	existing = frappe.db.get_value(
		"Fiscal Year", {"year_start_date": ("<=", d), "year_end_date": (">=", d), "disabled": 0}
	)
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": f"_QS Test Fiscal Year {d.year}",
				"year_start_date": f"{d.year}-01-01",
				"year_end_date": f"{d.year}-12-31",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _make_tree_node(doctype, name_field, name, parent_field, parent):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, name_field: name, parent_field: parent, "is_group": 0}).insert(
			ignore_permissions=True
		)
	return name


def make_item_group(name=ITEM_GROUP):
	return _make_tree_node("Item Group", "item_group_name", name, "parent_item_group", "All Item Groups")


def make_customer_group(name=CUSTOMER_GROUP):
	return _make_tree_node(
		"Customer Group", "customer_group_name", name, "parent_customer_group", "All Customer Groups"
	)


def make_territory(name=TERRITORY):
	return _make_tree_node("Territory", "territory_name", name, "parent_territory", "All Territories")


def make_price_list(name=STARTING_PRICE_LIST, currency="INR"):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"currency": currency,
				"selling": 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	return name


def make_item(item_code, rate=None, price_list=STARTING_PRICE_LIST, **fields):
	"""Item (non-stock by default); with `rate`, also an Item Price in `price_list`."""
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": make_item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				**fields,
			}
		).insert(ignore_permissions=True)
	if rate is not None:
		make_price_list(price_list)
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"uom": "Nos",
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)
	return item_code


def make_user(email, roles=()):
	"""System User with exactly `roles` (replaced if the user already exists)."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"_QS Test {email.split('@')[0]}",
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user.set("roles", [])
	user.add_roles(*roles)
	return email


def make_enquiry(lines=(), **fields):
	"""Insert a QS Enquiry. Each line dict needs `item_code`; missing Items are created."""
	for line in lines:
		make_item(line["item_code"])
		if line.get("alternative_item"):
			make_item(line["alternative_item"])
	doc = frappe.get_doc(
		{
			"doctype": "QS Enquiry",
			"buyer_name": "_QS Test Buyer",
			"mobile": DEFAULT_MOBILE,
			**fields,
			"items": [dict(line) for line in lines],
		}
	)
	return doc.insert(ignore_permissions=True)


# --- phase 2: catalog / website helpers (appended) ---------------------------------------------------

PUBLISHED_GROUP = "_QS Test Published Group"
BRAND_COLOR = "#1F4E79"


def make_group_tree(tree, parent="All Item Groups", published=1):
	"""Create nested published Item Groups from {"Name": {"Child": {}}}; returns every name, parents first.

	Siblings get qs_display_order 1, 2, 3 ... in dict order; get-or-create like the other factories.
	"""
	names = []
	for order, (name, children) in enumerate(tree.items(), start=1):
		if not frappe.db.exists("Item Group", name):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": name,
					"parent_item_group": parent,
					"is_group": 1 if children else 0,
					"qs_published": published,
					"qs_display_order": order,
				}
			).insert(ignore_permissions=True)
		names.append(name)
		names += make_group_tree(children, name, published)
	return names


def make_item_price(
	item_code,
	rate,
	price_list=STARTING_PRICE_LIST,
	valid_from=None,
	valid_upto=None,
	customer=None,
	uom="Nos",
):
	"""Item Price row (always a new row); returns its name.

	`valid_from` defaults to 30 days ago (not Frappe's "Today"), so tests can add a newer price today.
	"""
	make_price_list(price_list)
	return (
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"uom": uom,
				"price_list_rate": rate,
				"valid_from": valid_from or add_days(today(), -30),
				"valid_upto": valid_upto,
				"customer": customer,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_published_item(item_code, rate=None, group=None, published=1, **fields):
	"""Item with qs_published set (get-or-create), in a published Item Group; `rate` = starting price."""
	if group is None:
		make_group_tree({PUBLISHED_GROUP: {}})
		group = PUBLISHED_GROUP
	make_item(item_code, qs_published=published, item_group=group, **fields)
	if rate is not None:
		make_item_price(item_code, rate)
	return item_code


def png_bytes(width=2400, height=1200, color=(200, 30, 30)):
	"""In-memory PNG (Pillow); no files on disk."""
	from PIL import Image

	buffer = io.BytesIO()
	Image.new("RGB", (width, height), color).save(buffer, format="PNG")
	return buffer.getvalue()


def make_photo(
	item_code, width=2400, height=1200, color=(200, 30, 30), stem="_qs_test_photo", alt_text="", **sizes
):
	"""Public PNG File attached to `item_code` plus a QS Item Photo row (no Item save, no hooks).

	`sizes` (thumb=, medium=, large=) pre-fill the generated-size columns. Returns a dict with
	row, file_url, content, sha1 (first 10 hex chars of sha1(source bytes), as in the file naming rule).
	"""
	content = png_bytes(width, height, color)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{stem}.png",
			"content": content,
			"is_private": 0,
			"attached_to_doctype": "Item",
			"attached_to_name": item_code,
		}
	).insert(ignore_permissions=True)
	idx = frappe.db.count("QS Item Photo", {"parent": item_code, "parentfield": "qs_photos"}) + 1
	row = frappe.get_doc(
		{
			"doctype": "QS Item Photo",
			"parent": item_code,
			"parenttype": "Item",
			"parentfield": "qs_photos",
			"idx": idx,
			"image": file.file_url,
			"alt_text": alt_text,
			**sizes,
		}
	).insert(ignore_permissions=True)
	return frappe._dict(
		row=row.name,
		file_url=file.file_url,
		content=content,
		sha1=hashlib.sha1(content).hexdigest()[:10],
	)


def make_store_settings(**overrides):
	"""Save QS Store Settings with the required fields and deterministic defaults (+ overrides)."""
	doc = frappe.get_doc("QS Store Settings")
	doc.update(
		{
			"business_name": "_QS Test Shop",
			"starting_price_list": make_price_list(),
			"brand_color": BRAND_COLOR,
			"default_company": make_company(),
			"default_customer_group": make_customer_group(),
			"default_territory": make_territory(),
			"show_starting_prices": 1,
			"products_per_page": 24,
			"price_suffix": "per piece",
			"quote_button_label": "Quote",
			"default_theme": "Auto",
			"allow_theme_switch": 1,
			**overrides,
		}
	)
	doc.save(ignore_permissions=True)
	return doc


def make_homepage_settings(sections=("Hero", "Categories", "Products"), **overrides):
	"""Save QS Homepage Settings with `sections` enabled in that order (+ overrides)."""
	doc = frappe.get_doc("QS Homepage Settings")
	doc.update(
		{
			"hero_title": "_QS Test Hero",
			"hero_subtitle": "_QS Test hero subtitle",
			"show_how_it_works": 0,
			**overrides,
		}
	)
	doc.set("section_order", [{"section": s, "enabled": 1} for s in sections])
	doc.save(ignore_permissions=True)
	return doc
