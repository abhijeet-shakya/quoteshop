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


# --- phases 5-8: pricing, versions, accept/order, portal, reports (test-lead B, appended) ------------

SECOND_MOBILE = "+919800000002"


def make_order_settings(**overrides):
	"""Store settings that can create Sales Orders: company, fiscal year (today), group, territory."""
	make_fiscal_year(today())
	return make_store_settings(
		**{"default_warehouse": None, "auto_submit_sales_order": 0, "show_savings_to_buyer": 1, **overrides}
	)


def make_enquiry_settings(**overrides):
	"""Save QS Enquiry Settings: validity 15 days, no OTP, WhatsApp templates left as they are (+ overrides)."""
	doc = frappe.get_doc("QS Enquiry Settings")
	doc.update({"quote_validity_days": 15, "otp_required": 0, "login_mode": "Not required", **overrides})
	doc.save(ignore_permissions=True)
	return doc


def make_buyer_contact(mobile=DEFAULT_MOBILE, name="_QS Test Buyer"):
	"""Contact found/created exactly like submit_enquiry does (E.164 mobile_no)."""
	from quoteshop.quoteshop_enquiry.api import find_or_create_contact

	return find_or_create_contact(mobile, name)


def make_quote(lines, mobile=DEFAULT_MOBILE, deal=False, **fields):
	"""A "Requested" QS Enquiry with a Contact, as submit_enquiry leaves it.

	`lines` = [{"item_code", "requested_qty", "listed_rate", ...}]; items are created published (so a buyer
	may re-add them). `deal=True` also creates the CRM Deal.
	"""
	for line in lines:
		make_published_item(line["item_code"])
	contact = make_buyer_contact(mobile, fields.get("buyer_name") or "_QS Test Buyer")
	doc = make_enquiry(lines, **{"status": "Requested", "mobile": mobile, "contact": contact, **fields})
	if deal:
		from quoteshop.quoteshop_enquiry import crm

		crm.create_deal(doc)
		doc.reload()
	return doc


def send_quote(name):
	"""versions.send_price with frappe.enqueue patched → _dict(token, version, url, enqueue)."""
	from unittest.mock import patch
	from urllib.parse import parse_qs, urlsplit

	from quoteshop.quoteshop_enquiry.versions import send_price

	with patch("frappe.enqueue") as enqueue:
		result = send_price(name)
	token = parse_qs(urlsplit(result["url"]).query)["t"][0]
	return frappe._dict(token=token, enqueue=enqueue, **result)


def accept_and_order(name, token):
	"""accept_quote as the buyer (Guest) + run the order job directly → Sales Order name."""
	from unittest.mock import patch

	from quoteshop.quoteshop_enquiry import orders, quote_view

	user = frappe.session.user
	try:
		with patch("frappe.enqueue"):
			frappe.set_user("Guest")
			quote_view.accept_quote(name, token)
			version = frappe.db.get_value("QS Enquiry", name, "current_version")
			return orders.create_order(name, version)
	finally:
		frappe.set_user(user)


def make_otp_token(mobile=DEFAULT_MOBILE):
	"""An otp_token as verify_otp would issue it for `mobile` (30 minutes)."""
	from frappe.utils import add_to_date, now_datetime

	from quoteshop.quoteshop_enquiry.tokens import new_token

	raw, token_hash = new_token()
	frappe.cache.set_value(
		f"qs:otp-ok:{token_hash}",
		{"mobile": mobile, "expires_at": str(add_to_date(now_datetime(), seconds=1800))},
		expires_in_sec=1800,
	)
	return raw


# --- phases 3-4: enquiry APIs, OTP, CRM, WhatsApp (test-lead A, appended) ----------------------------

from frappe.tests import IntegrationTestCase

WA_ACCOUNT = "_QS Test WhatsApp"
WA_PHONE_ID = "_qs_test_phone_id"
WA_EVENTS = (
	"otp",
	"enquiry_received_buyer",
	"enquiry_alert_sales",
	"price_sent",
	"accepted",
	"changes_requested",
	"version_outdated",
)
WA_POST = "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message.make_post_request"
SAVEPOINT_A = "qs_test_a"


def make_wa_account(name=WA_ACCOUNT):
	"""Default outgoing + incoming WhatsApp Account (CONTRACTS §4.5); no network on insert."""
	if not frappe.db.exists("WhatsApp Account", name):
		frappe.get_doc(
			{
				"doctype": "WhatsApp Account",
				"account_name": name,
				"token": "_qs_test_token",
				"url": "https://graph.invalid",
				"version": "v17.0",
				"phone_id": WA_PHONE_ID,
				"business_id": "_qs_test_business",
				"status": "Active",
				"is_default_outgoing": 1,
				"is_default_incoming": 1,
			}
		).insert(ignore_permissions=True)
	return name


