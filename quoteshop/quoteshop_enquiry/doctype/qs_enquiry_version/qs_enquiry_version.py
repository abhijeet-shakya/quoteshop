# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSEnquiryVersion(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		accepted_on: DF.Datetime | None
		accepted_via: DF.Literal["", "Website", "WhatsApp", "Sales on behalf"]
		created_by: DF.Data | None
		created_by_type: DF.Literal["Buyer", "Sales"]
		created_on: DF.Datetime | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		snapshot: DF.JSON | None
		summary: DF.SmallText | None
		token_expires: DF.Datetime | None
		token_hash: DF.Data | None
		version: DF.Int
	# end: auto-generated types

	pass
