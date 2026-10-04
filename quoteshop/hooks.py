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
