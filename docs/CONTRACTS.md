# QuoteShop – CONTRACTS

Owner: orchestrator only. Sub-agents read, never edit. Source of truth for every name an agent may use.
Verified against: frappe 16.36.1 · erpnext 16.37.0 · hrms 16.20.1 · crm 1.86.0 (main) · frappe_whatsapp 1.0.12 (master) · payments version-16 (test site only).
Paths: `frappe/…` = apps/frappe/frappe, `erpnext/…` = apps/erpnext/erpnext, `crm/…` = apps/crm/crm, `fw/…` = apps/frappe_whatsapp/frappe_whatsapp.

Status tags: **FIXED** = verified fact or agreed rule · **PROPOSED** = §9 decision (all approved 2026-10-04, now binding) · **TBD** = filled in by a later phase.

---

## 1. Sites and environment (FIXED)
- quoteshop.localhost: dev, developer_mode, default site, `allow_tests` false. Never run tests here.
- staging.localhost: phase V target.
- test.localhost: all tests (`bench --site test.localhost run-tests --app quoteshop`). Has `payments` installed (ERPNext test records need `Payment Gateway`).
- Test deps installed in env: freezegun, responses, coverage, faker, hypothesis.
- Company "JAI BALAJI BILLIARDS" (INR, India) and Fiscal Year `2026-2027` exist on quoteshop.localhost only.
- Tests NEVER rely on site data (CI uses a fresh site with no Company/Fiscal Year/Warehouse). Company, Fiscal Year, Warehouse, Price List, Customer Group, Territory come from QS test factories (or ERPNext `_Test` records via `EXTRA_TEST_RECORD_DEPENDENCIES`). Frozen dates must fall inside the factory-created Fiscal Year.

## 2. ERPNext / Frappe standard DocTypes

### 2.1 Where custom fields go (last field of the form)
| DocType | Tab layout | insert "Storefront" Tab Break after |
|---|---|---|
| Item | ends with tab `dashboard_tab` (Connections) | PROPOSED `prices_html` (Storefront before Connections) |
| Item Group | no tabs | `rgt` (adding a Tab Break auto-creates a first "Details" tab) |
| Sales Order | ends with `connections_tab` | PROPOSED `party_account_currency` |
| Sales Order Item | child, no tabs | `qs_requested_qty` insert_after `qty` (next std field is `stock_uom`); not in_list_view |
| CRM Deal | n/a in Desk tabs list | Desk: "Storefront" Tab Break at end (TBD after layout map); Vue UI: §3.4 |
Every field chains `insert_after` to the previous QS field. Assert final order from `frappe.get_meta(dt).fields` (layout test).
Custom Fields/Property Setters: set `module` on each; export with `export_customizations(module, doctype, sync_on_migrate=1, apply_module_export_filter=1)` → `<module>/custom/<doctype>.json` (frappe/modules/utils.py:58). Sync is upsert-only; removing a field needs a patch.

### 2.2 Item (`erpnext/stock/doctype/item/item.json`)
Name = `item_code` (unique). Required: `item_code`, `item_group`, `stock_uom` (site default "Nos"). Use: `item_name`, `description` (Text Editor), `image` (hidden, form image_field), `disabled` (indexed), `has_variants`, `variant_of`, `is_sales_item`, `is_stock_item` (default 1), `brand`, `max_discount`.
No website fields exist in v16 (webshop app not installed). Template items (`has_variants=1`) cannot have an Item Price.

### 2.3 Item Group (`erpnext/setup/doctype/item_group/item_group.json`)
NestedSet. Name = `item_group_name`. Fields `parent_item_group`, `is_group`, `image`, `lft`, `rgt`.

### 2.4 Item Price / Price List
- Item Price required: `item_code`, `uom`, `price_list`, `price_list_rate`. `valid_from` defaults Today. Unique on item+list+uom+valid_from+valid_upto+customer+supplier+batch+packing_unit.
- Starting price query (FIXED): `price_list = settings.starting_price_list AND selling=1 AND IFNULL(customer,'')='' AND valid_from<=today AND (valid_upto IS NULL OR valid_upto>=today) AND uom = item.stock_uom`, newest `valid_from` wins.
- Price List "Website Starting Price" does NOT exist → created by quoteshop after_install (selling=1, currency = company currency, enabled=1).

### 2.5 Contact (`frappe/contacts/doctype/contact/contact.py`)
- `mobile_no`, `email_id`, `phone` are read-only, recomputed in validate from child tables. Add via `contact.add_phone(phone, is_primary_mobile_no=1)`, `contact.add_email(email, is_primary=1)`; links via `contact.append("links", {"link_doctype","link_name"})`.
- Lookup by mobile (FIXED): exact `Contact.mobile_no = <E.164>`; QS always stores E.164 with leading `+`. `Contact.mobile_no` is unindexed → quoteshop adds a Property Setter `search_index=1` (phase 1). Contacts stored in other formats (CRM UI, manual) will not match → QS normalises on lookup only for its own records; existing non-E.164 contacts may duplicate (accepted, documented). DO NOT use `get_contact_with_phone_number` (LIKE scan).
- Portal: set `Contact.user` explicitly. "Website User" is a User Type, not a Role.
- CRM overrides the Contact class (`crm.overrides.contact.CustomContact`), and separately a `doc_events` hook `Contact.validate → crm.api.contact.validate` pushes contact email/mobile onto deals where the contact is primary.

### 2.6 Customer (`erpnext/selling/doctype/customer/customer.py`)
Name = `customer_name` (" - N" on clash). Required `customer_name`, `customer_type` (Company/Individual/Partnership). Use `customer_group`, `territory`, `account_manager` (Link User), `customer_primary_contact`, `default_price_list`.
GOTCHA (FIXED rule): always set `customer_primary_contact = <QS contact>` on insert. Without it, any of mobile_no/email_id/first_name/last_name triggers `create_primary_contact` (customer.py:302) → duplicate Contact. (With it set, it also marks the Contact `is_primary_contact=1`, running Contact save hooks.) Then append a Dynamic Link (Customer) to the Contact.
Naming by customer_name relies on Selling Settings `cust_master_name="Customer Name"`. Selling Settings `customer_group`/`territory` fields exist but are empty → QS Store Settings supplies them. If an admin enables `validate_selling_price`, offered rates below cost would make order creation throw (surface as a clear error).

