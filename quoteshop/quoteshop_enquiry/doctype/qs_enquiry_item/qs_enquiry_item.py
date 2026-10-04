# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSEnquiryItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		alternative_item: DF.Link | None
		amount: DF.Currency
		availability: DF.Literal["Available", "Partial", "Made to Order", "Not Available", "Alternative"]
		availability_note: DF.Data | None
		change_flag: DF.Literal["", "Qty changed", "Price changed", "Removed", "Added", "Alternative"]
		item_code: DF.Link
		item_name: DF.Data | None
		lead_time_days: DF.Int
		listed_rate: DF.Currency
		offered_qty: DF.Float
		offered_rate: DF.Currency
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		requested_qty: DF.Float
		uom: DF.Link | None
	# end: auto-generated types

	pass
