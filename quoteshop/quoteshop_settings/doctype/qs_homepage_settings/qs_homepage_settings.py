# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from quoteshop.quoteshop_catalog.cache import clear_catalog_cache


class QSHomepageSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from quoteshop.quoteshop_settings.doctype.qs_homepage_section.qs_homepage_section import (
			QSHomepageSection,
		)
		from quoteshop.quoteshop_settings.doctype.qs_how_it_works_step.qs_how_it_works_step import (
			QSHowItWorksStep,
		)
		from quoteshop.quoteshop_settings.doctype.qs_promo_tile.qs_promo_tile import QSPromoTile
		from quoteshop.quoteshop_settings.doctype.qs_trust_point.qs_trust_point import QSTrustPoint

		hero_badge: DF.Data | None
		hero_image: DF.AttachImage | None
		hero_primary_label: DF.Data | None
		hero_primary_link: DF.Data | None
		hero_secondary_label: DF.Data | None
		hero_secondary_link: DF.Data | None
		hero_subtitle: DF.SmallText | None
		hero_title: DF.Data
		how_it_works: DF.Table[QSHowItWorksStep]
		mobile_strip_link: DF.Data | None
		mobile_strip_text: DF.Data | None
		promo_tiles: DF.Table[QSPromoTile]
		section_order: DF.Table[QSHomepageSection]
		show_how_it_works: DF.Check
		show_mobile_strip: DF.Check
		trust_points: DF.Table[QSTrustPoint]
	# end: auto-generated types

	def on_update(self) -> None:
		clear_catalog_cache()