### 2.7 Sales Order + Sales Order Item (`erpnext/selling/doctype/sales_order/…`)
Header set by QS: `customer`, `company`, `transaction_date`, `order_type="Sales"`, `selling_price_list = settings.starting_price_list`, `ignore_pricing_rule=1`, `set_warehouse` (PROPOSED §9), `contact_person`, `qs_enquiry`, `qs_version`. Currency/price-list fields are filled by `set_missing_values`.
Line set by QS: `item_code`, `qty = offered_qty`, `uom`, `price_list_rate = listed_rate`, `rate = offered_rate`, `discount_percentage = 0`, `delivery_date`, `qs_requested_qty`. Leave `discount_amount`, `margin_*` unset.
Result after validate (erpnext/controllers/taxes_and_totals.py:168-224): `rate` kept, `discount_amount = listed − offered` when offered < listed, margin "Amount" when offered > listed.
Rules: `offered_rate` must be > 0 for any line with `offered_qty > 0` (rate 0 is overwritten with price_list_rate). Line `delivery_date` ≥ `transaction_date`; header `delivery_date` becomes the max line date. Stock items need a warehouse.
Do not use: `/orders`, `/invoices`, `/quotations` routes (ERPNext portal); `order_type="Shopping Cart"`.

## 3. Frappe CRM

### 3.1 CRM Deal (`crm/fcrm/doctype/crm_deal/crm_deal.json`)
Naming `CRM-DEAL-.YYYY.-`. Key fields: `status` (Link CRM Deal Status, reqd), `deal_owner` (Link User), `contacts` (Table CRM Contacts: `contact`, `is_primary`), `contact`, `mobile_no`, `email`, `products` (Table CRM Products), `total`, `net_total`, `deal_value`, `expected_deal_value`, `lost_reason` (Link CRM Lost Reason), `lost_notes`, `closed_date`, `currency`.
Create (FIXED): `frappe.new_doc("CRM Deal")`, set `contacts=[{"contact": c, "is_primary": 1}]`, `qs_enquiry`, `qs_buyer_type`, `qs_version`, `deal_value`, optional `deal_owner`; `insert(ignore_permissions=True)`.
Do not: set `mobile_no`/`email` directly (overwritten from primary contact); use `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` (it creates/dedupes Contacts itself).
Deal value: set `deal_value` only. Do not fill `products` (CRM totals are computed in browser JS only and need CRM Product records). This departs from PHASES §4 "mirror lines into the CRM products table" → §9 item 12.

### 3.2 Deal statuses (`CRM Deal Status`: `deal_status`, `type` Open|Ongoing|On Hold|Won|Lost, `color`, `position`, `probability`)
Colours allowed: black gray blue green red pink orange amber yellow cyan teal violet purple (no `darkgrey`).
Won/Lost decided by `type`. Resolve Won as `frappe.db.get_value("CRM Deal Status", {"type": "Won"})`. Lost requires `lost_reason`; `lost_notes` too when reason is "Other".
Status set by QS (PROPOSED §9): see §9 item 5.

### 3.3 Assignment
- `deal_owner` set on insert → CRM shares + assigns (ToDo) + notifies. ToDo after_insert copies the latest assignee back into `deal_owner`.
- QS priority: buyer-type `default_assignee` → `Customer.account_manager` → leave `deal_owner` empty and let a frappe Assignment Rule on CRM Deal assign. Set `deal_owner` ONLY when QS resolves someone (avoids double assignment).
- After insert read `deal_owner` (fallback `_assign`) into `QS Enquiry.assigned_to`.

### 3.4 CRM Vue layout (`CRM Fields Layout`, name `CRM Deal-Side Panel`)
Idempotent patch/after_install: load layout JSON; if no section `name == "qs_enquiry_section"`, append
`{"label":"Enquiry","name":"qs_enquiry_section","opened":true,"columns":[{"name":"qs_col","fields":["qs_enquiry","qs_buyer_type","qs_version","qs_open_quote"]}]}`; save with ignore_permissions. Merge, never overwrite. Do not use `save_fields_layout` with full JSON.
`qs_open_quote`: Custom Field, fieldtype HTML, options `<a href="/app/qs-enquiry/{{ qs_enquiry }}">Open quote</a>` (CRM interpolates `{{ field }}`, DOMPurify-sanitised).
Note: CRM rewrites the side panel's `lost_reason_section` on every status change; other sections survive.

### 3.5 CRM ↔ ERPNext auto-sync (FIXED: never used by QS)
ERPNext CRM Settings is disabled on all sites. QS owns Customer + Sales Order creation. after_install/settings validate warns if `ERPNext CRM Settings.enabled and create_customer_on_status_change` (would duplicate Customers on Won).

### 3.6 CRM's WhatsApp hooks (crm/hooks.py:260)
`WhatsApp Message.validate` overwrites `reference_doctype/reference_name` with the Contact/Lead/Deal matched by phone (picks an arbitrary deal if the contact is primary on several). Therefore:
- Outgoing QS messages set `reference_doctype="CRM Deal"`, `reference_name=<deal>` anyway; CRM may overwrite it with the Contact/Lead/another deal matched by phone.
- QS never reads `WhatsApp Message.reference_*` to find an enquiry; it uses its own message log (§4.3).

### 3.7 Routes
CRM SPA `/crm`, deal `/crm/deals/<name>`. Desk `/app/crm-deal/<name>`, `/app/qs-enquiry/<name>`.

## 4. frappe_whatsapp

### 4.1 Sending (`fw/frappe_whatsapp/doctype/whatsapp_message/whatsapp_message.py`)
HTTP call to Meta happens synchronously in `before_insert` (before validate/db_insert). Therefore every QS send runs in a job: `frappe.enqueue(..., enqueue_after_commit=True, job_id=f"qs-wa-{enquiry}-{version}-{event}")`; the job first checks the QS message log for an existing `message_id` for (enquiry, version, event). Guarantee is at most once per successful insert: if anything fails after the POST, the message may be sent without a stored id, so send jobs are NOT auto-retried (failures go to Error Log for manual resend).
Template send:
```python
frappe.get_doc(
	{
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"to": mobile_e164,
		"content_type": "document" | "text",
		"use_template": 1,
		"template": template_name,
		"body_param": json.dumps(ordered_params),  # dict; values() used in order
		"attach": public_pdf_url,  # header DOCUMENT; filename forced to document.pdf
		"reference_doctype": "CRM Deal",
		"reference_name": deal,
	}
).insert(ignore_permissions=True)
# → doc.message_id stored in the QS message log
```
Body params only sent if the template has `sample_values`. frappe_whatsapp needs a `WhatsApp Account` with `is_default_outgoing=1` (status ignored). CRM additionally requires `WhatsApp Settings.default_outgoing_account` set and that account status Active (crm/api/whatsapp.py:103). Set both.

### 4.2 Templates (`WhatsApp Templates`, buttons child `WhatsApp Button`)
QS settings only LINK existing approved templates (created in Meta + fetched, or created in Desk by admin). Never insert templates from after_install (calls Meta). "Template placeholders" (SPEC §3, PHASES §1) = the 7 template Link fields in QS Enquiry Settings left empty, plus a README list of templates to register → §9 item 13.
Quick-reply button payload = button label (no custom payload). Dynamic URL buttons are broken in the stock path. → see §9 items 1–2.

