# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from quoteshop.quoteshop_catalog.cache import clear_catalog_cache

HEX_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")
WHITE = "#FFFFFF"
MIN_CONTRAST = 4.5  # WCAG AA: buttons use white text on the brand colour


class QSStoreSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from quoteshop.quoteshop_settings.doctype.qs_social_link.qs_social_link import QSSocialLink

		address: DF.SmallText | None
		allow_theme_switch: DF.Check
		auto_submit_sales_order: DF.Check
		brand_color: DF.Color
		business_name: DF.Data
		default_company: DF.Link
		default_customer_group: DF.Link
		default_territory: DF.Link
		default_theme: DF.Literal["Auto", "Light", "Dark"]
		default_warehouse: DF.Link | None
		email: DF.Data | None
		favicon: DF.AttachImage | None
		logo: DF.AttachImage | None
		price_suffix: DF.Data | None
		products_per_page: DF.Int
		quote_button_label: DF.Data | None
		response_time_text: DF.Data | None
		search_placeholder: DF.Data | None
		short_name: DF.Data | None
		show_savings_to_buyer: DF.Check
		show_starting_prices: DF.Check
		social_links: DF.Table[QSSocialLink]
		starting_price_list: DF.Link
		whatsapp_number: DF.Data | None
	# end: auto-generated types

	def validate(self) -> None:
		self.warn_low_contrast()
		warn_crm_auto_customer()

	def on_update(self) -> None:
		clear_catalog_cache()

	def warn_low_contrast(self) -> None:
		if not self.brand_color:
			return  # mandatory check reports it
		if not HEX_COLOUR.fullmatch(self.brand_color):
			frappe.throw(_("Brand colour must be a hex colour such as #146B47."))
		ratio = contrast_ratio(WHITE, self.brand_color)
		if ratio < MIN_CONTRAST:
			frappe.msgprint(
				_(
					"Brand colour {0} has low contrast with white button text ({1}:1). Aim for at least {2}:1."
				).format(self.brand_color, flt(ratio, 2), MIN_CONTRAST),
				title=_("Low contrast"),
				indicator="orange",
			)


def warn_crm_auto_customer() -> None:
	"""CONTRACTS §3.5: CRM's ERPNext sync would create a second Customer when a deal is Won. Warn only."""
	if not frappe.db.exists("DocType", "ERPNext CRM Settings"):
		return
	crm = frappe.db.get_singles_dict("ERPNext CRM Settings")
	if cint(crm.get("enabled")) and cint(crm.get("create_customer_on_status_change")):
		frappe.msgprint(
			_(
				"ERPNext CRM Settings creates a Customer when a deal changes status. QuoteShop creates"
				" Customers itself, so turn off 'Create customer on status change' to avoid duplicates."
			),
			title=_("Duplicate Customers"),
			indicator="orange",
		)


def contrast_ratio(hex1: str, hex2: str) -> float:
	"""WCAG 2 contrast ratio (1 to 21) between two #RRGGBB colours."""
	lighter, darker = sorted((_luminance(hex1), _luminance(hex2)), reverse=True)
	return (lighter + 0.05) / (darker + 0.05)


def _luminance(hex_colour: str) -> float:
	digits = hex_colour.lstrip("#")
	r, g, b = (
		c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
		for c in (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
	)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b
