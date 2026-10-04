"""LAYOUT_MAP (approved) as data, asserted from frappe.get_meta(...).fields the way Desk lays them out.

TEST_MATRIX DSK-14..DSK-20, NFR-13. Fields use the map's notation:
`fieldname Fieldtype[:options] [=default] [ro] [reqd] [idx] [unique] [⇐fetch_from] [↓depends_on]`
- flags, fetch_from and depends_on are exact: not written in the map = not set;
- options are shown for Data/Link/Select/Table types (Select values joined with "/");
- default "0" is the same as no default (Check/Int);
- depends_on in shorthand: `eval:doc.status == "Lost"` -> `status=Lost`.
"ro once set" on qs_route is behaviour, tested by CAT-19 (Frappe's set_only_once would also block
empty -> slug on existing Items, so it is not the mechanism).
"""

import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cstr

OPTION_TYPES = ("Data", "Link", "Select", "Table", "Table MultiSelect")
FLAGS = {"read_only": "ro", "reqd": "reqd", "search_index": "idx", "unique": "unique"}
OPEN_QUOTE = '<a href="/app/qs-enquiry/{{ qs_enquiry }}">Open quote</a>'  # CONTRACTS §3.4


def condition(expr):
	expr = re.sub(r"eval:|doc\.|[\"']", "", expr)
	return re.sub(r"\s*={2,3}\s*", "=", expr).strip()


def field(df):
	text = f"{df.fieldname} {df.fieldtype}"
	if df.options and df.fieldtype in OPTION_TYPES:
		text += ":" + df.options.replace("\n", "/")
	if cstr(df.default) not in ("", "0"):
		text += f" ={df.default}"
	text += "".join(f" {flag}" for key, flag in FLAGS.items() if df.get(key))
	if df.fetch_from:
		text += f" ⇐{df.fetch_from}"
	if df.depends_on:
		text += f" ↓{condition(df.depends_on)}"
	return text


def section(df):
	text = cstr(df.label) + (" coll" if df.collapsible else "")
	return text + (f" ↓{condition(df.depends_on)}" if df.depends_on else "")


def rows(doctype):
	"""(tab, section, column, field) per field, with Desk's rules (frappe/public/js/frappe/form/layout.js):
	fields before the first Tab Break sit in "Details"; a Tab/Section Break opens a section with no
	column; a Column Break opens the next column; a field with no open column opens column 1."""
	tab, sec, col, out = "Details", "", 0, []
	for df in frappe.get_meta(doctype).fields:
		if df.fieldtype == "Tab Break":
			tab, sec, col = df.label, "", 0
		elif df.fieldtype == "Section Break":
			sec, col = section(df), 0
		elif df.fieldtype == "Column Break":
			col += 1
		else:
			col = col or 1
			out.append((tab, sec, col, field(df)))
	return out


def expected_rows(tabs):
	"""Map-shaped [(tab, [(section, [[field, ...] per column]), ...]), ...] -> rows() shape."""
	return [
		(tab, sec, col, f)
		for tab, sections in tabs
		for sec, columns in sections
		for col, column in enumerate(columns, 1)
		for f in column
	]


def storefront(doctype):
	return [row for row in rows(doctype) if row[0] == "Storefront"]


def fields_of(doctype):
	return [row[3] for row in rows(doctype)]


def tab_labels(doctype):
	return [df.label for df in frappe.get_meta(doctype).fields if df.fieldtype == "Tab Break"]


def list_view(doctype):
	"""in_list_view fieldnames in field order (= grid column order for a child table)."""
	return [df.fieldname for df in frappe.get_meta(doctype).fields if df.in_list_view]


# A. Custom fields on standard DocTypes

ITEM = [  # A1, Storefront tab between Pricing and Connections (CONTRACTS §9.3)
	(
		"Storefront",
		[
			(
				"Publishing",
				[
					["qs_published Check idx", "qs_display_order Int idx"],
					["qs_route Data unique", "qs_lead_time Int"],
					["qs_min_qty Int =1", "qs_hide_price Check"],
				],
			),
			("Starting price ↓qs_published", [["qs_starting_price_html HTML"]]),
			("Content ↓qs_published", [["qs_short_description Small Text"]]),
			("Photos ↓qs_published", [["qs_photos Table:QS Item Photo"]]),
			("Specifications coll", [["qs_specs Table:QS Item Spec"]]),
			("Related items coll", [["qs_related Table MultiSelect:QS Related Item"]]),
		],
	)
]