### 4.3 Incoming (`fw/utils/webhook.py`, guest, no signature check)
Quick reply arrives as WhatsApp Message `type="Incoming"`, `content_type="button"`, `message=<button label>`, `reply_to_message_id=<our outgoing message_id>`, `from=<digits, no +>`. Payload is not stored.
QS hook: `doc_events["WhatsApp Message"]["after_insert"] = "quoteshop.quoteshop_enquiry.whatsapp.on_whatsapp_message"` (TBD path, phase 4). Handler: return unless `type=="Incoming"`; never raise; enqueue after commit with `job_id=f"qs-wa-in-{message_id}"`; inside the job match `reply_to_message_id` → QS message log → (enquiry, version, event); verify `"+" + from == enquiry.mobile`; map label → action; act idempotently.
Duplicate Meta deliveries create duplicate WhatsApp Messages → dedupe by `message_id` in the job.

### 4.4 QS message log (PROPOSED, phase 4 data-model)
Child table `QS Enquiry Message` on QS Enquiry: `version` (Int), `event` (Select: enquiry_received_buyer, enquiry_alert_sales, price_sent, accepted, changes_requested, version_outdated), `direction` (Outgoing/Incoming), `message_id` (Data, indexed via `search_index`), `whatsapp_message` (Link), `sent_on`. Lookups by `message_id` go through this table, not `tabWhatsApp Message` (unindexed).

### 4.5 Test mocks (FIXED)
- Outgoing: patch `frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message.make_post_request` → `{"messages": [{"id": "wamid.TEST..."}]}`; assert on `json.loads(call.kwargs["data"])`. Never make it raise.
- Templates: create with `frappe.get_doc(...).db_insert()` or patch `…whatsapp_templates.whatsapp_templates.make_post_request`.
- Incoming: `frappe.local.form_dict = <Meta payload>`; call `frappe_whatsapp.utils.webhook.post()`.
- Fixture: `WhatsApp Account` (`is_default_outgoing=1`, `is_default_incoming=1`, `phone_id` matching payload `metadata.phone_number_id`, status Active).

## 5. Frappe v16 framework

### 5.1 Tests
- `from frappe.tests import UnitTestCase, IntegrationTestCase`.
- Helpers (context manager / decorator / `self.x`): `freeze_time(dt)`, `set_user(user)`, `change_settings(doctype, {...})` (Integration only), `patch_hooks({...})`.
- `self.assertQueryCount(n, query_type=None)` asserts ≤ n; `assertRedisCallCounts`, `assertRowsRead`.
- Test records: `test_records.toml`; `EXTRA_TEST_RECORD_DEPENDENCIES` / `IGNORE_TEST_RECORD_DEPENDENCIES` module attributes (QS Enquiry tests ignore Customer, CRM Deal, Sales Order deps and build data via factories).
- Jobs with `enqueue_after_commit=True` never run in tests (no commit; and running after_commit only pushes to Redis, no worker in CI). Tests patch `frappe.enqueue`, assert its args (method, job_id, enqueue_after_commit), then call the job function directly.
- `freeze_time` does not move Redis TTLs → OTP stores `expires_at` inside the payload and checks it.
- Rate limits only apply when `frappe.request` is set. Tests use the test client against `/api/method/<path>` (v1 sets `form_dict.cmd`), or `set_request(...)` plus explicitly `frappe.local.request_ip = "…"` and `frappe.form_dict.cmd = "<dotted.path>"` (set_request sets neither; without cmd all endpoints share key `rl:None:…`).
- Website render in tests: `frappe.utils.get_html_for_route(route)`.

### 5.2 rate_limit
`from frappe.rate_limiter import rate_limit` (NOT `frappe.rate_limit`). Signature `rate_limit(key=None, limit=5, seconds=86400, methods="ALL", ip_based=True)`. `key` reads `frappe.form_dict[key]`. Per-number + per-IP = two stacked decorators: `@rate_limit(key="mobile", ip_based=False, limit=…, seconds=…)` and `@rate_limit(limit=…, seconds=…)`.

### 5.3 Website
- Routes (hooks): `website_route_rules = [{"from_route": "/p/<route>", "to_route": "p"}, {"from_route": "/c/<route>", "to_route": "c"}, {"from_route": "/q/<name>", "to_route": "q"}]`. `/`, `/quote`, `/account`, `/search` are plain www pages. No clash with installed apps.
- Base template: QS pages use `quoteshop/templates/qs_base.html` (never extend `templates/web.html`/`base.html`: they load frappe-web.bundle.js, breaks the budget). Wire via hook `base_template_map` or per-page `base_template_path`.
- Assets: `quoteshop/public/js/qs.bundle.js`, `quoteshop/public/css/qs.bundle.css`; include with `{{ include_script("qs.bundle.js") }}` / `{{ include_style("qs.bundle.css") }}` in qs_base.html only. Never `web_include_js/css`.
- Page cache: dynamic routes and dev mode are never page-cached; page cache is not per-user. Performance comes from the catalog Redis cache. Pages with per-user bits set `no_cache = 1` (or render those bits in JS).
- Catalog cache keys: `frappe.cache.set_value(f"qs:catalog:{hash_of_params}", payload, expires_in_sec=…)` / `get_value(..., expires=True)`; invalidate with `frappe.cache.delete_keys("qs:catalog:")` from Item, Item Group, Item Price and settings `on_update`/`on_trash`, plus hook `website_clear_cache`. Do not use `@redis_cache` (process-salted keys).
- Home page: hook `home_page = "index"` with `quoteshop/www/index.html` (PROPOSED; desk users still land on desk).

### 5.4 Jobs
`frappe.enqueue(method, queue="default", timeout=None, enqueue_after_commit=False, job_id=None, deduplicate=False, **kwargs)`. `deduplicate=True` needs `job_id`. Idempotency is enforced inside the job (e.g. existing Sales Order with `qs_enquiry`), not by `deduplicate` alone.

### 5.5 Tokens, OTP, hashing
Token: `secrets.token_urlsafe(32)`; store `hashlib.sha256(token.encode()).hexdigest()` in `token_hash` + `token_expires`. OTP: `f"{secrets.randbelow(10**6):06d}"`, Redis key `qs:otp:{mobile}` = `{"hash", "expires_at", "attempts"}` with `expires_in_sec=600`.

### 5.6 PDF
`frappe.get_print("QS Enquiry", name, print_format="QS Quote", as_pdf=True)`; wkhtmltopdf 0.12.6 (default generator). Attach as a public File so Meta can fetch it (URL contains an unguessable file name).

