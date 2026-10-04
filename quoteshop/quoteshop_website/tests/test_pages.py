"""Phase 2 website rendering as Guest (CONTRACTS §5.3, §7.1, §8): /, /c/<route>, /p/<route>, /search?q=.

TEST_MATRIX CAT-02/05/10/11 (page half), CAT-20, CAT-21, SET-09..12, SET-14, NFR-09 (markup half).
Rendering goes through frappe.website (frappe.website.serve.get_response); no server, no network.
Fixture (helpers.Storefront): 5 published items (1 no price, 1 qs_hide_price), 1 unpublished, 1 disabled,
3 published groups (one nested), 1 unpublished group, foreign prices 7777 / 8888 that must never show.
"""

import json
import re
import unittest

import frappe

from quoteshop.quoteshop_website.tests.helpers import (
	THEME_TOGGLE,
	Storefront,
	external_references,
	has_number,
	price_regex,
	render,
)

PRICE_ON_REQUEST = "Price on request"
SECRET_AMOUNTS = (7777, 8888, 4444, 2222, 5555)
ASH_CARD_PRICE = price_regex(1250) + r"\s*·\s*lower for bulk"


class TestCatalogPages(Storefront):
	def test_home_renders(self):
		"""CAT-20: /"""
		page = render("/")
		self.assertEqual(page.status, 200)
		self.assertIn("Acme Billiards", page.text)
		self.assertIn("Acme Billiards", page.soup.title.get_text())
		self.assertIn("Cues, Tables and Chalk", page.text)
		self.assertIn("Everything for the game room", page.text)
		for group in ("_QS Cues", "_QS Chalk"):
			self.assertIn(group, page.text)
			self.assertIn(self.category_path(group), page.links("/c/"))
		for code, name in (
			("_QS-CUE-1", "Ash Cue Pro"),
			("_QS-CASE-1", "Hard Cue Case"),
			("_QS-CHALK-1", "Blue Chalk Box"),
			("_QS-NOPRICE", "Custom Cue"),
			("_QS-SECRET", "Secret Cue"),
		):
			self.assertIn(name, page.text)
			self.assertIn(self.product_path(code), page.links("/p/"))

	def test_home_price_texts(self):
		page = render("/")
		self.assertRegex(page.text, ASH_CARD_PRICE)
		self.assertRegex(page.text, price_regex(800.5))
		self.assertRegex(page.text, price_regex(120))
		self.assertEqual(len(re.findall(r"From\s*₹", page.text)), 3)  # priced cards only
		self.assertIn(PRICE_ON_REQUEST, page.text)  # no price / qs_hide_price
		self.assertFalse(has_number(page.text, 5555))  # hidden price never in the page

	def test_home_hides_unpublished_and_disabled(self):
		page = render("/")
		self.assertEqual(page.status, 200)
		self.assertIn("Ash Cue Pro", page.text)  # control: published item is there
		for name in ("Draft Cue", "Disabled Cue", "_QS Hidden Group"):
			self.assertNotIn(name, page.text)
		self.assertNotIn(self.product_path("_QS-DRAFT"), page.links("/p/"))
		self.assertNotIn(self.category_path("_QS Hidden Group"), page.links("/c/"))

	def test_category_renders(self):
		"""CAT-20: /c/<route> (includes descendants)"""
		page = render(self.category_path("_QS Cues"))
		self.assertEqual(page.status, 200)
		self.assertIn("_QS Cues", page.text)
		for name in (
			"Ash Cue Pro",
			"Custom Cue",
			"Secret Cue",
			"Hard Cue Case",
		):  # last one is in a child group
			self.assertIn(name, page.text)
		self.assertNotIn("Blue Chalk Box", page.text)
		self.assertNotIn("Draft Cue", page.text)
		self.assertRegex(page.text, ASH_CARD_PRICE)

	def test_child_category_renders_only_its_items(self):
		page = render(self.category_path("_QS Cue Cases"))
		self.assertEqual(page.status, 200)
		self.assertIn("Hard Cue Case", page.text)
		self.assertNotIn("Ash Cue Pro", page.text)

	def test_unpublished_group_404(self):
		"""CAT-02"""
		self.assertEqual(render(self.category_path("_QS Chalk")).status, 200)  # control: published group
		self.assertEqual(render(self.category_path("_QS Hidden Group")).status, 404)

	def test_unknown_group_404(self):
		self.assertEqual(render(self.category_path("_QS Chalk")).status, 200)  # control
		self.assertEqual(render("/c/no-such-category").status, 404)

	def test_search_renders(self):
		"""CAT-20: /search?q="""
		page = render("/search", {"q": "chalk"})
		self.assertEqual(page.status, 200)
		self.assertIn("Blue Chalk Box", page.text)
		self.assertNotIn("Ash Cue Pro", page.text)
		self.assertIn(self.product_path("_QS-CHALK-1"), page.links("/p/"))

	def test_search_is_case_insensitive_and_published_only(self):
		upper = render("/search", {"q": "CUE"})
		self.assertEqual(upper.status, 200)
		for name in ("Ash Cue Pro", "Custom Cue", "Hard Cue Case"):
			self.assertIn(name, upper.text)
		for name in ("Draft Cue", "Disabled Cue"):
			self.assertNotIn(name, upper.text)

	def test_search_without_results_and_empty_query_render(self):
		none = render("/search", {"q": "zzzz-nothing"})
		self.assertEqual(none.status, 200)
		self.assertEqual(none.links("/p/"), [])
		self.assertEqual(render("/search").status, 200)
		self.assertEqual(render("/search", {"q": ""}).status, 200)

	def test_search_query_is_escaped(self):
		page = render("/search", {"q": "<script>alert(1)</script>"})
		self.assertEqual(page.status, 200)
		self.assertNotIn("<script>alert(1)</script>", page.html)

	def test_product_renders(self):
		"""CAT-20: /p/<route>"""
		page = render(self.product_path("_QS-CUE-1"))
		self.assertEqual(page.status, 200)
		self.assertIn("Ash Cue Pro", page.text)
		self.assertIn("Handmade ash shaft", page.text)
		self.assertIn("Weight", page.text)
		self.assertIn("19 oz", page.text)
		self.assertRegex(page.text, ASH_CARD_PRICE)
		self.assertIn("Quote", page.text)  # quote_button_label
		self.assertIn(self.category_path("_QS Cues"), page.links("/c/"))
		self.assertIn("Acme Billiards", page.soup.title.get_text())

	def test_product_related_items_published_only(self):
		page = render(self.product_path("_QS-CUE-1"))
		self.assertIn(self.product_path("_QS-CASE-1"), page.links("/p/"))
		self.assertIn("Hard Cue Case", page.text)
		self.assertNotIn(self.product_path("_QS-DRAFT"), page.links("/p/"))
		self.assertNotIn("Draft Cue", page.text)

	def test_quote_button_label_comes_from_settings(self):
		self.set_settings(quote_button_label="Enquire now")
		page = render(self.product_path("_QS-CUE-1"))
		self.assertIn("Enquire now", page.text)

	def test_unpublished_product_404(self):
		"""CAT-05"""
		self.assertEqual(render(self.product_path("_QS-CHALK-1")).status, 200)  # control: published product
		self.assertEqual(render(self.product_path("_QS-DRAFT")).status, 404)

	def test_disabled_product_404(self):
		self.assertEqual(render(self.product_path("_QS-CHALK-1")).status, 200)  # control
		self.assertEqual(render(self.product_path("_QS-OFF")).status, 404)

	def test_unknown_product_404(self):
		self.assertEqual(render(self.product_path("_QS-CHALK-1")).status, 200)  # control
		self.assertEqual(render("/p/no-such-product").status, 404)

	def test_unpublish_removes_product_from_pages_and_cache(self):
		"""CAT-03/04/05 end to end: warm the pages, unpublish, every page forgets the item."""
		path = self.product_path("_QS-CHALK-1")
		self.assertEqual(render(path).status, 200)
		self.assertIn("Blue Chalk Box", render("/").text)
		item = frappe.get_doc("Item", "_QS-CHALK-1")
		item.qs_published = 0
		item.save(ignore_permissions=True)
		self.assertEqual(render(path).status, 404)
		self.assertNotIn("Blue Chalk Box", render("/").text)
		self.assertNotIn("Blue Chalk Box", render("/search", {"q": "chalk"}).text)
		self.assertNotIn("Blue Chalk Box", render(self.category_path("_QS Chalk")).text)

	def test_no_foreign_data(self):
		"""CAT-20: nothing that is not published/public: other price lists, standard rate, hidden prices, drafts."""
		for name, page in self.pages().items():
			for amount in SECRET_AMOUNTS:
				self.assertFalse(has_number(page.text, amount), f"{amount} leaked on {name}")
			for secret in ("Draft Cue", "_QS-DRAFT", "Disabled Cue", "_QS Hidden Group", "Administrator"):
				self.assertNotIn(secret, page.html, f"{secret} leaked on {name}")