ITEM_GROUP = [  # A2
	(
		"Storefront",
		[
			(
				"Publishing",
				[
					["qs_published Check idx", "qs_display_order Int idx"],
					["qs_route Data unique", "qs_image Attach Image"],
				],
			)
		],
	)
]

SALES_ORDER = [  # A3
	(
		"Storefront",
		[
			("Source", [["qs_enquiry Link:QS Enquiry ro idx"], ["qs_version Int ro"]]),
			("Price summary", [["qs_price_summary_html HTML ro"]]),
		],
	)
]

CRM_DEAL = [  # A5, one section; the map gives no section label ("" below, label ignored)
	# qs_open_quote is NOT read-only (CRM hides read-only valueless fields) and shows only with an enquiry
	# (CONTRACTS §6.6).
	(
		"Storefront",
		[
			(
				"",
				[
					["qs_enquiry Link:QS Enquiry ro idx", "qs_open_quote HTML ↓qs_enquiry"],
					["qs_buyer_type Data ro"],
					["qs_version Int ro"],
				],
			)
		],
	)
]

# B. QuoteShop DocTypes

STORE_SETTINGS = [  # B1
	(
		"Brand",
		[
			(
				"Identity",
				[
					["business_name Data reqd", "short_name Data"],
					["logo Attach Image", "favicon Attach Image"],
				],
			),
			(
				"Website text",
				[["search_placeholder Data", "quote_button_label Data =Quote"], ["response_time_text Data"]],
			),
		],
	),
	(
		"Contact",
		[
			("Contact", [["whatsapp_number Data:Phone", "email Data:Email"], ["address Small Text"]]),
			("Social links", [["social_links Table:QS Social Link"]]),
		],
	),
	(
		"Pricing",
		[
			(
				"Prices",
				[
					["show_starting_prices Check =1", "show_savings_to_buyer Check =1"],
					[
						"starting_price_list Link:Price List =Website Starting Price reqd",
						"price_suffix Data =per piece",
					],
					["products_per_page Int =24"],
				],
			)
		],
	),
	(
		"Theme",
		[
			(
				"Theme",
				[
					["brand_color Color =#146B47 reqd"],
					["default_theme Select:Auto/Light/Dark =Auto", "allow_theme_switch Check =1"],
				],
			)
		],
	),
	(
		"Defaults",
		[
			(
				"Orders",
				[
					[
						"default_company Link:Company reqd",
						"default_customer_group Link:Customer Group reqd",
						"default_territory Link:Territory reqd",
					],
					["default_warehouse Link:Warehouse", "auto_submit_sales_order Check"],
				],
			)
		],
	),
]

HOMEPAGE_SETTINGS = [  # B2
	(
		"Hero",
		[
			(
				"Hero",
				[
					["hero_badge Data", "hero_title Data reqd", "hero_subtitle Small Text"],
					["hero_image Attach Image"],
				],
			),
			(
				"Buttons",
				[
					["hero_primary_label Data", "hero_primary_link Data"],
					["hero_secondary_label Data", "hero_secondary_link Data"],
				],
			),
		],
	),
	(
		"Sections",
		[
			("Section order", [["section_order Table:QS Homepage Section"]]),
			("Promo tiles", [["promo_tiles Table:QS Promo Tile"]]),
			("Trust line", [["trust_points Table:QS Trust Point"]]),
			(
				"How it works",
				[
					[
						"show_how_it_works Check =1",
						"how_it_works Table:QS How It Works Step ↓show_how_it_works",
					]
				],
			),
		],
	),
	(
		"Mobile",
		[
			(
				"Trade strip",
				[
					["show_mobile_strip Check"],
					[
						"mobile_strip_text Data ↓show_mobile_strip",
						"mobile_strip_link Data ↓show_mobile_strip",
					],
				],
			)
		],
	),
]

