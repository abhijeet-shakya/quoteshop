"""DSK-01..DSK-03 / SPEC §5 / LAYOUT_MAP §D - Desk colour maps, read from the JS literals desk-ui ships.

Contract with desk-ui: one object literal per map, `const NAME = { "Key": "colour", ... };`, no nested
braces (bare keys, as prettier writes them, are accepted). On-screen rendering is DSK-21 (e2e).
"""

import re
from pathlib import Path

from frappe.tests import UnitTestCase

HERE = Path(__file__).parent
PAIR = re.compile(r'(?:"([^"]+)"|(\w+))\s*:\s*"([^"]*)"')

STATUS_COLORS = {
	"Draft": "gray",
	"Requested": "blue",
	"Price Sent": "orange",
	"Changes Requested": "yellow",
	"Accepted": "green",
	"Lost": "red",
	"Expired": "darkgrey",
}
AVAILABILITY_COLORS = {
	"Available": "green",
	"Partial": "orange",
	"Made to Order": "blue",
	"Not Available": "red",
	"Alternative": "purple",
}
VERSION_BY_COLORS = {"Buyer": "cyan", "Sales": "blue"}


def js_map(filename, name):
	"""`const <name> = {...}` from a JS file next to this test, as a dict; None when not declared."""
	literal = re.search(rf"const {name}\s*=\s*\{{(.*?)\}}", (HERE / filename).read_text(), re.S)
	if not literal:
		return None
	return {quoted or bare: colour for quoted, bare, colour in PAIR.findall(literal.group(1))}


class TestEnquiryIndicators(UnitTestCase):
	def test_status_indicator_mapping(self):
		self.assertEqual(js_map("qs_enquiry_list.js", "QS_STATUS_COLORS"), STATUS_COLORS)
		# The form's indicator comes from the list get_indicator; a copy in the form script must not drift.
		self.assertIn(js_map("qs_enquiry.js", "QS_STATUS_COLORS"), (None, STATUS_COLORS))

	def test_availability_colour_mapping(self):
		self.assertEqual(js_map("qs_enquiry.js", "QS_AVAILABILITY_COLORS"), AVAILABILITY_COLORS)

	def test_version_by_colour_mapping(self):
		self.assertEqual(js_map("qs_enquiry.js", "QS_VERSION_BY_COLORS"), VERSION_BY_COLORS)
