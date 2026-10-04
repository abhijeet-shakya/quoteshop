# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSEnquiryMessage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		direction: DF.Literal["Outgoing", "Incoming"]
		event: DF.Literal[
			"enquiry_received_buyer",
			"enquiry_alert_sales",
			"price_sent",
			"accepted",
			"changes_requested",
			"version_outdated",
			"otp",
		]
		message_id: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		sent_on: DF.Datetime | None
		version: DF.Int
		whatsapp_message: DF.Link | None
	# end: auto-generated types

	pass