class TestPricesVisibility(Storefront):
	def all_pages(self):
		return {
			"home": render("/"),
			"category": render(self.category_path("_QS Cues")),
			"search": render("/search", {"q": "chalk"}),
			"product": render(self.product_path("_QS-CHALK-1")),
		}

	def test_price_on_request_global(self):
		"""CAT-10: show_starting_prices off -> 'Price on request' everywhere, no number leaks"""
		self.set_settings(show_starting_prices=0)
		for name, page in self.all_pages().items():
			self.assertEqual(page.status, 200, name)
			self.assertIn(PRICE_ON_REQUEST, page.text, name)
			self.assertNotRegex(page.text, r"From\s*₹", name)
			for amount in (1250, 120):
				self.assertFalse(has_number(page.text, amount), f"{amount} on {name}")

	def test_price_on_request_per_item(self):
		"""CAT-11"""
		page = render(self.product_path("_QS-SECRET"))
		self.assertEqual(page.status, 200)
		self.assertIn(PRICE_ON_REQUEST, page.text)
		self.assertNotRegex(page.text, r"From\s*₹")
		self.assertFalse(has_number(page.text, 5555))

	def test_price_on_request_without_price(self):
		page = render(self.product_path("_QS-NOPRICE"))
		self.assertIn(PRICE_ON_REQUEST, page.text)

	def test_price_visible_when_shown(self):
		page = render(self.product_path("_QS-CHALK-1"))
		self.assertRegex(page.text, price_regex(120) + r"\s*·\s*lower for bulk")
		self.assertNotIn(PRICE_ON_REQUEST, page.text)

	def test_price_suffix_from_settings(self):
		self.set_settings(price_suffix="per box")
		page = render(self.product_path("_QS-CHALK-1"))
		self.assertRegex(page.text, price_regex(120, "per box"))


