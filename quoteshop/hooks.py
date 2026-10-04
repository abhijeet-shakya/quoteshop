app_name = "quoteshop"
app_title = "QuoteShop"
app_publisher = "Abhijeet Shakya"
app_description = "Configurable storefront with quote list, enquiries and CRM integration"
app_email = "abhijeet.shakya@infinitelocus.com"
app_license = "gpl-3.0"

required_apps = ["erpnext", "crm", "frappe_whatsapp", "erp_custom"]

after_install = "quoteshop.install.after_install"

permission_query_conditions = {
	"QS Enquiry": "quoteshop.quoteshop_enquiry.permissions.enquiry_query_conditions",
}

has_permission = {
	"QS Enquiry": "quoteshop.quoteshop_enquiry.permissions.has_enquiry_permission",
}

home_page = "index"

website_route_rules = [
	{"from_route": "/c/<route>", "to_route": "c"},
	{"from_route": "/p/<route>", "to_route": "p"},
	{"from_route": "/q/<name>", "to_route": "q"},
]

doc_events = {
	"Item": {
		"validate": "quoteshop.quoteshop_catalog.routes.set_route",
		"on_update": [
			"quoteshop.quoteshop_catalog.cache.on_catalog_change",
			"quoteshop.quoteshop_catalog.images.queue_photo_sizes",
		],
		"on_trash": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
		"after_rename": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
	},
	"Item Group": {
		"validate": "quoteshop.quoteshop_catalog.routes.set_route",
		"on_update": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
		"on_trash": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
		"after_rename": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
	},
	"Item Price": {
		"on_update": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
		"on_trash": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
		"after_rename": "quoteshop.quoteshop_catalog.cache.on_catalog_change",
	},
	"WhatsApp Message": {
		"after_insert": "quoteshop.quoteshop_enquiry.whatsapp.on_whatsapp_message",
	},
}

doctype_js = {
	"Item": "public/js/item.js",
	"Sales Order": "public/js/sales_order.js",
}

scheduler_events = {
	"daily": ["quoteshop.quoteshop_enquiry.orders.expire_quotes"],
}

# Must not be clear_catalog_cache: that calls clear_website_cache, which runs this hook.
website_clear_cache = "quoteshop.quoteshop_catalog.cache.delete_catalog_keys"

jinja = {
	"methods": [
		"quoteshop.quoteshop_catalog.catalog.format_price",
		"quoteshop.quoteshop_catalog.catalog.get_image_size",
	]
}

# Document Events
# ---------------
# doc_events = {
# 	"DocType": {
# 		"on_submit": "quoteshop.module.file.method",
# 	}
# }

# Override whitelisted methods
# ----------------------------
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "quoteshop.module.file.get_events"
# }

# Override DocType classes
# ------------------------
# override_doctype_class = {
# 	"ToDo": "quoteshop.overrides.CustomToDo"
# }

# DocType JS
# ----------
# doctype_js = {"DocType": "public/js/doctype.js"}

# Permissions
# -----------
# permission_query_conditions = {
# 	"DocType": "quoteshop.module.file.get_permission_query_conditions",
# }

# Website route rules
# -------------------
# website_route_rules = [
# 	{"from_route": "/path/<name>", "to_route": "template"},
# ]

# Scheduled Tasks
# ---------------
# scheduler_events = {
# 	"daily": ["quoteshop.tasks.daily"],
# }