TEMPLATE = "{} Link:WhatsApp Templates"
ENQUIRY_SETTINGS = [  # B3
	(
		"Form",
		[
			(
				"Login",
				[
					["login_mode Select:Not required/Optional/Required =Not required"],
					["otp_required Check =1"],
				],
			),
			(
				"Fields",
				[
					["show_pincode Check", "require_pincode Check ↓show_pincode"],
					["show_business_name Check =1", "show_notes Check =1"],
				],
			),
		],
	),
	("Buyer types", [("Buyer types", [["buyer_types Table:QS Buyer Type"]])]),
	("Questions", [("Questions", [["questions Table:QS Enquiry Question"]])]),
	(
		"Quote rules",
		[
			(
				"Validity & tiers",
				[["quote_validity_days Int =15"], ["bulk_tier_2 Int =2", "bulk_tier_3 Int =5"]],
			)
		],
	),
	(
		"WhatsApp templates",
		[
			(
				"Templates",
				[
					[
						TEMPLATE.format(f)
						for f in (
							"otp_template",
							"enquiry_received_buyer_template",
							"enquiry_alert_sales_template",
							"price_sent_template",
						)
					],
					[
						TEMPLATE.format(f)
						for f in (
							"accepted_template",
							"changes_requested_template",
							"version_outdated_template",
						)
					],
				],
			)
		],
	),
]

ENQUIRY = [  # B4
	(
		"Quote",
		[
			(
				"Summary",
				[
					[
						"status Select:Draft/Requested/Price Sent/Changes Requested/Accepted/Lost/Expired =Draft ro idx",
						"current_version Int ro",
						"valid_till Date ro",
					],
					[
						"total_listed Currency ro",
						"total_offered Currency ro",
						"total_saved Currency ro",
						"saved_pct Percent ro",
					],
					[
						"line_count Int ro",
						"unit_count Float ro",
						"available_count Int ro",
						"partial_count Int ro",
						"not_available_count Int ro",
					],
				],
			),
			("Items", [["items Table:QS Enquiry Item"]]),
			(
				"Notes coll",
				[
					[
						"notes Small Text",
						"answers Table:QS Enquiry Answer",
						"lost_reason Small Text ↓status=Lost",
					]
				],
			),
		],
	),
	(
		"Buyer",
		[
			(
				"Contact",
				[
					["buyer_name Data reqd", "mobile Data reqd idx", "email Data"],
					["business_name Data", "buyer_type Data", "pincode Data"],
				],
			),
			(
				"Linked records",
				[
					["customer Link:Customer ro", "contact Link:Contact ro"],
					[
						"crm_deal Link:CRM Deal ro",
						"sales_order Link:Sales Order ro",
						"assigned_to Link:User ro idx",
					],
				],
			),
		],
	),
	("Versions", [("Versions", [["versions Table:QS Enquiry Version ro"]])]),
	("System", [("WhatsApp log coll", [["messages Table:QS Enquiry Message ro"]])]),
]

ENQUIRY_ITEM = [  # B4 row form (child table: no Tab Break, so Desk's "Details")
	(
		"Details",
		[
			(
				"Item",
				[
					["item_code Link:Item reqd", "item_name Data ro ⇐item_code.item_name", "uom Link:UOM"],
					[
						"requested_qty Float reqd",
						"offered_qty Float",
						"change_flag Select:/Qty changed/Price changed/Removed/Added/Alternative ro",
					],
				],
			),
			("Price", [["listed_rate Currency ro", "offered_rate Currency"], ["amount Currency ro"]]),
			(
				"Availability",
				[
					[
						"availability Select:Available/Partial/Made to Order/Not Available/Alternative =Available",
						"lead_time_days Int",
					],
					["availability_note Data", "alternative_item Link:Item ↓availability=Alternative"],
				],
			),
		],
	)
]

ENQUIRY_VERSION = [  # all ro
	"version Int ro",
	"created_by_type Select:Buyer/Sales ro",
	"created_by Data ro",
	"created_on Datetime ro",
	"summary Small Text ro",
	"snapshot JSON ro",
	"token_hash Data ro idx",
	"token_expires Datetime ro",
	"accepted_on Datetime ro",
	"accepted_via Select:/Website/WhatsApp/Sales on behalf ro",
]

