"""Print format "QS Quote" (HTML for 1 and 100 lines, savings rules) and the attached quote PDF (CONTRACTS §5.6, §10)."""

import re

import frappe
from bs4 import BeautifulSoup
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_enquiry import versions, whatsapp
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_enquiry_settings,
	make_order_settings,
	make_quote,
	send_quote,
)


def line(code, qty, listed, **extra):
	return {"item_code": code, "requested_qty": qty, "listed_rate": listed, **extra}


def html(name):
	return frappe.get_print("QS Enquiry", name, print_format="QS Quote", as_pdf=False)


def text(markup):
	return re.sub(r"\s+", " ", BeautifulSoup(markup, "html.parser").get_text(" "))


def item_rows(markup):
	return BeautifulSoup(markup, "html.parser").select("table.qs-lines tbody tr:not(.qs-group)")


def pdf_or_skip(test, fn, *args):
	try:
		return fn(*args)
	except Exception as e:  # wkhtmltopdf needs the web server for /assets
		if any(s in str(e) for s in ("wkhtmltopdf", "HostNotFound", "ContentNotFound", "ConnectionRefused")):
			test.skipTest(f"PDF needs the web server for assets: {str(e)[:200]}")
		raise


class TestQuotePrint(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_order_settings(show_savings_to_buyer=1)
		make_enquiry_settings()

	def test_one_line(self):
		doc = make_quote([line("_QS-PR-1", 3, 100)], buyer_name="<b>Ravi</b>")
		versions.apply_discount(doc.name, 10, "all")
		out = html(doc.name)
		self.assertEqual(len(item_rows(out)), 1)
		t = text(out)
		for expected in ("Quotation", doc.name, "_QS-PR-1", "Your price", "270", "You save", "Listed total"):
			self.assertIn(expected, t)
		self.assertNotIn("<b>Ravi</b>", out)  # buyer text escaped
		self.assertIn("&lt;b&gt;Ravi", out)

	def test_hundred_lines(self):
		doc = make_quote([line(f"_QS-PR-H{i:03d}", 1, 10 + i) for i in range(100)])
		out = html(doc.name)
		rows = item_rows(out)
		self.assertEqual(len(rows), 100)
		self.assertEqual(rows[-1].find("td").get_text(strip=True), "100")
		self.assertIn("Lines: 100", text(out))

	def test_savings_hidden_when_not_positive(self):
		doc = make_quote([line("_QS-PR-2", 1, 100, offered_rate=120)])
		t = text(html(doc.name))
		self.assertNotIn("You save", t)
		doc = make_quote([line("_QS-PR-3", 1, 100)])
		self.assertNotIn("You save", text(html(doc.name)))

	def test_listed_and_savings_hidden_when_setting_off(self):
		doc = make_quote([line("_QS-PR-4", 2, 100, offered_rate=80)])
		with self.change_settings("QS Store Settings", show_savings_to_buyer=0):
			out = html(doc.name)
		t = text(out)
		for hidden in ("You save", "Listed total", "Listed"):
			self.assertNotIn(hidden, t)
		self.assertFalse(BeautifulSoup(out, "html.parser").find("s"))
		self.assertIn("160", t)

	def test_removed_and_not_available_lines(self):
		doc = make_quote(
			[
				line("_QS-PR-5", 1, 50),
				line("_QS-PR-6", 2, 30, availability="Not Available"),
				line("_QS-PR-7", 1, 20, change_flag="Removed"),
			]
		)
		out = html(doc.name)
		self.assertEqual(len(item_rows(out)), 2)
		self.assertNotIn("_QS-PR-7", text(out))
		self.assertIn("Not available", text(out))

	def test_colour_shown_under_the_item_name(self):
		doc = make_quote(
			[
				line("_QS-PR-C1", 1, 10, colour="Red"),
				line("_QS-PR-C1", 2, 10, colour="<b>Blue</b>"),
				line("_QS-PR-C2", 1, 10),
			]
		)
		out = html(doc.name)
		red, blue, plain = item_rows(out)
		self.assertIn("Colour: Red", text(str(red)))
		self.assertIn("Colour: <b>Blue</b>", text(str(blue)))  # shown as text, not markup
		self.assertNotIn("<b>Blue</b>", out)
		self.assertIn("&lt;b&gt;Blue&lt;/b&gt;", out)
		self.assertNotIn("Colour", text(str(plain)))

	def test_pdf_one_and_hundred_lines(self):
		for lines in ([line("_QS-PR-P1", 1, 10)], [line(f"_QS-PR-P{i:03d}", 1, 10) for i in range(100)]):
			doc = make_quote(lines)
			pdf = pdf_or_skip(
				self, lambda: frappe.get_print("QS Enquiry", doc.name, print_format="QS Quote", as_pdf=True)
			)
			self.assertTrue(pdf.startswith(b"%PDF"))

	def test_pdf_attached_once_per_version(self):
		doc = make_quote([line("_QS-PR-8", 1, 10)])
		send_quote(doc.name)
		doc.reload()
		url = pdf_or_skip(self, whatsapp._quote_pdf, doc, 1)
		self.assertEqual(whatsapp._quote_pdf(doc, 1), url)  # stored, not rendered again
		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "QS Enquiry", "attached_to_name": doc.name},
			fields=["file_url", "is_private", "file_name"],
		)
		self.assertEqual(len(files), 1)
		self.assertEqual((files[0].file_url, files[0].is_private), (url, 0))
		self.assertRegex(files[0].file_name, rf"^{doc.name}-v1-[0-9a-f]{{16}}\.pdf$")