class TestSettingsReflection(Storefront):
	def home_settings(self, **values):
		doc = frappe.get_doc("QS Homepage Settings")
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc

	def test_settings_change_reflects_on_home(self):
		"""SET-09: name, hero text, hero buttons, sections, prices toggle without code"""
		first = render("/")
		self.assertIn("Acme Billiards", first.text)
		self.set_settings(business_name="Zenith Cues")
		self.home_settings(
			hero_title="New hero headline",
			hero_subtitle="New hero words",
			hero_primary_label="Browse everything",
			hero_primary_link="/search",
		)
		page = render("/")
		self.assertIn("Zenith Cues", page.text)
		self.assertNotIn("Acme Billiards", page.text)
		self.assertIn("New hero headline", page.text)
		self.assertIn("New hero words", page.text)
		self.assertNotIn("Cues, Tables and Chalk", page.text)
		(button,) = [
			a for a in page.soup.find_all("a", href="/search") if "Browse everything" in a.get_text()
		]
		self.assertIsNotNone(button)

	def test_disabled_section_is_not_rendered(self):
		doc = frappe.get_doc("QS Homepage Settings")
		doc.set("section_order", [{"section": "Hero", "enabled": 1}, {"section": "Products", "enabled": 0}])
		doc.save(ignore_permissions=True)
		page = render("/")
		self.assertIn("Cues, Tables and Chalk", page.text)
		self.assertNotIn("Ash Cue Pro", page.text)

	def test_trust_line_section(self):
		doc = frappe.get_doc("QS Homepage Settings")
		doc.set("section_order", [{"section": "Hero", "enabled": 1}, {"section": "Trust line", "enabled": 1}])
		doc.set("trust_points", [{"text": "Free delivery over five thousand"}])
		doc.save(ignore_permissions=True)
		self.assertIn("Free delivery over five thousand", render("/").text)
		doc.set("section_order", [{"section": "Hero", "enabled": 1}])
		doc.save(ignore_permissions=True)
		self.assertNotIn("Free delivery over five thousand", render("/").text)

	def test_business_name_reflects_on_every_page(self):
		self.set_settings(business_name="Zenith Cues")
		for name, page in self.pages().items():
			self.assertIn("Zenith Cues", page.soup.title.get_text(), name)

	def test_products_per_page_reflects_on_listing(self):
		self.set_settings(products_per_page=2)
		page = render("/search", {"q": "cue"})
		self.assertEqual(len(page.links("/p/")), 2)