def make_wa_template(template_name, sample_values="a,b", field_names=None, header_type=None, buttons=()):
	"""Approved WhatsApp Template via db_insert (never calls Meta); returns its name."""
	name = f"{template_name}-en"
	if not frappe.db.exists("WhatsApp Templates", name):
		doc = frappe.get_doc(
			{
				"doctype": "WhatsApp Templates",
				"name": name,
				"template_name": template_name,
				"actual_name": template_name,
				"template": "_QS Test body {{1}}",
				"language": "en",
				"language_code": "en",
				"category": "UTILITY",
				"status": "APPROVED",
				"sample_values": sample_values,
				"field_names": field_names,
				"header_type": header_type,
				"buttons": [dict(b) for b in buttons],
			}
		)
		doc.db_insert()
		for row in doc.buttons:
			row.db_insert()
	frappe.clear_document_cache("WhatsApp Templates", name)
	return name


def link_wa_templates(*events, **field_names):
	"""Create one template per event and link it in QS Enquiry Settings; `field_names` per event."""
	make_wa_account()
	doc = frappe.get_doc("QS Enquiry Settings")
	for event in events:
		doc.set(
			f"{event}_template", make_wa_template(f"_qs_test_{event}", field_names=field_names.get(event))
		)
	doc.save(ignore_permissions=True)
	return doc


def make_qs_customer(name, contact=None, account_manager=None):
	"""Customer (+ Dynamic Link on `contact`, CONTRACTS §2.6: customer_primary_contact set on insert)."""
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": make_customer_group(),
				"territory": make_territory(),
				"account_manager": account_manager,
				"customer_primary_contact": contact,
			}
		).insert(ignore_permissions=True)
	if contact:
		doc = frappe.get_doc("Contact", contact)
		if not any(link.link_doctype == "Customer" and link.link_name == name for link in doc.links):
			doc.append("links", {"link_doctype": "Customer", "link_name": name})
			doc.save(ignore_permissions=True)
	return name


def make_website_user(email, mobile=None):
	"""Website User (portal buyer); with `mobile`, linked as Contact.user of that buyer's Contact."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "_QS Test Portal",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	if mobile:
		contact = make_buyer_contact(mobile)
		frappe.db.set_value("Contact", contact, "user", email)
	return email


def wa_incoming_payload(from_digits, reply_to, message_id, label="Accept quote", kind="button"):
	"""Meta webhook body for a quick-reply (template button) or plain text reply (CONTRACTS §4.3)."""
	message = {"from": from_digits, "id": message_id, "timestamp": "1700000000", "type": kind}
	if reply_to:
		message["context"] = {"from": "910000000000", "id": reply_to}
	if kind == "button":
		message["button"] = {"text": label, "payload": label}
	else:
		message["text"] = {"body": label}
	return {
		"object": "whatsapp_business_account",
		"entry": [
			{
				"id": "_qs_test_business",
				"changes": [
					{
						"field": "messages",
						"value": {
							"messaging_product": "whatsapp",
							"metadata": {"phone_number_id": WA_PHONE_ID},
							"contacts": [{"profile": {"name": "_QS Test Buyer"}, "wa_id": from_digits}],
							"messages": [message],
						},
					}
				],
			}
		],
	}


def call_api(cmd, *, user="Guest", http_method="POST", ip="10.9.9.1", **params):
	"""Call a whitelisted method like /api/method/<cmd> does: whitelist + guest + HTTP method checks,
	type validation and rate limits (frappe.request, request_ip and form_dict.cmd set; CONTRACTS §5.1)."""
	from frappe.handler import execute_cmd
	from frappe.utils import set_request

	previous_user = frappe.session.user
	previous_request = getattr(frappe.local, "request", None)
	frappe.set_user(user)  # resets form_dict, so it goes first
	set_request(method=http_method, path=f"/api/method/{cmd}")
	frappe.local.request_ip = ip
	frappe.local.form_dict = frappe._dict(cmd=cmd, **params)
	try:
		return execute_cmd(cmd)
	finally:
		frappe.set_user(previous_user)
		frappe.local.request = previous_request
		frappe.local.form_dict = frappe._dict()


def clear_qs_redis():
	"""Redis is not rolled back: drop QS OTP/rate-limit keys and the cached settings/templates."""
	for prefix in ("qs:otp", "qs:catalog:", "rl:"):
		frappe.cache.delete_keys(prefix)
	for doctype in ("QS Store Settings", "QS Homepage Settings", "QS Enquiry Settings"):
		frappe.clear_document_cache(doctype)
	for name in frappe.get_all("WhatsApp Templates", pluck="name"):
		frappe.clear_document_cache("WhatsApp Templates", name)


class EnquiryTestCase(IntegrationTestCase):
	"""Phase 3-4 base: store + enquiry settings (OTP on, no templates), each test in a savepoint."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from quoteshop.patches.v1_0 import seed_crm_statuses

		seed_crm_statuses.execute()
		make_store_settings()

	def setUp(self):
		super().setUp()
		frappe.local.request = None  # a request left by an earlier test would switch rate limits on
		frappe.db.savepoint(SAVEPOINT_A)
		clear_qs_redis()
		make_enquiry_settings(
			otp_required=1,
			show_pincode=0,
			require_pincode=0,
			show_business_name=1,
			show_notes=1,
			buyer_types=[],
			questions=[],
			**{f"{event}_template": None for event in WA_EVENTS},
		)
		self.addCleanup(self._reset)

	def _reset(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point=SAVEPOINT_A)
		clear_qs_redis()


