# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSEnquiryQuestion(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		fieldtype: DF.Literal["Data", "Check", "Select", "Date", "Small Text"]
		label: DF.Data
		options: DF.SmallText | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		required: DF.Check
	# end: auto-generated types

	pass
