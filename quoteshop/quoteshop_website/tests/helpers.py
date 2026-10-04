"""Rendering helpers for phase 2 website tests (CONTRACTS §5.1: render with the website router, no server)."""

import html as htmllib
import re
from typing import ClassVar
from urllib.parse import urlsplit

import frappe
from bs4 import BeautifulSoup
from frappe.utils import set_request

from quoteshop.quoteshop_catalog.tests.base import CatalogTestCase
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_group_tree,
	make_homepage_settings,
	make_item_price,
	make_photo,
	make_published_item,
	make_store_settings,
)

# Proposed hooks for the markup (CONTRACTS is silent; listed as a gap in the test-lead report).
THEME_TOGGLE = "[data-qs-theme-toggle]"


class Page:
	"""A rendered response: status, parsed HTML, visible text."""

	def __init__(self, response):
		self.response = response
		self.status = response.status_code
		self.html = frappe.safe_decode(response.get_data())
		self.soup = BeautifulSoup(self.html, "html.parser")
		visible = BeautifulSoup(self.html, "html.parser")
		for tag in visible(["script", "style", "noscript"]):
			tag.decompose()
		self.text = re.sub(r"\s+", " ", htmllib.unescape(visible.get_text(" "))).strip()

	def links(self, prefix):
		return [a["href"] for a in self.soup.find_all("a", href=True) if a["href"].startswith(prefix)]

	def meta(self, name):
		tag = self.soup.find("meta", attrs={"name": name})
		return tag.get("content", "") if tag else ""


def render(route, query=None, user="Guest"):
	"""Render `route` through frappe.website like a request from `user` (default Guest)."""
	from frappe.website.serve import get_response

	previous_user = frappe.session.user
	frappe.set_user(user)
	frappe.local.no_cache = False
	frappe.local.response = frappe._dict()
	frappe.local.response_headers.clear()
	frappe.local.form_dict = frappe._dict(query or {})
	query_string = "&".join(f"{k}={v}" for k, v in (query or {}).items())
	set_request(method="GET", path=route, query_string=query_string)
	try:
		return Page(get_response())
	finally:
		frappe.set_user(previous_user)


def external_references(page):
	"""Absolute / protocol-relative URLs in script, link (except canonical), img, source, iframe, video, audio."""
	found = []
	for tag in page.soup.find_all(["script", "link", "img", "source", "iframe", "video", "audio"]):
		if tag.name == "link" and "canonical" in (tag.get("rel") or []):
			continue
		for attr in ("src", "href", "srcset", "poster"):
			value = tag.get(attr)
			if not value:
				continue
			urls = (
				[part.split()[0] for part in value.split(",") if part.strip()]
				if attr == "srcset"
				else [value]
			)
			for url in urls:
				if url.startswith("//") or urlsplit(url).scheme in ("http", "https"):
					found.append((tag.name, attr, url))
	for style in page.soup.find_all("style"):
		found += [
			("style", "url", u)
			for u in re.findall(r"""(?:url\(|@import\s+)['"]?((?:https?:)?//[^'")\s]+)""", style.get_text())
		]
	return found


def has_number(text, number):
	"""True if `number` appears as a standalone amount (5555 or 5,555), not inside a hash or id."""
	digits = str(number)
	grouped = f"{int(digits):,}"
	return bool(re.search(rf"(?<![\w.]){digits}(?![\w])|(?<![\w.]){re.escape(grouped)}(?![\w])", text))


def price_regex(amount, suffix="per piece"):
	"""'From ₹1,250 per piece' with Frappe's money formatting left open (1,250 / 1250 / 1,250.00)."""
	whole, _, frac = f"{amount}".partition(".")
	grouped = f"{int(whole):,}".replace(",", ",?")
	decimals = rf"\.{frac}0*" if frac else r"(?:\.0+)?"
	return rf"From\s*₹\s*{grouped}{decimals}\s*{suffix}"