class TestTheme(Storefront):
	def test_data_theme_attribute_from_settings(self):
		"""SET-12: server fallback = default_theme lowercased; Auto -> light"""
		for setting, expected in (("Light", "light"), ("Dark", "dark"), ("Auto", "light")):
			self.set_settings(default_theme=setting)
			for route in ("/", self.product_path("_QS-CUE-1"), self.category_path("_QS Cues")):
				page = render(route)
				self.assertEqual(page.soup.html.get("data-theme"), expected, f"{setting} {route}")

	def test_brand_color_variable_rendered(self):
		"""SET-11: inline :root{--accent:<brand_color>}"""

		def accent(page):
			css = " ".join(style.get_text() for style in page.soup.find_all("style"))
			match = re.search(r"--accent\s*:\s*(#[0-9A-Fa-f]{3,8})", css)
			return match.group(1).upper() if match else None

		self.assertEqual(accent(render("/")), "#1F4E79")
		self.set_settings(brand_color="#B0301F")
		for route in ("/", self.product_path("_QS-CUE-1")):
			self.assertEqual(accent(render(route)), "#B0301F", route)

	def test_inline_theme_script_contract(self):
		"""§8: inline head script reads localStorage['qs-theme'] and prefers-color-scheme (no flash)."""
		self.set_settings(default_theme="Auto", allow_theme_switch=1)
		page = render("/")
		inline = " ".join(s.get_text() for s in page.soup.head.find_all("script") if not s.get("src"))
		self.assertIn("qs-theme", inline)
		self.assertIn("prefers-color-scheme", inline)
		self.assertIn("data-theme", inline)

	def test_toggle_present_when_switch_allowed(self):
		self.set_settings(allow_theme_switch=1)
		for route in ("/", self.product_path("_QS-CUE-1")):
			self.assertGreaterEqual(len(render(route).soup.select(THEME_TOGGLE)), 1, route)

	def test_toggle_hidden_when_switch_disabled(self):
		"""SET-14"""
		self.set_settings(allow_theme_switch=0)
		for route in ("/", self.product_path("_QS-CUE-1"), self.category_path("_QS Cues")):
			page = render(route)
			self.assertEqual(page.status, 200, route)
			self.assertEqual(page.soup.select(THEME_TOGGLE), [], route)


