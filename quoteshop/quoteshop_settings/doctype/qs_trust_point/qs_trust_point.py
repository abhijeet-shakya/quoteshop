# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSTrustPoint(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		text: DF.Data | None
	# end: auto-generated types

	pass