class Storefront(CatalogTestCase):
	"""Class-level fixture shared by the page tests (built once per class, rolled back with the class)."""

	ASH_SIZES: ClassVar[dict] = {
		"thumb": "/files/ash-400.webp",
		"medium": "/files/ash-1000.webp",
		"large": "/files/ash-1800.webp",
	}

	@staticmethod
	def _remove_photo_files():
		for name in frappe.get_all("File", filters={"attached_to_name": ("like", "_QS-%")}, pluck="name"):
			frappe.delete_doc("File", name, force=1, ignore_permissions=True)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.addClassCleanup(cls._remove_photo_files)  # runs before the class rollback
		make_store_settings(business_name="Acme Billiards", brand_color="#1F4E79")
		make_homepage_settings(
			hero_title="Cues, Tables and Chalk",
			hero_subtitle="Everything for the game room",
			hero_image="/files/_qs_hero.png",
		)
		make_group_tree({"_QS Cues": {"_QS Cue Cases": {}}, "_QS Chalk": {}, "_QS Hidden Group": {}})
		make_published_item(
			"_QS-CUE-1",
			rate=1250,
			group="_QS Cues",
			item_name="Ash Cue Pro",
			description="<p>Handmade ash shaft</p>",
			qs_short_description="Tournament grade",
			standard_rate=7777,
		)
		make_item_price("_QS-CUE-1", 8888, price_list="_QS Test Other List")
		make_photo("_QS-CUE-1", 10, 10, alt_text="Ash cue front", stem="_qs_pg_cue", **cls.ASH_SIZES)
		make_published_item("_QS-CASE-1", rate=800.5, group="_QS Cue Cases", item_name="Hard Cue Case")
		make_published_item(
			"_QS-CHALK-1",
			rate=120,
			group="_QS Chalk",
			item_name="Blue Chalk Box",
			qs_short_description="Pack of twelve",
		)
		make_published_item("_QS-NOPRICE", group="_QS Cues", item_name="Custom Cue")
		make_published_item(
			"_QS-SECRET", rate=5555, group="_QS Cues", item_name="Secret Cue", qs_hide_price=1
		)
		make_published_item("_QS-DRAFT", rate=4444, group="_QS Cues", item_name="Draft Cue")
		make_published_item("_QS-OFF", rate=2222, group="_QS Cues", item_name="Disabled Cue")

		item = frappe.get_doc("Item", "_QS-CUE-1")
		item.append("qs_specs", {"label": "Weight", "value": "19 oz"})
		item.append("qs_related", {"item": "_QS-CASE-1"})
		item.append("qs_related", {"item": "_QS-DRAFT"})
		item.save(ignore_permissions=True)

		# Routes exist once published; then take the draft item, the hidden group and the disabled item offline.
		cls.routes = {
			code: frappe.db.get_value("Item", code, "qs_route")
			for code in (
				"_QS-CUE-1",
				"_QS-CASE-1",
				"_QS-CHALK-1",
				"_QS-NOPRICE",
				"_QS-SECRET",
				"_QS-DRAFT",
				"_QS-OFF",
			)
		}
		cls.group_routes = {
			name: frappe.db.get_value("Item Group", name, "qs_route")
			for name in ("_QS Cues", "_QS Cue Cases", "_QS Chalk", "_QS Hidden Group")
		}
		frappe.db.set_value("Item", "_QS-DRAFT", "qs_published", 0)
		frappe.db.set_value("Item", "_QS-OFF", "disabled", 1)
		frappe.db.set_value("Item Group", "_QS Hidden Group", "qs_published", 0)
		frappe.cache.delete_keys("qs:catalog:")

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(setattr, frappe.flags, "force_website_cache", False)

	def product_path(self, code):
		return f"/p/{self.routes[code]}"

	def category_path(self, name):
		return f"/c/{self.group_routes[name]}"

	def pages(self):
		"""One rendered page per catalog page type (Guest)."""
		pages = {
			"home": render("/"),
			"category": render(self.category_path("_QS Cues")),
			"search": render("/search", {"q": "cue"}),
			"product": render(self.product_path("_QS-CUE-1")),
		}
		for name, page in pages.items():
			self.assertEqual(page.status, 200, f"{name} did not render")
		return pages
