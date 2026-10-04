# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class QSPromoTile(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		kicker: DF.Data | None
		link: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		show_on_desktop: DF.Check
		show_on_mobile: DF.Check
		style: DF.Literal["Dark", "Soft", "Plain"]
		title: DF.Data | None
	# end: auto-generated types

	pass
