"""Deterministic storefront data for the Cypress specs (apps/quoteshop/cypress/integration/qs_*.js).

Run once per e2e site: `bench --site <site> execute quoteshop.tests.e2e_seed.seed`. Commits (the browser
talks to a real server). Idempotent. Display order is fixed so the card order is E2E-CUE-1..3, E2E-CHK-1, 2, E2E-CUE-X.
"""

import frappe

from quoteshop.quoteshop_enquiry.tests.factories import (
	make_group_tree,
	make_homepage_settings,
	make_item_price,
	make_published_item,
	make_store_settings,
)

ITEMS = (
	# code, name, group, price, display order
	("E2E-CUE-1", "E2E Cue Alpha", "E2E Cues", 1250, 1),
	("E2E-CUE-2", "E2E Cue Beta", "E2E Cues", 900, 2),
	("E2E-CUE-3", "E2E Cue Gamma", "E2E Cues", 700, 3),
	("E2E-CHK-1", "E2E Chalk Blue", "E2E Chalk", 120, 4),
	("E2E-CHK-2", "E2E Chalk Green", "E2E Chalk", 110, 5),
	("E2E-CUE-X", "E2E Cue Custom", "E2E Cues", None, 6),
)


def seed():
	make_store_settings(
		business_name="E2E Billiards",
		brand_color="#1F4E79",
		default_theme="Auto",
		allow_theme_switch=1,
		show_starting_prices=1,
	)
	make_homepage_settings(hero_title="E2E hero title", hero_subtitle="E2E hero subtitle")
	make_group_tree({"E2E Cues": {}, "E2E Chalk": {}})
	for code, name, group, price, order in ITEMS:
		make_published_item(code, group=group, item_name=name, qs_display_order=order)
		if price and not frappe.db.exists("Item Price", {"item_code": code}):
			make_item_price(code, price)
	frappe.db.commit()