# --- phase 8: report dataset (test-lead B, appended) -------------------------------------------------

REPORT_DAY = "2026-03-16"
REPORT_SALES_1 = "qs-b-report-sales-1@example.com"
REPORT_SALES_2 = "qs-b-report-sales-2@example.com"


def make_report_dataset():
	"""Known dataset for the 5 reports, all created on REPORT_DAY (filter from/to = that day).

	E1 S1 Retailer Accepted (SO submitted): A 4 x 250 → 225, B 2 x 100 → 90   listed 1200 offered 1080
	E2 S2 Club     Accepted (SO submitted): A 1 x 250 → 200, C 3 Not Available listed  250 offered  200
	E3 S1 Retailer Lost "Too expensive":   A 1 x 250,       C 5 Not Available           offered  250
	E4 S2 Club     Lost "Too expensive":   D 2 x 30                                      offered   60
	E5 S1 Retailer Requested:              C 2 Not Available, D 1 x 30
	"""
	from unittest.mock import patch

	from frappe.tests.classes.context_managers import freeze_time

	from quoteshop.quoteshop_enquiry import versions

	make_user(REPORT_SALES_1, ["Sales User"])
	make_user(REPORT_SALES_2, ["Sales User"])
	make_fiscal_year(REPORT_DAY)
	store = make_order_settings(auto_submit_sales_order=1)
	make_enquiry_settings(buyer_types=[{"label": "Retailer"}, {"label": "Club"}])

	def quote(mobile, owner, buyer_type, lines, discount=None, not_available=()):
		doc = make_quote(
			[{"item_code": c, "requested_qty": q, "listed_rate": r} for c, q, r in lines],
			mobile=mobile,
			assigned_to=owner,
			buyer_type=buyer_type,
		)
		for code in not_available:
			row = next(r for r in doc.items if r.item_code == code)
			versions.set_availability(doc.name, [row.name], "Not Available")
		if discount:
			versions.apply_discount(doc.name, discount, "all")
		return doc.name

	data = frappe._dict(
		day=REPORT_DAY, company=store.default_company, sales_1=REPORT_SALES_1, sales_2=REPORT_SALES_2
	)
	# tick=True: a fully frozen clock makes Sales Order submit fail check_if_latest (same `modified`)
	with freeze_time(f"{REPORT_DAY} 11:00:00", tick=True), patch("frappe.enqueue"):
		data.e1 = quote(
			"+919800000301", REPORT_SALES_1, "Retailer", [("_QS-REP-A", 4, 250), ("_QS-REP-B", 2, 100)], 10
		)
		data.so1 = accept_and_order(data.e1, send_quote(data.e1).token)
		data.e2 = quote(
			"+919800000302",
			REPORT_SALES_2,
			"Club",
			[("_QS-REP-A", 1, 250), ("_QS-REP-C", 3, 40)],
			20,
			["_QS-REP-C"],
		)
		data.so2 = accept_and_order(data.e2, send_quote(data.e2).token)
		if not (data.so1 and data.so2):
			frappe.throw(
				"report dataset: Sales Order not created (see Error Log 'QuoteShop: Sales Order not created')"
			)
		data.e3 = quote(
			"+919800000303",
			REPORT_SALES_1,
			"Retailer",
			[("_QS-REP-A", 1, 250), ("_QS-REP-C", 5, 40)],
			None,
			["_QS-REP-C"],
		)
		send_quote(data.e3)
		versions.mark_lost(data.e3, "Too expensive")
		data.e4 = quote("+919800000304", REPORT_SALES_2, "Club", [("_QS-REP-D", 2, 30)])
		versions.mark_lost(data.e4, "Too expensive")
		data.e5 = quote(
			"+919800000305",
			REPORT_SALES_1,
			"Retailer",
			[("_QS-REP-C", 2, 40), ("_QS-REP-D", 1, 30)],
			None,
			["_QS-REP-C"],
		)
	return data


def report_filters(data, **extra):
	return frappe._dict({"from_date": data.day, "to_date": data.day, "company": data.company, **extra})