class TestMarkup(Storefront):
	def test_no_jquery_and_no_frappe_web_bundle(self):
		for name, page in self.pages().items():
			self.assertNotRegex(page.html.lower(), r"jquery", name)
			self.assertNotIn("frappe-web.bundle", page.html, name)
			self.assertNotIn("frappe.csrf_token", page.html, name)

	def test_only_qs_bundle_assets(self):
		for name, page in self.pages().items():
			scripts = [s["src"] for s in page.soup.find_all("script", src=True)]
			styles = [
				link["href"]
				for link in page.soup.find_all("link", href=True)
				if "stylesheet" in (link.get("rel") or [])
			]
			self.assertTrue(scripts, f"{name}: no script")
			self.assertTrue(styles, f"{name}: no stylesheet")
			for url in scripts + styles:
				self.assertIn("qs.bundle", url, f"{name}: {url}")
			for script in page.soup.find_all("script", src=True):
				self.assertTrue(
					script.has_attr("defer") or script.has_attr("async"), f"{name}: {script['src']}"
				)

	def test_no_external_hosts_or_cdn(self):
		for name, page in self.pages().items():
			self.assertEqual(external_references(page), [], name)
			self.assertNotRegex(page.html.lower(), r"cdn\.|googleapis|gstatic|cloudflare|unpkg", name)

	def test_title_description_canonical(self):
		for name, page in self.pages().items():
			self.assertTrue(page.soup.title and page.soup.title.get_text().strip(), name)
			self.assertTrue(page.meta("description").strip(), f"{name}: meta description")
			self.assertTrue(page.soup.find("link", rel="canonical"), f"{name}: canonical")

	def test_json_ld_is_valid_when_present(self):
		for name, page in self.pages().items():
			for script in page.soup.find_all("script", type="application/ld+json"):
				data = json.loads(script.get_text())
				self.assertIn("@type", data if isinstance(data, dict) else data[0], name)

	def test_product_description_is_item_specific(self):
		page = render(self.product_path("_QS-CUE-1"))
		self.assertNotEqual(
			page.meta("description"), render(self.product_path("_QS-CHALK-1")).meta("description")
		)

	def assert_images(self, name, page, high_priority):
		images = page.soup.find_all("img")
		for img in images:
			where = f"{name}: {img}"
			if img.get("aria-hidden") != "true" and img.get("role") != "presentation":
				self.assertTrue(img.get("alt", "").strip(), f"{where}: alt")
			self.assertRegex(img.get("width", ""), r"^\d+$", f"{where}: width")
			self.assertRegex(img.get("height", ""), r"^\d+$", f"{where}: height")
			if img.get("fetchpriority") == "high":
				self.assertNotEqual(img.get("loading"), "lazy", f"{where}: LCP image must not be lazy")
			else:
				self.assertEqual(img.get("loading"), "lazy", f"{where}: loading")
		high = [img for img in images if img.get("fetchpriority") == "high"]
		self.assertLessEqual(len(high), 1, f"{name}: one LCP image")
		if high_priority:
			self.assertEqual(len(high), 1, f"{name}: LCP image needs fetchpriority=high")

	def test_images_have_alt_size_and_loading(self):
		pages = self.pages()
		self.assertTrue(pages["home"].soup.find("img"), "home has images")
		self.assert_images("home", pages["home"], high_priority=True)  # hero
		self.assert_images("category", pages["category"], high_priority=False)
		self.assert_images("search", pages["search"], high_priority=False)
		self.assert_images("product", pages["product"], high_priority=True)  # first photo

	def test_alt_text_comes_from_photo_row(self):
		self.assertIn("Ash cue front", [img.get("alt") for img in render("/").soup.find_all("img")])
		self.assertIn(
			"Ash cue front",
			[img.get("alt") for img in render(self.product_path("_QS-CUE-1")).soup.find_all("img")],
		)

	def test_srcset_when_sizes_exist(self):
		def srcsets(page):
			return " ".join(img["srcset"] for img in page.soup.find_all("img") if img.get("srcset"))

		self.assertIn("/files/ash-400.webp 400w", srcsets(render("/")))
		product = srcsets(render(self.product_path("_QS-CUE-1")))
		for url, width in (("ash-400", 400), ("ash-1000", 1000), ("ash-1800", 1800)):
			self.assertIn(f"/files/{url}.webp {width}w", product)
		self.assertTrue(
			all(
				img.get("sizes")
				for img in render(self.product_path("_QS-CUE-1")).soup.find_all("img", srcset=True)
			)
		)

	def test_item_without_photo_has_no_broken_image(self):
		page = render(self.product_path("_QS-NOPRICE"))
		self.assertEqual(page.status, 200)
		for img in page.soup.find_all("img"):
			self.assertTrue(img.get("src"), "img without src")


