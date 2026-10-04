# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSHomepageSection(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		section: DF.Literal["Hero", "Promo tiles", "Trust line", "How it works", "Categories", "Products"]
	# end: auto-generated types

	pass