### 5.7 Desk artefacts
Number Card, Dashboard Chart, Workspace (+ v16 Desktop Icon / Workspace Sidebar) exported as standard JSON in the quoteshop module and synced on migrate (PROPOSED §9 item 10). Kanban Board "Enquiry Pipeline" via `quick_kanban_board("QS Enquiry", "Enquiry Pipeline", "status")` in an idempotent patch. Saved filters = `List Filter` records.

## 6. QuoteShop fieldnames and phase-1 functions
Fieldnames, types, DocTypes, child tables, roles and placement: **docs/LAYOUT_MAP.md** (single source; layout tests read it).

### 6.1 Totals – `QSEnquiry.set_totals()` (called in `validate`), `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/qs_enquiry.py`
Per line, in one pass:
- default `offered_qty = requested_qty` and `offered_rate = listed_rate` when None.
- `amount = flt(offered_rate * offered_qty, precision("amount"))`.
- a line "counts" unless `availability == "Not Available"` or `change_flag == "Removed"`; non-counting lines have `amount = 0`.
- `offered_rate` must be > 0 for a counting line with `offered_qty > 0` ONLY when `status` is "Price Sent" or "Accepted" (a priced quote). Earlier statuses (Draft/Requested/Changes Requested) may hold unpriced lines (rate 0, e.g. "Price on request" items with no starting price); they count 0 towards totals until priced. `offered_rate` still defaults to `listed_rate`.
- `listed_rate` is a snapshot set once at request (phase 3); `validate` never refreshes or changes it.
- One line per `item_code`: `validate` raises `frappe.ValidationError` on a duplicate item_code (the website merges quantities; versions are diffed by item_code).
Header:
- `total_listed = Σ listed_rate × offered_qty`, `total_offered = Σ amount` (counting lines only), currency precision.
- `total_saved = total_listed − total_offered` (may be negative when offered > listed; NOT clamped — website/print/WhatsApp hide savings when ≤ 0); `saved_pct = flt(total_saved / total_listed × 100, 2)` (0 when total_listed = 0).
- Rounding everywhere: Frappe `flt(value, precision)` (System Settings rounding method), never Python `round()`. Money precision = the field's precision (`self.precision(fieldname)` / `row.precision(fieldname)`).
- `line_count` = lines with `change_flag != "Removed"`; `unit_count = Σ offered_qty` of counting lines.
- `available_count` / `partial_count` / `not_available_count` = lines (not Removed) whose availability is exactly Available / Partial / Not Available.

### 6.2 Diff – `quoteshop/quoteshop_enquiry/diff.py`
`diff_lines(previous: list[dict], current: list[dict], *, rate_precision: int = 2, qty_precision: int = 3) -> dict[str, str]` keyed by `item_code`, value = change_flag. Rows are dicts with item_code, offered_qty, offered_rate, availability, alternative_item. Callers pass field precisions (phase 5).
- in current only → "Added"; in previous only → "Removed"
- "Alternative" when current availability is Alternative AND (previous availability was not Alternative OR `alternative_item` changed); else offered_rate differs → "Price changed"; else offered_qty differs → "Qty changed"; else "".
- Comparisons: `flt(rate, rate_precision)` / `flt(qty, qty_precision)`; `alternative_item` compared as `(value or "")` so None == ""; order-independent. Pure function, no DB. Rows may be dicts or child-table rows (read with `.get`).

### 6.3 Tokens – `quoteshop/quoteshop_enquiry/tokens.py`
- `new_token() -> tuple[str, str]` → (raw `secrets.token_urlsafe(32)`, sha256 hex of raw).
- `hash_token(raw: str) -> str`.
- `is_valid_token(raw: str | None, token_hash: str | None, expires: datetime | None) -> bool` → `hmac.compare_digest(hash_token(raw), token_hash)` and (expires is None or `now_datetime() < expires`; exactly at `expires` = invalid). Raw tokens are never stored. Trust boundary: returns False (never raises) when `raw` or `token_hash` is empty/None.

### 6.4 Settings cache
Read settings only via `frappe.get_cached_doc("QS Store Settings")` (and Homepage/Enquiry); Frappe invalidates on save. `on_update` of all three settings calls `quoteshop.quoteshop_catalog.cache.clear_catalog_cache()` → `frappe.cache.delete_keys("qs:catalog:")`.

### 6.5 Permissions – `quoteshop/quoteshop_enquiry/permissions.py` (hooks `permission_query_conditions` / `has_permission` for "QS Enquiry")
- `enquiry_query_conditions(user: str | None = None) -> str` → "" for System Manager / Sales Manager; for Sales User: `` (`tabQS Enquiry`.assigned_to = {u} or `tabQS Enquiry`.owner = {u} or `tabQS Enquiry`._assign like {%"u"%}) `` (escaped with frappe.db.escape).
- `has_enquiry_permission(doc, ptype: str, user: str | None = None) -> bool` → same rule on one doc.

