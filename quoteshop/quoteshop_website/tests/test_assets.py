"""Bundle budget and template hygiene (CONTRACTS §5.3, §8). TEST_MATRIX NFR-09 (+ part of NFR-08).

Budget: first load of a catalog page < 120 KB gzipped excluding images = gzip(HTML) + gzip(qs.bundle.js)
+ gzip(qs.bundle.css) (the only assets a QS page may load). Skipped, with a reason, until
`bench build --app quoteshop` has produced the bundle; the source/template checks always run.
"""

import gzip
import json
import os
import re

import frappe
from frappe.tests import IntegrationTestCase

from quoteshop.quoteshop_website.tests.helpers import Storefront, render

BUDGET_BYTES = 120 * 1024
BUNDLES = ("qs.bundle.js", "qs.bundle.css")
REQUIRED_TEMPLATES = (
	"templates/qs_base.html",
	"www/index.html",
	"www/c.html",
	"www/p.html",
	"www/search.html",
)
EXTERNAL_SCRIPT = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["'](?:https?:)?//""", re.I)
EXTERNAL_LINK = re.compile(r"""<link\b(?![^>]*canonical)[^>]*\bhref\s*=\s*["'](?:https?:)?//""", re.I)
THIRD_PARTY = re.compile(r"cdn\.|googleapis|gstatic|cloudflare|unpkg|jsdelivr|jquery", re.I)


def app_file(*parts):
	return os.path.join(frappe.get_app_path("quoteshop"), *parts)


def template_files():
	found = []
	for folder in ("templates", "www"):
		for root, _dirs, files in os.walk(app_file(folder)):
			found += [os.path.join(root, f) for f in files if f.endswith((".html", ".md", ".jinja"))]
	return found


def built_bundle(name):
	"""Path of the built bundle in sites/assets, or None when `bench build` has not produced it."""
	assets_json = os.path.join(frappe.utils.get_bench_path(), "sites", "assets", "assets.json")
	with open(assets_json) as f:
		url = json.load(f).get(name)
	if not url:
		return None
	path = os.path.join(frappe.utils.get_bench_path(), "sites", url.lstrip("/"))
	return path if os.path.exists(path) else None


def gzipped_size(path):
	with open(path, "rb") as f:
		return len(gzip.compress(f.read(), compresslevel=9))


class TestTemplateHygiene(IntegrationTestCase):
	def test_required_templates_exist(self):
		for relative in REQUIRED_TEMPLATES:
			self.assertTrue(os.path.exists(app_file(relative)), f"missing quoteshop/{relative}")

	def test_bundle_sources_exist(self):
		for relative in ("public/js/qs.bundle.js", "public/css/qs.bundle.css"):
			path = app_file(relative)
			self.assertTrue(os.path.exists(path), f"missing quoteshop/{relative}")
			self.assertGreater(os.path.getsize(path), 0, relative)

	def test_templates_load_no_other_origin(self):
		files = template_files()
		self.assertTrue(files, "no templates yet")
		for path in files:
			with open(path) as f:
				source = f.read()
			self.assertIsNone(EXTERNAL_SCRIPT.search(source), f"{path}: <script src> to another origin")
			self.assertIsNone(EXTERNAL_LINK.search(source), f"{path}: <link href> to another origin")
			self.assertIsNone(THIRD_PARTY.search(source), f"{path}: CDN / third-party / jquery reference")

	def test_base_template_is_standalone_and_uses_the_bundles(self):
		with open(app_file("templates", "qs_base.html")) as f:
			source = f.read()
		self.assertNotRegex(source, r"""{%\s*extends\s+["'](?:templates/)?(?:web|base)\.html["']""")
		self.assertRegex(source, r"""include_script\(\s*["']qs\.bundle\.js["']\s*\)""")
		self.assertRegex(source, r"""include_style\(\s*["']qs\.bundle\.css["']\s*\)""")
		self.assertNotIn("frappe-web.bundle", source)

	def test_pages_use_the_qs_base_template(self):
		for page in ("index", "c", "p", "search"):
			with open(app_file("www", f"{page}.html")) as f:
				source = f.read()
			self.assertNotRegex(source, r"""{%\s*extends\s+["'](?:templates/)?(?:web|base)\.html["']""", page)
			self.assertRegex(
				source, r"base_template_path|extends\s+[\"']quoteshop/templates/qs_base\.html", page
			)


class TestBundleBudget(Storefront):
	def setUp(self):
		super().setUp()
		for name in BUNDLES:
			if not built_bundle(name):
				self.skipTest(f"{name} is not built: run `bench build --app quoteshop` first")

	def test_js_plus_css_under_budget(self):
		total = sum(gzipped_size(built_bundle(name)) for name in BUNDLES)
		self.assertLess(total, BUDGET_BYTES, f"JS+CSS gzipped = {total} bytes")

	def test_bundles_have_no_jquery_or_frappe_web(self):
		for name in BUNDLES:
			with open(built_bundle(name), encoding="utf-8") as f:
				source = f.read().lower()
			self.assertNotIn("jquery", source, name)
			self.assertNotIn("frappe-web", source, name)

	def test_first_catalog_load_under_budget(self):
		"""NFR-09: HTML + the qs bundles the page references, gzipped, excluding images."""
		bundle_total = sum(gzipped_size(built_bundle(name)) for name in BUNDLES)
		for name, page in self.pages().items():
			html_size = len(gzip.compress(page.html.encode(), compresslevel=9))
			self.assertLess(
				html_size + bundle_total, BUDGET_BYTES, f"{name}: html {html_size} + bundles {bundle_total}"
			)