ENQUIRY_MESSAGE = [  # all ro
	"version Int ro",
	"event Select:enquiry_received_buyer/enquiry_alert_sales/price_sent/accepted/changes_requested"
	"/version_outdated/otp ro",
	"direction Select:Outgoing/Incoming ro",
	"message_id Data ro idx",
	"whatsapp_message Link:WhatsApp Message ro",
	"sent_on Datetime ro",
]

# B5: the map lists these fields by name (types only in part) -> fieldnames in order.
SETTINGS_CHILD_TABLES = {
	"QS Social Link": ["label", "url"],
	"QS Homepage Section": ["section", "enabled"],
	"QS Promo Tile": ["kicker", "title", "link", "style", "show_on_desktop", "show_on_mobile"],
	"QS Trust Point": ["text"],
	"QS How It Works Step": ["title", "text"],
	"QS Buyer Type": ["label", "customer_group", "default_assignee"],
	"QS Enquiry Question": ["label", "fieldtype", "options", "required"],
}


class TestLayout(IntegrationTestCase):
	def assertDocType(self, doctype, **expected):
		meta = frappe.get_meta(doctype)
		self.assertEqual({k: meta.get(k) for k in expected}, expected, doctype)

	# A. Standard DocTypes

	def test_item_storefront_layout(self):
		self.assertEqual(tab_labels("Item")[-3:], ["Pricing", "Storefront", "Connections"])
		self.assertEqual(storefront("Item"), expected_rows(ITEM))
		named = {
			"qs_storefront_tab": "Storefront",
			"qs_publishing_section": "Publishing",
			"qs_lead_time": "Lead time (days)",
		}
		self.assertEqual(
			{df.fieldname: df.label for df in frappe.get_meta("Item").fields if df.fieldname in named}, named
		)

	def test_item_child_tables(self):
		for doctype in ("QS Item Photo", "QS Item Spec", "QS Related Item"):
			self.assertDocType(doctype, module="QuoteShop Catalog", istable=1)
		self.assertEqual(
			fields_of("QS Item Photo"),
			["image Attach Image reqd", "alt_text Data", "thumb Data ro", "medium Data ro", "large Data ro"],
		)
		self.assertEqual(list_view("QS Item Photo"), ["image", "alt_text"])
		self.assertEqual(fields_of("QS Item Spec"), ["label Data reqd", "value Data reqd"])
		self.assertEqual(list_view("QS Item Spec"), ["label", "value"])
		self.assertEqual(fields_of("QS Related Item"), ["item Link:Item reqd"])

	def test_item_group_layout(self):
		# Existing fields stay in Desk's implicit first "Details" tab.
		self.assertEqual(tab_labels("Item Group"), ["Storefront"])
		self.assertEqual(storefront("Item Group"), expected_rows(ITEM_GROUP))

	def test_sales_order_layout(self):
		self.assertEqual(tab_labels("Sales Order")[-3:], ["More Info", "Storefront", "Connections"])
		self.assertEqual(storefront("Sales Order"), expected_rows(SALES_ORDER))

	def test_sales_order_item_layout(self):
		names = [df.fieldname for df in frappe.get_meta("Sales Order Item").fields]
		at = names.index("qty")
		self.assertEqual(names[at : at + 3], ["qty", "qs_requested_qty", "stock_uom"])
		self.assertEqual(
			[f for f in fields_of("Sales Order Item") if f.startswith("qs_")], ["qs_requested_qty Float ro"]
		)
		self.assertNotIn("qs_requested_qty", list_view("Sales Order Item"))  # row form only

	def test_crm_deal_layout(self):
		self.assertEqual(tab_labels("CRM Deal")[-2:], ["Lost Details", "Storefront"])
		self.assertEqual(
			[(tab, "", col, f) for tab, _, col, f in storefront("CRM Deal")], expected_rows(CRM_DEAL)
		)
		self.assertEqual(
			[df.options for df in frappe.get_meta("CRM Deal").fields if df.fieldname == "qs_open_quote"],
			[OPEN_QUOTE],
		)

	def test_contact_mobile_no_indexed(self):
		setters = frappe.get_all(
			"Property Setter",
			filters={"doc_type": "Contact", "field_name": "mobile_no", "property": "search_index"},
			fields=["value", "module"],
		)
		self.assertEqual([s.value for s in setters], ["1"])
		self.assertIn(setters[0].module, frappe.get_module_list("quoteshop"))
		self.assertEqual(frappe.get_meta("Contact").get_field("mobile_no").search_index, 1)
		self.assertIsNotNone(frappe.db.get_column_index("tabContact", "mobile_no"))  # the lookup is indexed

	def test_custom_fields_only_in_storefront_tab(self):
		"""Every quoteshop Custom Field: qs_ prefix, module set, and inside the app's own Storefront tab."""
		modules = frappe.get_module_list("quoteshop")
		custom = [
			cf
			for cf in frappe.get_all("Custom Field", fields=["dt", "fieldname", "module"])
			if cf.fieldname.startswith("qs_") or cf.module in modules
		]
		self.assertEqual(
			sorted({cf.dt for cf in custom}),
			["CRM Deal", "Item", "Item Group", "Sales Order", "Sales Order Item"],
		)
		self.assertEqual(
			[cf for cf in custom if not (cf.fieldname.startswith("qs_") and cf.module in modules)], []
		)
		for doctype in ("CRM Deal", "Item", "Item Group", "Sales Order"):  # Sales Order Item has no tabs (A4)
			misplaced = [
				(tab, f) for tab, _, _, f in rows(doctype) if f.startswith("qs_") != (tab == "Storefront")
			]
			self.assertEqual(misplaced, [], doctype)

	# B. QuoteShop DocTypes

	def test_store_settings_layout(self):
		self.assertDocType("QS Store Settings", module="QuoteShop Settings", issingle=1)
		self.assertEqual(rows("QS Store Settings"), expected_rows(STORE_SETTINGS))

	def test_homepage_settings_layout(self):
		self.assertDocType("QS Homepage Settings", issingle=1)
		self.assertEqual(rows("QS Homepage Settings"), expected_rows(HOMEPAGE_SETTINGS))

	def test_enquiry_settings_layout(self):
		self.assertDocType("QS Enquiry Settings", issingle=1)
		self.assertEqual(rows("QS Enquiry Settings"), expected_rows(ENQUIRY_SETTINGS))

	def test_settings_child_tables(self):
		for doctype, names in SETTINGS_CHILD_TABLES.items():
			self.assertDocType(doctype, module="QuoteShop Settings", istable=1)
			self.assertEqual([f.split()[0] for f in fields_of(doctype)], names, doctype)
		self.assertEqual(list_view("QS Promo Tile"), ["title", "style", "show_on_desktop", "show_on_mobile"])

	def test_qs_enquiry_layout(self):
		self.assertDocType(
			"QS Enquiry", module="QuoteShop Enquiry", autoname="RFQ-.#####", is_submittable=0, track_changes=1
		)
		self.assertEqual(rows("QS Enquiry"), expected_rows(ENQUIRY))

	def test_qs_enquiry_child_tables(self):
		for doctype in ("QS Enquiry Item", "QS Enquiry Version", "QS Enquiry Answer", "QS Enquiry Message"):
			self.assertDocType(doctype, istable=1)
		self.assertEqual(rows("QS Enquiry Item"), expected_rows(ENQUIRY_ITEM))
		self.assertEqual(
			list_view("QS Enquiry Item"),
			["item_name", "requested_qty", "offered_qty", "offered_rate", "availability"],
		)
		self.assertEqual(fields_of("QS Enquiry Version"), ENQUIRY_VERSION)
		self.assertEqual(
			list_view("QS Enquiry Version"),
			["version", "created_by_type", "created_on", "summary", "accepted_on"],
		)
		self.assertEqual(fields_of("QS Enquiry Answer"), ["question Data", "value Small Text"])
		self.assertEqual(fields_of("QS Enquiry Message"), ENQUIRY_MESSAGE)
		self.assertEqual(list_view("QS Enquiry Message"), ["version", "event", "direction", "sent_on"])

	def test_enquiry_list_view(self):
		# LAYOUT_MAP D. Desk orders list columns by field order, so only membership is fixed.
		self.assertCountEqual(
			list_view("QS Enquiry"),
			["buyer_name", "business_name", "buyer_type", "total_offered", "assigned_to", "valid_till"],
		)
		self.assertEqual(
			[df.fieldname for df in frappe.get_meta("QS Enquiry").fields if df.in_standard_filter],
			["status", "buyer_type", "assigned_to"],
		)
