# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from quoteshop.quoteshop_catalog.cache import clear_catalog_cache


class QSEnquirySettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from quoteshop.quoteshop_settings.doctype.qs_buyer_type.qs_buyer_type import QSBuyerType
		from quoteshop.quoteshop_settings.doctype.qs_enquiry_question.qs_enquiry_question import (
			QSEnquiryQuestion,
		)

		accepted_template: DF.Link | None
		bulk_tier_2: DF.Int
		bulk_tier_3: DF.Int
		buyer_types: DF.Table[QSBuyerType]
		changes_requested_template: DF.Link | None
		enquiry_alert_sales_template: DF.Link | None
		enquiry_received_buyer_template: DF.Link | None
		login_mode: DF.Literal["Not required", "Optional", "Required"]
		otp_required: DF.Check
		otp_template: DF.Link | None
		price_sent_template: DF.Link | None
		questions: DF.Table[QSEnquiryQuestion]
		quote_validity_days: DF.Int
		require_pincode: DF.Check
		show_business_name: DF.Check
		show_notes: DF.Check
		show_pincode: DF.Check
		version_outdated_template: DF.Link | None
	# end: auto-generated types

	def on_update(self) -> None:
		clear_catalog_cache()
