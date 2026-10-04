from frappe import _


def get_data() -> dict:
	"""Connections: deal and order point back via `qs_enquiry`; customer/contact are links on the enquiry."""
	return {
		"fieldname": "qs_enquiry",
		"internal_links": {"Customer": "customer", "Contact": "contact"},
		"transactions": [
			{"label": _("CRM"), "items": ["CRM Deal"]},
			{"label": _("Selling"), "items": ["Sales Order"]},
			{"label": _("Buyer"), "items": ["Customer", "Contact"]},
		],
	}