class TestCacheHeaders(Storefront):
	"""CAT-21. Frappe page-caches static www routes only (and never with a query string); /c and /p are
	dynamic routes (CONTRACTS §5.3) so they rely on the catalog cache. force_website_cache bypasses dev mode."""

	def setUp(self):
		super().setUp()
		frappe.flags.force_website_cache = True
		frappe.cache.delete_keys("website_page::")

	def test_guest_catalog_cache_headers(self):
		page = render("/")
		self.assertEqual(page.status, 200)
		self.assertIn("Acme Billiards", page.text)  # the QS home, not a login/404 page
		self.assertFalse(frappe.local.no_cache, "home must not set no_cache")
		self.assertTrue(
			frappe.local.response_headers.get("Cache-Control", "").startswith("private,max-age="),
			frappe.local.response_headers.get("Cache-Control"),
		)
		again = render("/")
		self.assertEqual(again.response.headers["X-From-Cache"], "True")
		self.assertEqual(again.html, page.html)

	def test_no_per_user_bits_in_guest_pages(self):
		for name, page in self.pages().items():
			self.assertNotIn("csrf_token", page.html, name)
			self.assertNotIn("sid=", page.html, name)

	def test_dynamic_pages_never_send_no_store(self):
		for route in (self.product_path("_QS-CUE-1"), self.category_path("_QS Cues")):
			self.assertEqual(render(route).status, 200, route)
			self.assertNotIn("no-store", frappe.local.response_headers.get("Cache-Control", ""), route)

	def test_settings_save_invalidates_cache(self):
		"""SET-10: a cached home page shows new settings after save."""
		self.assertIn("Acme Billiards", render("/").text)
		self.assertEqual(render("/").response.headers["X-From-Cache"], "True")
		self.set_settings(business_name="Zenith Cues")
		page = render("/")
		self.assertIn("Zenith Cues", page.text)
		self.assertNotIn("Acme Billiards", page.text)

	def test_item_change_invalidates_cached_home(self):
		self.assertIn("Blue Chalk Box", render("/").text)
		self.assertEqual(render("/").response.headers["X-From-Cache"], "True")
		item = frappe.get_doc("Item", "_QS-CHALK-1")
		item.qs_published = 0
		item.save(ignore_permissions=True)
		self.assertNotIn("Blue Chalk Box", render("/").text)

	def test_item_price_change_invalidates_cached_home(self):
		self.assertRegex(render("/").text, price_regex(120))
		self.assertEqual(render("/").response.headers["X-From-Cache"], "True")
		from quoteshop.quoteshop_enquiry.tests.factories import make_item_price

		make_item_price("_QS-CHALK-1", 99, valid_from=frappe.utils.today())
		self.assertRegex(render("/").text, price_regex(99))

	@unittest.skip(
		"Set-Cookie is added by frappe.app (session/cookie manager), not by website.serve.get_response, "
		"so it cannot be asserted from a router-level render; needs a live server (Cypress/curl in qa)."
	)
	def test_guest_response_sets_no_cookie(self):
		pass


class TestRouting(Storefront):
	def test_route_rules_and_home_page_hooks(self):
		rules = frappe.get_hooks("website_route_rules", app_name="quoteshop")
		self.assertIn({"from_route": "/p/<route>", "to_route": "p"}, rules)
		self.assertIn({"from_route": "/c/<route>", "to_route": "c"}, rules)
		self.assertEqual(frappe.get_hooks("home_page", app_name="quoteshop"), ["index"])

	def test_no_global_web_includes(self):
		"""§5.3: bundles only via qs_base.html; never web_include_js/css (they leak into other pages)."""
		self.assertEqual(frappe.get_hooks("web_include_js", app_name="quoteshop"), [])
		self.assertEqual(frappe.get_hooks("web_include_css", app_name="quoteshop"), [])
