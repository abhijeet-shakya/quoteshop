"""CONTRACTS §9.11 - brand colour: white button text on the brand colour must reach 4.5:1 (WCAG AA).

Low contrast warns (msgprint) but never blocks; anything that is not #RRGGBB is rejected.
"""

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry.tests.factories import (
	make_company,
	make_customer_group,
	make_price_list,
	make_territory,
)
from quoteshop.quoteshop_settings.doctype.qs_store_settings.qs_store_settings import contrast_ratio

DEFAULT_BRAND = "#146B47"  # design default, JSON default of brand_color
LOW_CONTRAST = "Low contrast"  # msgprint title


class TestContrastRatio(IntegrationTestCase):
	"""WCAG 2 reference values (SET-06)."""

	def test_extremes(self):
		self.assertEqual(contrast_ratio("#FFFFFF", "#000000"), 21.0)
		self.assertEqual(contrast_ratio("#FFFFFF", "#FFFFFF"), 1.0)

	def test_symmetric(self):
		self.assertEqual(contrast_ratio("#000000", "#FFFFFF"), contrast_ratio("#FFFFFF", "#000000"))

	def test_aa_boundary_greys(self):
		# #767676 is the lightest grey that passes AA on white (4.54:1); #777777 just fails (4.48:1).
		self.assertAlmostEqual(contrast_ratio("#FFFFFF", "#767676"), 4.54, places=2)
		self.assertAlmostEqual(contrast_ratio("#FFFFFF", "#777777"), 4.48, places=2)

	def test_yellow_on_white(self):
		self.assertAlmostEqual(contrast_ratio("#FFFFFF", "#FFFF00"), 1.07, places=2)

	def test_default_brand_passes(self):
		self.assertGreaterEqual(contrast_ratio("#FFFFFF", DEFAULT_BRAND), 4.5)

	def test_case_insensitive(self):
		self.assertEqual(contrast_ratio("#ffffff", "#ff0000"), contrast_ratio("#FFFFFF", "#FF0000"))


class TestQSStoreSettings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.required = {
			"business_name": "_QS Test Shop",
			"starting_price_list": make_price_list(),
			"default_company": make_company(),
			"default_customer_group": make_customer_group(),
			"default_territory": make_territory(),
		}

	def validate(self, brand_color):
		"""Run the controller's validate; returns the msgprint titles raised."""
		frappe.clear_messages()
		doc = frappe.get_doc("QS Store Settings")
		doc.brand_color = brand_color
		doc.validate()
		return [LOW_CONTRAST for message in frappe.local.message_log if LOW_CONTRAST in str(message)]

	def test_default_brand_color_is_design_default_and_no_warning(self):
		self.assertEqual(frappe.get_meta("QS Store Settings").get_field("brand_color").default, DEFAULT_BRAND)
		self.assertEqual(self.validate(DEFAULT_BRAND), [])

	def test_brand_color_contrast_light(self):
		"""SET-06: threshold sits exactly at AA 4.5:1 for white text."""
		self.assertEqual(self.validate("#767676"), [])  # 4.54:1
		self.assertEqual(self.validate("#777777"), [LOW_CONTRAST])  # 4.48:1
		self.assertEqual(self.validate("#000000"), [])

	def test_low_contrast_brand_color_warns_not_blocks(self):
		"""SET-08: yellow warns on validate and the save still goes through."""
		self.assertEqual(self.validate("#FFFF00"), [LOW_CONTRAST])
		frappe.clear_messages()
		doc = frappe.get_doc("QS Store Settings")
		doc.update({**self.required, "brand_color": "#FFFF00"})
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.get_cached_doc("QS Store Settings").brand_color, "#FFFF00")
		self.assertIn(LOW_CONTRAST, str(frappe.local.message_log))

	def test_lowercase_hex_accepted(self):
		self.assertEqual(self.validate("#ff0000"), [LOW_CONTRAST])  # 4.0:1

	def test_non_hex_brand_color_rejected(self):
		"""Anything but #RRGGBB (names, short hex, junk) is a ValidationError, not a warning."""
		for value in ("red", "#FFF", "#GGGGGG", "146B47", "#146B47 ", "rgb(20,107,71)"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				self.validate(value)

	def test_empty_brand_color_left_to_mandatory_check(self):
		self.assertEqual(self.validate(""), [])