### 6.6 Install – `quoteshop/install.py` → hook `after_install = "quoteshop.install.after_install"`; also run by patch for existing sites. Idempotent (run twice = no change, no error):
- Price List "Website Starting Price" (selling=1, enabled=1, currency = default company currency, else "INR").
- Brand colour check (QS Store Settings.validate): warn (never block) when WHITE text on `brand_color` has contrast < 4.5:1 (buttons use white on accent); the dark-background check is dropped. Non-hex values (not `#RRGGBB`) are rejected (colour is written inline into CSS).
- Accepted lock: once the stored status is Accepted every save raises; jobs write `sales_order` etc. with `db_set`/`frappe.db.set_value`.
- `qs_price_summary_html` (Sales Order, HTML) is never stored: phase 6 renders it on form load from the linked QS Enquiry (JS) — the criterion "qs fields set" means `qs_enquiry` and `qs_version`.
- `qs_open_quote` is NOT read-only (CRM hides read-only valueless fields); fixed in phase 4 (CRM side panel) with a CRM Form Script / button instead of an HTML link; update the layout test then.
- Role "Catalog Manager" (desk_access=1). DocPerms on standard DocTypes only via `frappe.permissions.add_permission(doctype, role, permlevel=0, ptype)` + `update_permission_property(doctype, role, 0, ptype, 1)` — both call `setup_custom_perms` first, which copies the standard perms so existing roles (Sales User read Item/Item Group, Sales Master Manager write Item Price, …) keep their access. Catalog Manager: Item / Item Group read+write+create; Item Price read+write+create+delete. Perms on QS DocTypes live in their DocType JSON.
- Settings seeding runs ONLY when that Single has no stored values yet (first install); later runs leave settings untouched (so an admin's unchecked box is never re-checked). Seed with `flags.ignore_mandatory = True` and `save(ignore_permissions=True)`.
- QS Store Settings seed: LAYOUT_MAP B1 defaults (brand_color "#146B47" — design default accent, also the DocType default; starting_price_list "Website Starting Price", quote_button_label "Quote", price_suffix "per piece", products_per_page 24, default_theme Auto, allow_theme_switch 1, show_starting_prices 1, show_savings_to_buyer 1) plus site sources, each only if present:
  - `default_company` = `frappe.db.get_single_value("Global Defaults", "default_company")`
  - `default_customer_group` = Selling Settings `customer_group`; `default_territory` = Selling Settings `territory`
  - `default_warehouse` = Stock Settings `default_warehouse`
- Price list currency = `Company.default_currency` of that default company, else "INR".
- QS Enquiry Settings seed: LAYOUT_MAP B3 defaults (login_mode "Not required", otp_required 1, show_business_name 1, show_notes 1, quote_validity_days 15, bulk_tier_2 2, bulk_tier_3 5); the 7 template links stay empty (§9.13).
- QS Homepage Settings seed: show_how_it_works 1 only (content is entered by the admin).
- Never inserts WhatsApp Templates; never touches CRM data (CRM statuses/side panel = phase 4).

## 7. Website + whitelisted APIs

### 7.1 Phase 2 – catalog (module QuoteShop Catalog / QuoteShop Website)
Catalog service `quoteshop/quoteshop_catalog/catalog.py` (pages call these directly in `get_context`; also exposed `@frappe.whitelist(allow_guest=True, methods=["GET"])`):
- `list_products(category: str | None = None, q: str | None = None, page: int = 1) -> dict` → `{"items": [card…], "total": int, "page": int, "page_size": int, "has_more": bool}`.
  - One SQL query (frappe.qb or parametrised SQL) joining Item + starting Item Price (CONTRACTS §2.4 rule, newest valid_from) + first QS Item Photo (lowest idx); plus at most one COUNT query.
  - Filters: `qs_published=1`, `disabled=0`, `has_variants=0`; category = published Item Group by `qs_route`, including descendants (lft/rgt); `q` = case-insensitive LIKE on item_name, item_code, qs_short_description (escape `%`/`_`), max 100 chars.
  - Order: `qs_display_order` asc, `item_name` asc, `name` asc (stable). `page_size = QS Store Settings.products_per_page` (default 24); page < 1 → 1.
  - card = `{item_code, item_name, route, item_group, group_route, short_description, min_qty, image: {thumb, medium, large, alt} | None, starting_price: float | None, currency}`; `starting_price` is None when `show_starting_prices` is off, the item has `qs_hide_price`, or no valid price exists.
- `get_product(route: str) -> dict` → card fields + `description`, `photos: [{thumb, medium, large, alt}]`, `specs: [{label, value}]`, `related: [card]` (published only), `lead_time`, `uom`. Unpublished/disabled/unknown → `frappe.DoesNotExistError` (page renders 404).
- `get_categories() -> list[dict]` → published Item Groups `{name, route, image, display_order}` ordered by qs_display_order, name.
- Cache: `frappe.cache.set_value(key, value, expires_in_sec=86400)` / `get_value(key, expires=True)` with keys `qs:catalog:list:<sha1(json params)>`, `qs:catalog:product:<route>`, `qs:catalog:categories`. Invalidation = `clear_catalog_cache()` from doc_events on Item, Item Group, Item Price (on_update, on_trash, after_rename) and the 3 settings' on_update.
- Query budgets (approved §9.9): list_products ≤5 queries cold / ≤1 warm; get_product ≤8 cold / ≤1 warm.
- Routes (hooks `website_route_rules`): `/c/<route>` → `c`, `/p/<route>` → `p` (later `/q/<name>` → `q`). www pages in `quoteshop/www/`: `index` (home, via hook `home_page = "index"`), `c`, `p`, `search` (`/search?q=`). Unknown/unpublished category or product → `frappe.PageDoesNotExistError` → 404.
- Image pipeline `quoteshop/quoteshop_catalog/images.py`:
  - doc_event Item.on_update → `queue_photo_sizes(doc)`: if any QS Item Photo row lacks sizes or its source changed → `frappe.enqueue("quoteshop.quoteshop_catalog.images.generate_photo_sizes", item_code=…, enqueue_after_commit=True, job_id=f"qs-img-{item_code}", deduplicate=True)`.
  - `generate_photo_sizes(item_code: str) -> None`: per row, WebP widths 400/1000/1800 via Pillow (never upscale: width = min(target, source width)); file name `<stem>-<sha1(source bytes)[:10]>-<w>.webp` as public File attached to the Item; set `thumb`/`medium`/`large` with `frappe.db.set_value` on the child row (no Item save → no loop). Idempotent: if the row's URLs already contain the current source hash → skip (unchanged photos are never reprocessed).

### 7.1b Phase 2 rules (resolved gaps)
- Visibility: an item is listed iff `qs_published=1`, `disabled=0`, `has_variants=0` (its group's publish state does not matter). Category chips/`get_categories` = all published Item Groups, flat, ordered by qs_display_order, name. Category filter = the published group by `qs_route` plus ALL descendants (lft/rgt), published or not. Unknown or unpublished category → `frappe.DoesNotExistError` (page 404).
- Input: `q` is stripped; empty/whitespace → no search; `page` = `cint(page)`, < 1 → 1. Page links use the query param `?page=N` with `rel="next"/"prev"`.
- Prices: Item Price with `valid_from` NULL counts as valid (`IFNULL(valid_from, '1900-01-01') <= today`).
- Money on the website: Indian grouping from the system number format; whole amounts without decimals ("₹1,55,000"), otherwise 2 decimals (`frappe.utils.fmt_money`).
- `qs_route`: generated in Item/Item Group `validate` (doc_event) when published and empty: slug of item_name / item_group_name (lowercase, a–z 0–9, hyphens), unique per doctype by appending `-2`, `-3`… Never changed once set; unpublished docs keep theirs.
- Images: a photo without generated sizes falls back to its original `image` URL for thumb/medium/large. `alt` = `alt_text` or the item name. File name `<stem>-<sha1(source)[:10]>-<target>.webp` where `<target>` is the TARGET width (400/1000/1800); actual width = min(target, source width).
- Loading: one `fetchpriority="high"` image per page (hero on `/`, first photo on `/p`); every other `<img>` `loading="lazy"` except the header logo (`data-qs-logo`, eager). Every `<img>` has width + height; hero dimensions are read once from the file with Pillow and cached with the catalog cache.
- Homepage: empty `section_order` → default order Hero, Promo tiles, Trust line, How it works, Categories, Products (all enabled).
- Cache: `clear_catalog_cache()` also calls `frappe.website.utils.clear_website_cache()` so the page-cached `/` refreshes after Item/Item Group/Item Price/settings changes. `/c` and `/p` are never page-cached (Frappe router sets no_cache for dynamic routes) — accepted.
- Page query budgets (NFR-18): `/`, `/c/<route>`, `/p/<route>`, `/search` ≤ 12 queries cold, ≤ 6 warm.
- DOM hooks (stable selectors for tests/JS): `[data-qs-theme-toggle]`, `[data-qs-card]`, `[data-qs-add]` (card + product page), `[data-qs-chip]`, `input[name="q"]`, `[data-qs-quote-count]`, `[data-qs-logo]`, `[data-qs-qty]` (qty stepper value).

### 7.2 Phases 3–7 (all whitelisted, module paths fixed; guest = allow_guest + rate limits per §5.2)
Mobile numbers: E.164 (`+` and 8–15 digits); a bare 10-digit number is prefixed "+91". OTP and order logic per SPEC §3/§4.

**Phase 3 – quote + enquiry** (`quoteshop/quoteshop_enquiry/api.py`, guest):
- `get_quote_items(item_codes: list[str] | str) -> list[card]` — published items only (card per §7.1); max 500 codes.
- `parse_quote_paste(text: str) -> {"matched": [{item_code, item_name, qty}], "unmatched": [{line: str, reason: str}]}` — one line per item, "<code or exact name><tab|,|;|space><qty>"; CSV uploads are read in the browser and sent as text. Max 500 lines.
- `send_otp(mobile: str) -> {"sent": true, "expires_in": 600}` — rate limits: 5/hour per number, 20/hour per IP. Sends the `otp_template` WhatsApp message (enqueued). If no template/account is configured: raise a clear error, except in developer_mode where the code is written to the `quoteshop` logger (never returned to the client).
- `verify_otp(mobile: str, otp: str) -> {"verified": true, "otp_token": str}` — max 5 wrong attempts per code; `otp_token` proves the number for 30 min (Redis `qs:otp-ok:<sha256(token)>` → mobile).
- `submit_enquiry(data: dict | str) -> {"name": str}` — 10/hour per IP. data = `{items: [{item_code, qty}], buyer_name, mobile, otp_token?, email?, business_name?, pincode?, buyer_type?, answers?: [{question, value}], notes?}`. Re-validates items (published, qty ≥ max(1, qs_min_qty), duplicates merged, ≤ 500 lines), required settings fields/questions, otp_token when `otp_required`. Snapshots `listed_rate` (starting price or 0), finds/creates Contact by mobile, links an existing Customer of that Contact, status "Requested", assignment (§3.3), CRM Deal (phase 4) — one transaction; WhatsApp messages enqueued after commit.

**Phase 4 – CRM + WhatsApp** (`quoteshop/quoteshop_enquiry/crm.py`, `whatsapp.py`):
- `crm.create_deal(enquiry_doc) -> str`, `crm.sync_deal_status(enquiry_doc)` (QS status → CRM status of the same name; Accepted → the Won-type status; Lost sets lost_reason "Other" + lost_notes).
- CRM Deal Status records seeded idempotently: Requested blue, Price Sent orange, Changes Requested yellow, Expired gray (Won/Lost exist).
- `whatsapp.queue_message(enquiry: str, event: str, version: int | None = None)` → enqueued `whatsapp.send_message(...)` per §4.1 (no-op with an Error Log note when the event's template link is empty); `whatsapp.on_whatsapp_message(doc, method=None)` hook per §4.3.

**Phase 5 – pricing + versions** (`quoteshop/quoteshop_enquiry/versions.py`, desk calls, Sales User/Manager with doc permission):
- `apply_discount(name, percent: float, scope: "all"|"selected"|"category", rows: list[str] | None = None, item_group: str | None = None)` — offered_rate = listed_rate × (1 − percent/100).
- `set_availability(name, rows: list[str], availability: str, note: str | None = None, lead_time_days: int | None = None, offered_qty: float | None = None)`.
- `copy_from_last_order(name)` — offered rates from the buyer's last submitted Sales Order lines.
- `send_price(name) -> {"version": int, "url": str}` — create_version("Sales"), status "Price Sent", valid_till = today + quote_validity_days, enqueue PDF + price_sent WhatsApp.
- `mark_lost(name, reason: str)`.
- `create_version(doc, by: "Buyer"|"Sales") -> str` (raw token) — snapshot, diff flags (§6.2), new token (old invalid), validity reset, summary. Buyer link: `/q/<name>?t=<raw token>`.

**Phase 6 – buyer view, accept, order** (`quoteshop/quoteshop_enquiry/quote_view.py`, `orders.py`, guest with token):
- `get_quote_view(name, token) -> dict` — latest version data for `/q` (lines, totals, availability counts, history); old/expired token → `{"outdated": true, "url": <current link if still valid>}`.
- `request_changes(name, token, items: [{item_code, qty}]) -> {"url": str}` — buyer may change qty, remove, add published items; NEVER prices (any rate in input → rejected). Creates a Buyer version, status "Changes Requested", rotates token.
- `accept_quote(name, token) -> {"accepted": true}` — latest unexpired version only; enqueues `orders.create_order(enquiry, version)` (job_id `qs-order-<name>`).
- `download_quote(name, token, format: "pdf"|"xlsx")`.
- `orders.create_order(enquiry: str, version: int)` — idempotent; Deal Won, Customer found/created (§2.6), ONE Sales Order (§2.7), confirmation WhatsApp. `orders.expire_quotes()` daily scheduler job.

**Phase 7 – portal** (`quoteshop/quoteshop_enquiry/portal.py`):
- `portal_login(mobile, otp_token) -> {"redirect": "/account"}` — after verify_otp; find/create Website User `<digits>@buyers.invalid` (no password), link `Contact.user`, `login_as`.
- `get_account_data() -> {orders: [...], requests: [...], totals: {...}}` — logged-in buyer's own records only (via Contact → Customer).
- `reorder(sales_order: str) -> {"items": [{item_code, qty}]}` — own orders only; published items only.

**Front-end pages** (www): `/quote` (quote list + form + OTP + success), `/q/<name>?t=` (buyer view), `/account` (portal; login form when Guest). Same base template/bundle as §8. JS calls the APIs above with `fetch` (`/api/method/<path>`, CSRF token from the page for logged-in users).

**Desk (phase 5)**: QS Enquiry form buttons call the versions.py functions; workspace "QuoteShop", Kanban "Enquiry Pipeline", saved filters, number cards, charts, print format "QS Quote" per SPEC §5.
**Reports (phase 8)**: in quoteshop module QuoteShop Enquiry (decision §9.7): Listed vs Sold by Item, Discount by Salesperson, Discount by Buyer Type, Won vs Lost, Most-requested Not Available.

## 8. Website front end (phase 2)
- Base template `quoteshop/templates/qs_base.html` (never extends frappe `web.html`/`base.html`): own `<head>` (title, meta description, canonical, favicon from settings), inline critical theme script, `{{ include_style("qs.bundle.css") }}`, `{{ include_script("qs.bundle.js") }}` (defer). Pages set `base_template_path`.
- Theme: CSS tokens copied 1:1 from the design `<helmet><style>` blocks with the SAME custom-property names (`--bg --surface --panel --field --tile --tile-2 --tile-3 --tile-4 --line --border --text --muted --ink-bg --sel-bg --sel-fg --glass --dot --ph`). Light values for the tokens that are self-referencing (broken) in some design files come from Account/MobileOrders/QuoteDetail: `--panel #F7F7F4`, `--field #F4F4F1`, `--tile #F1F1EE`, `--line #ECECE8`, `--border #E2E2DE`, `--glass rgba(255,255,255,0.9)` (quote-detail pages use 0.94). Dark values from any design file (identical).
- `<html data-theme="light|dark">` is always set: inline head script picks `localStorage["qs-theme"]` if switching is allowed, else settings `default_theme` (Light/Dark), else (Auto) `prefers-color-scheme`; no flash. Toggle hidden when `allow_theme_switch` is off. Server fallback attribute = default_theme lowercased (Auto → "light").
- Brand: `:root{--accent:<brand_color>}` inline from settings; soft tints with `color-mix(in srgb, var(--accent) 12%, var(--surface))` and a solid fallback.
- Pages `{% extends "quoteshop/templates/qs_base.html" %}` (Frappe v16 applies base_template_path only via web.html) and call `quoteshop.quoteshop_website.context.setup(context, "<page>")` in get_context. Blocks: head, header, mobile_header, content, quote_bar, footer, tabbar.
- CSS partials are imported relative to the build root: `@import "../quoteshop/quoteshop/public/css/qs/<file>.css";` (Frappe's postcss copies the entry to a temp folder, so `./qs/…` fails).
- Bundles: `quoteshop/public/js/qs.bundle.js` (vanilla, no jQuery/frappe-web), `quoteshop/public/css/qs.bundle.css`; first load < 120 KB gzipped excl. images.
- Quote list (browser only until submit): `localStorage["qs-quote"] = {"v": 1, "items": [{"item_code": str, "qty": number}]}`; every change dispatches `window` event `qs:quote-changed` with `detail = {count, units}`; header pill + floating bar listen to it.
- Price text: "From ₹X per piece · lower for bulk" (suffix from settings `price_suffix`) or "Price on request"; money formatted server-side with the item currency.
- Responsive: one template per page matching the desktop design at 1280 and the mobile design at 390 (breakpoints taken from the designs).

## 9. Decisions (ALL APPROVED by user 2026-10-04 — bold option is the rule)
1. WhatsApp quick-reply payload `QS:<action>:<enquiry>:<version>` cannot round-trip through frappe_whatsapp. **Correlate via `reply_to_message_id` → QS message log + button label + sender number; update SPEC wording.** Alternatives: QS-built Meta payload; upstream PR.
2. "View full quote" dynamic URL button is broken in frappe_whatsapp. **Static URL button to the site + tokenised link in the body text** (works with stock code). Alternative: QS builds the Meta payload itself (bypasses part of frappe_whatsapp).
3. Storefront tab position. **Before the Connections tab** (Connections stays last, ERPNext convention).
4. Sales Order warehouse for stock items. **QS Store Settings `default_warehouse` (default = Stock Settings default "Stores - JBB") → `set_warehouse`.** Alternative: create catalog items as non-stock.
5. CRM deal statuses. **Add QS statuses** (Requested blue, Price Sent orange, Changes Requested yellow, Won green, Lost red, Expired gray) **via idempotent after_install; leave CRM's defaults**. Delete the 7 demo deals + demo users on quoteshop.localhost? (destructive → your call).
6. Free lines: **offered_rate must be > 0 when offered_qty > 0** (validation error otherwise).
7. Reports live in erp_custom (SPEC) but read QS Enquiry, and erp_custom must not depend on quoteshop. **Move the 5 QS reports into quoteshop (module QuoteShop Enquiry); keep erp_custom for generic ERPNext reports.**
8. E2E runner. **Cypress via `bench run-ui-tests`** (Frappe-native, TESTING §2.9) for journeys; **Playwright MCP** only for qa visual comparison screenshots.
9. Query-count limits (test-lead proposal): list_products ≤6 cold / ≤1 warm, get_product ≤8 / ≤1, submit_enquiry (100 lines) ≤85 SELECTs (measured fixed cost ~70 incl. CRM Deal + frappe_whatsapp hooks; the 100 child-row INSERTs are inherent and excluded; the proposed 40 counted them), /q (100 lines) ≤15, /account ≤15.
10. Desk seeding. **Standard exported JSON (workspace, cards, charts, desktop icon, sidebar) + patch for Kanban/List Filters**, instead of after_install for those.
11. Brand colour contrast failure: **warn, not block**.
12. CRM products table. PHASES §4 says mirror lines into it. **Don't mirror; set `deal_value` = total offered** (CRM computes product totals only in browser JS and needs CRM Product master records; ERPNext sync is off).
13. "Template placeholders" seed. **Leave the 7 template links empty + list templates to register in the README**; never insert WhatsApp Templates (each insert calls Meta).

## 10. Review fix pass (2026-10-04) — supersedes earlier wording where it differs
- **Status lock**: `status` and `valid_till` are read-only. Changing status on an existing QS Enquiry requires `doc.flags.qs_status_change = True`; only these writers set it: versions.send_price / mark_lost, quote_view.request_changes, orders.accept, orders.expire_quotes, whatsapp.handle_reply. Kanban drags and set_value are refused.
- **§2.7 Alternative lines**: a line with availability Alternative and `alternative_item` orders that item (its item_name, uom = its stock_uom); qty = offered_qty, rate = offered_rate, price_list_rate = listed_rate.
- **Phase 3 limits**: paste text ≤ 50 KB, lines ≤ 200 chars, split at the last separator `[\t,; ]+`; qty > 0, finite, ≤ 100000 (also in build_lines; ≤ 500 items checked before iterating). verify_otp: + per-number limit 10/hour; failures counted atomically in `qs:otp-fail:<mobile>` (600 s) before comparing; 5th failure burns the code. developer_mode OTP logged at WARNING to `quoteshop` logger.
- **Phase 5**: `versions.resend_price(name) -> {"version", "url"}` — same version, no token rotation, link `/account?next=/q/<name>`, stored PDF. `queue_message/send_message(..., resend: bool = False)`, job_id suffix `-resend`.
- **Phase 6**: outdated → `{"outdated": true, "url": "<abs>/account?next=/q/<name>", "current_version", "status"}`; version_outdated params (buyer_name, ref, version, current_version, url). `create_order` always runs as Administrator, never raises (savepoint rollback, Error Log "QuoteShop: Sales Order not created", Comment on the enquiry). `orders.retry_order(name) -> {"queued": true}` (Sales Manager/System Manager; Accepted + no sales_order). download_quote serves the stored PDF when present.
- **Phase 7**: portal_login refuses Contacts whose user is not a QuoteShop `@buyers.invalid` user. `/account?next=` accepts only `/account`, `/quote`, `/q/<name>[?t=…]`.
- **Website**: all template output escaped (`|e`); search results with `q` / empty pages not cached; catalog GET APIs rate-limited; UI strings translatable (JS strings via `#qs-i18n` JSON).
- **Print format**: listed column, listed total and savings shown only when `show_savings_to_buyer` is on.

## 11. Colour options on one item (option A, approved by user 2026-10-05)
- **Admin**: Item → Storefront tab → new section "Colours" (after Photos, before Specifications; depends on qs_published): `qs_colours` Table → **QS Item Colour** (module QuoteShop Catalog): `label` Data reqd (in_list_view), `swatch` Color reqd (in_list_view, `#RRGGBB`). Max 12 colours; labels unique per item (case-insensitive); validated in Item `validate`.
- **Photo tag**: QS Item Photo gets `colour` (Select, optional, grid column after alt_text). Options = the item's colour labels, filled by `public/js/item.js` on refresh/row add; server validates `photo.colour` ∈ item colour labels or empty (and must be empty when the item has no colours). Photo without a colour = general photo, always shown.
- **Catalog**: `get_product(route)` adds `colours: [{label, swatch}]` and each photo `colour: str` ("" = general). Cards (`list_products`) add `has_colours: bool`. Cache keys unchanged (cleared on Item save).
- **Product page**: swatch circles (design `Item.dc.html`/`MobileItem.dc.html` "Cloth" row: `<label> · <selected name>`), first colour pre-selected, radio-group semantics (arrow keys, names as aria-labels). Selecting a colour: gallery shows that colour's photos first then general photos; "Add to quote" sends the chosen colour. Cards on lists/search for items with `has_colours`: the "+" button links to the product page instead of adding directly.
- **Line identity = (item_code, colour)** everywhere (colour "" when the item has no colours or none chosen): two colours of one item = two lines. localStorage `qs-quote` items `{item_code, qty, colour?}` (v stays 1; colour omitted when empty); `quote_store.setQty(item_code, qty, colour = "")`, `remove(item_code, colour = "")`.
- **API**: items in `get_quote_items`, `submit_enquiry`, `request_changes`, `reorder` accept `{item_code, qty, colour?}` (`get_quote_items` also still accepts plain code strings); colour, when given, must be one of the item's colour labels else ValidationError; empty colour allowed (not chosen, e.g. pasted lists — shown "Colour not chosen" to sales). Merge/dedupe key = (item_code, colour). `parse_quote_paste` unchanged (no colour).
- **QS Enquiry Item**: new field `colour` Data (read-only, placed after `uom` in the "Item" section of the row form; not in grid); duplicate check and `diff_lines` key = `item_code` + `\x1f` + `colour`; a colour change = Removed + Added. Snapshot rows carry `colour`.
- **Sales Order**: Sales Order Item custom field `qs_colour` Data read-only (chained after `qs_requested_qty`, hidden when empty); order creation also appends `<br>Colour: <label>` to the line `description`. One SO line per (item, colour).
- **Display**: colour name (with swatch dot where there's room) on /quote lines, /q lines, /account order lines, print format "QS Quote", desk grid row form; cart/quote line text "Name · Colour".
- **Alternative lines** keep the colour only if the alternative item has a colour with that label, else colour "".
- **`catalog.get_colours(item_codes) -> {item_code: [{label, swatch}]}`** (guest GET/POST, rate-limited 600/h, ≤ 500 codes, published items only, one query): used by /quote for colour selects, swatch dots and stale-colour clearing. `get_quote_items` read path tolerates a stale/unknown colour (→ colour "" / swatch ""); submit_enquiry / request_changes / build_lines stay strict.
- Fresh-install rule: `before_install` creates the "Website Starting Price" Price List (Frappe initialises all Singles — QS Store Settings links to it — before `after_install`).
- **Listing cards with colours (2026-10-05)**: cards of items with colours also carry `colours: [{label, swatch, image: {thumb, medium, large, alt} | None}]` (≤ 12; `image` = first photo tagged with that colour, else None → keep the general image). Computed by ONE extra batched query for the whole page (list_products cold: 1 main + 1 colours/photos query = 2 on pages with colour items, still 1 otherwise; budget now **≤ 6 cold / ≤ 1 warm**). Cards pick the colour in place: the "+" adds the SELECTED colour (default first); stepper counts that colour's line; tile outline when any colour of the item is in the quote; name/photo link carries `?colour=<selected>`. 4 swatches desktop / 3 mobile, "+N" link to the product page for the rest. Related-item cards and `get_quote_items` cards carry only `has_colours`.

## 12. Header, categories and home rows (approved by user 2026-10-05; canvas HNGQyjFVXEDBfxqfLjxSeL v40)
- **One header on every page** (`templates/qs/header.html`, `public/js/qs/nav.js`): message strip (QS Store Settings `header_messages`, child doctype `QS Header Message`: message, link, active), desktop row (logo, All categories ▾, up to `header_max_links` category links, search, theme, account, Quote), phone row (☰ + search, logo, WhatsApp, quote count). Transparent over the home hero (`qs.overlay`), solid otherwise; hides on scroll down, returns on scroll up.
- **Item Group custom fields** (module QuoteShop Catalog): `qs_show_in_menu` Check, `qs_menu_order` Int (depends on show in menu). Header links and home rows = groups ticked, by menu order; none ticked → every top-level published group.
- **QS Store Settings** (tab Header): `header_messages`, `header_max_links` (default 5, 0–8), `show_all_categories` (default 1), `quote_bar_delay` ms (default 500, 0–5000; floating Get price bar hides while scrolling and returns after this idle time).
- **Category tree**: `catalog.category_tree()` / whitelisted GET `get_category_tree` — `[{name, route, count, show_in_menu, menu_order, kids: [{name, route, count}]}]`; top level = published groups with no published ancestor, kids = every published descendant (flat), counts include descendants, groups without products omitted. Cached under `qs:catalog:tree`.
- **Pages**: `/` = full-width hero + promo row + one row per menu group (desktop scroll row with arrows, phone 2×2 + View all when more than 4); `/search` and `/c/<route>` = category tree filter (sidebar; phone bottom sheet) + sub-category chips + grid. All Categories panel and phone menu load the tree from the API on first open and filter it in the browser.
- **Other**: colour tiles are rounded squares and sit above the product name; no "From" before prices; quote lines show unit price and line total, with an Estimated total (lines on request are named, not summed).

