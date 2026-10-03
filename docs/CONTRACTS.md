# QuoteShop – CONTRACTS

Owner: orchestrator only. Sub-agents read, never edit. Source of truth for every name an agent may use.
Verified against: frappe 16.36.1 · erpnext 16.37.0 · hrms 16.20.1 · crm 1.86.0 (main) · frappe_whatsapp 1.0.12 (master) · payments version-16 (test site only).
Paths: `frappe/…` = apps/frappe/frappe, `erpnext/…` = apps/erpnext/erpnext, `crm/…` = apps/crm/crm, `fw/…` = apps/frappe_whatsapp/frappe_whatsapp.

Status tags: **FIXED** = verified fact or agreed rule · **PROPOSED** = default pending approval (see §9) · **TBD** = filled in by a later phase.

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
frappe.get_doc({
  "doctype": "WhatsApp Message", "type": "Outgoing", "to": mobile_e164,
  "content_type": "document" | "text", "use_template": 1, "template": template_name,
  "body_param": json.dumps(ordered_params),   # dict; values() used in order
  "attach": public_pdf_url,                     # header DOCUMENT; filename forced to document.pdf
  "reference_doctype": "CRM Deal", "reference_name": deal,
}).insert(ignore_permissions=True)
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

## 6. QuoteShop fieldnames (from SPEC §4; extended by phase)
TBD phase 1: QS Store Settings, QS Homepage Settings, QS Enquiry Settings, QS Enquiry (+ QS Enquiry Item, QS Enquiry Version, QS Enquiry Answer), Item/Item Group/Sales Order/Sales Order Item/CRM Deal custom fields — after LAYOUT MAP approval.

## 7. Whitelisted APIs (signatures fixed when the phase starts)
TBD phase 2–7: `list_products`, `get_product`, `send_otp`, `verify_otp`, `submit_enquiry`, `create_version`, `accept`, portal APIs.

## 8. CSS tokens / JS events
TBD phase 2 (ported 1:1 from `docs/design/*.dc.html` `<helmet><style>` tokens).

## 9. Decisions needed (orchestrator recommendation in bold)
1. WhatsApp quick-reply payload `QS:<action>:<enquiry>:<version>` cannot round-trip through frappe_whatsapp. **Correlate via `reply_to_message_id` → QS message log + button label + sender number; update SPEC wording.** Alternatives: QS-built Meta payload; upstream PR.
2. "View full quote" dynamic URL button is broken in frappe_whatsapp. **Static URL button to the site + tokenised link in the body text** (works with stock code). Alternative: QS builds the Meta payload itself (bypasses part of frappe_whatsapp).
3. Storefront tab position. **Before the Connections tab** (Connections stays last, ERPNext convention).
4. Sales Order warehouse for stock items. **QS Store Settings `default_warehouse` (default = Stock Settings default "Stores - JBB") → `set_warehouse`.** Alternative: create catalog items as non-stock.
5. CRM deal statuses. **Add QS statuses** (Requested blue, Price Sent orange, Changes Requested yellow, Won green, Lost red, Expired gray) **via idempotent after_install; leave CRM's defaults**. Delete the 7 demo deals + demo users on quoteshop.localhost? (destructive → your call).
6. Free lines: **offered_rate must be > 0 when offered_qty > 0** (validation error otherwise).
7. Reports live in erp_custom (SPEC) but read QS Enquiry, and erp_custom must not depend on quoteshop. **Move the 5 QS reports into quoteshop (module QuoteShop Enquiry); keep erp_custom for generic ERPNext reports.**
8. E2E runner. **Cypress via `bench run-ui-tests`** (Frappe-native, TESTING §2.9) for journeys; **Playwright MCP** only for qa visual comparison screenshots.
9. Query-count limits (test-lead proposal): list_products ≤5 cold / ≤1 warm, get_product ≤8 / ≤1, submit_enquiry (100 lines) ≤40, /q (100 lines) ≤15, /account ≤15.
10. Desk seeding. **Standard exported JSON (workspace, cards, charts, desktop icon, sidebar) + patch for Kanban/List Filters**, instead of after_install for those.
11. Brand colour contrast failure: **warn, not block**.
12. CRM products table. PHASES §4 says mirror lines into it. **Don't mirror; set `deal_value` = total offered** (CRM computes product totals only in browser JS and needs CRM Product master records; ERPNext sync is off).
13. "Template placeholders" seed. **Leave the 7 template links empty + list templates to register in the README**; never insert WhatsApp Templates (each insert calls Meta).
