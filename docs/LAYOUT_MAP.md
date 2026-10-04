# QuoteShop – LAYOUT MAP (phase 1)

Status: **APPROVED by the user (2026-10-04)**. After approval this file is the source of truth for the layout tests (TEST_MATRIX DSK-14..20, NFR-13): tab → section → column → fields, in this order.

Notation: `[c1]` `[c2]` `[c3]` = columns (Column Break between). `ro` read-only · `reqd` mandatory · `idx` search_index · `↓` depends_on · `(coll)` collapsible section. Types: Chk Check, Int, Flt Float, Cur Currency, Pct Percent, Dt Date, DtT Datetime, Sel Select, Lnk Link, Tbl Table, TMS Table MultiSelect, Att Attach Image.

---

## A. Custom fields on standard DocTypes (app quoteshop, prefix `qs_`)

### A1. Item → tab **Storefront** (`qs_storefront_tab`, insert_after `prices_html`, before Connections)
| Section | Columns / fields |
|---|---|
| Publishing (`qs_publishing_section`) | [c1] `qs_published` Chk idx · `qs_display_order` Int idx — [c2] `qs_route` Data unique, ro once set · `qs_lead_time` Int "Lead time (days)" — [c3] `qs_min_qty` Int default 1 · `qs_hide_price` Chk |
| Starting price ↓published | `qs_starting_price_html` HTML (shows the Website Starting Price row or "Price on request") |
| Content ↓published | `qs_short_description` Small Text (full width) |
| Photos ↓published | `qs_photos` Tbl **QS Item Photo** (grid: image, alt_text) |
| Specifications (coll) | `qs_specs` Tbl **QS Item Spec** (grid: label, value) |
| Related items (coll) | `qs_related` TMS **QS Related Item** (item → Item) |
↓published = `eval:doc.qs_published`

Child tables (module QuoteShop Catalog):
- QS Item Photo: `image` Att reqd · `alt_text` Data · `thumb` `medium` `large` Data ro (generated WebP 400/1000/1800, phase 2)
- QS Item Spec: `label` Data reqd · `value` Data reqd
- QS Related Item: `item` Lnk Item reqd

### A2. Item Group → tab **Storefront** (insert_after `rgt`; Frappe auto-adds a first "Details" tab for the existing fields)
| Section | Columns / fields |
|---|---|
| Publishing | [c1] `qs_published` Chk idx · `qs_display_order` Int idx — [c2] `qs_route` Data unique, ro once set · `qs_image` Att |

### A3. Sales Order → tab **Storefront** (insert_after `party_account_currency`, before Connections)
| Section | Columns / fields |
|---|---|
| Source (all ro) | [c1] `qs_enquiry` Lnk QS Enquiry idx — [c2] `qs_version` Int |
| Price summary | `qs_price_summary_html` HTML ro |

### A4. Sales Order Item
`qs_requested_qty` Flt ro, insert_after `qty`, row form only (not in grid list view).

### A5. CRM Deal
- Desk form: tab **Storefront** at the end (data-model reads the real last field from crm_deal.json), one section, all ro: [c1] `qs_enquiry` Lnk QS Enquiry idx · `qs_open_quote` HTML — [c2] `qs_buyer_type` Data — [c3] `qs_version` Int.
- CRM Vue side panel (`CRM Deal-Side Panel`): section "Enquiry" = `qs_enquiry`, `qs_buyer_type`, `qs_version`, `qs_open_quote` (seeded in phase 4).

### A6. Contact
Property Setter: `mobile_no` search_index = 1 (fast lookup by mobile).

erp_custom ("Business" tab): no fields this phase.

---

## B. QuoteShop DocTypes

### B1. QS Store Settings (Single, module QuoteShop Settings) – tabs Brand · Contact · Pricing · Theme · Defaults
| Tab | Section | Columns / fields |
|---|---|---|
| Brand | Identity | [c1] `business_name` Data reqd · `short_name` Data — [c2] `logo` Att · `favicon` Att |
| Brand | Website text | [c1] `search_placeholder` Data · `quote_button_label` Data default "Quote" — [c2] `response_time_text` Data |
| Contact | Contact | [c1] `whatsapp_number` Data (Phone) · `email` Data (Email) — [c2] `address` Small Text |
| Contact | Social links | `social_links` Tbl **QS Social Link** (label, url) |
| Pricing | Prices | [c1] `show_starting_prices` Chk default 1 · `show_savings_to_buyer` Chk default 1 — [c2] `starting_price_list` Lnk Price List reqd default "Website Starting Price" · `price_suffix` Data default "per piece" — [c3] `products_per_page` Int default 24 |
| Theme | Theme | [c1] `brand_color` Color reqd — [c2] `default_theme` Sel Auto/Light/Dark default Auto · `allow_theme_switch` Chk default 1 |
| Defaults | Orders | [c1] `default_company` Lnk Company reqd · `default_customer_group` Lnk Customer Group reqd · `default_territory` Lnk Territory reqd — [c2] `default_warehouse` Lnk Warehouse · `auto_submit_sales_order` Chk default 0 |
Brand colour: on save, warn (not block) if contrast < AA against light or dark surface.

### B2. QS Homepage Settings (Single) – tabs Hero · Sections · Mobile
| Tab | Section | Columns / fields |
|---|---|---|
| Hero | Hero | [c1] `hero_badge` Data · `hero_title` Data reqd · `hero_subtitle` Small Text — [c2] `hero_image` Att |
| Hero | Buttons | [c1] `hero_primary_label` Data · `hero_primary_link` Data — [c2] `hero_secondary_label` Data · `hero_secondary_link` Data |
| Sections | Section order | `section_order` Tbl **QS Homepage Section** (section Sel Hero/Promo tiles/Trust line/How it works/Categories/Products, enabled Chk) |
| Sections | Promo tiles | `promo_tiles` Tbl **QS Promo Tile** (kicker, title, link, style Sel Dark/Soft/Plain, show_on_desktop Chk, show_on_mobile Chk; grid: title, style, show_on_desktop, show_on_mobile) |
| Sections | Trust line | `trust_points` Tbl **QS Trust Point** (text) |
| Sections | How it works | `show_how_it_works` Chk default 1 · `how_it_works` Tbl **QS How It Works Step** (title, text) ↓show_how_it_works |
| Mobile | Trade strip | [c1] `show_mobile_strip` Chk — [c2] `mobile_strip_text` Data · `mobile_strip_link` Data (↓show_mobile_strip) |

### B3. QS Enquiry Settings (Single) – tabs Form · Buyer types · Questions · Quote rules · WhatsApp templates
| Tab | Section | Columns / fields |
|---|---|---|
| Form | Login | [c1] `login_mode` Sel Not required/Optional/Required default Not required — [c2] `otp_required` Chk default 1 |
| Form | Fields | [c1] `show_pincode` Chk · `require_pincode` Chk ↓show_pincode — [c2] `show_business_name` Chk default 1 · `show_notes` Chk default 1 |
| Buyer types | Buyer types | `buyer_types` Tbl **QS Buyer Type** (label reqd, customer_group Lnk, default_assignee Lnk User) |
| Questions | Questions | `questions` Tbl **QS Enquiry Question** (label reqd, fieldtype Sel Data/Check/Select/Date/Small Text, options Small Text ↓Select, required Chk) |
| Quote rules | Validity & tiers | [c1] `quote_validity_days` Int default 15 — [c2] `bulk_tier_2` Int default 2 · `bulk_tier_3` Int default 5 |
| WhatsApp templates | Templates (all Lnk WhatsApp Templates, empty by default) | [c1] `otp_template` · `enquiry_received_buyer_template` · `enquiry_alert_sales_template` · `price_sent_template` — [c2] `accepted_template` · `changes_requested_template` · `version_outdated_template` |

### B4. QS Enquiry (module QuoteShop Enquiry; naming `RFQ-.#####`; not submittable; track changes) – tabs Quote · Buyer · Versions · System
| Tab | Section | Columns / fields |
|---|---|---|
| Quote | Summary | [c1] `status` Sel Draft/Requested/Price Sent/Changes Requested/Accepted/Lost/Expired default Draft ro idx · `current_version` Int ro · `valid_till` Dt ro — [c2] `total_listed` Cur ro · `total_offered` Cur ro · `total_saved` Cur ro · `saved_pct` Pct ro — [c3] `line_count` Int ro · `unit_count` Flt ro · `available_count` Int ro · `partial_count` Int ro · `not_available_count` Int ro |
| Quote | Items | `items` Tbl **QS Enquiry Item** (grid: item_name, requested_qty, offered_qty, offered_rate, availability) |
| Quote | Notes (coll) | `notes` Small Text · `answers` Tbl **QS Enquiry Answer** (question, value) · `lost_reason` Small Text ↓status=Lost |
| Buyer | Contact | [c1] `buyer_name` Data reqd · `mobile` Data reqd idx (E.164) · `email` Data — [c2] `business_name` Data · `buyer_type` Data · `pincode` Data |
| Buyer | Linked records (ro) | [c1] `customer` Lnk Customer · `contact` Lnk Contact — [c2] `crm_deal` Lnk CRM Deal · `sales_order` Lnk Sales Order · `assigned_to` Lnk User idx |
| Versions | Versions | `versions` Tbl **QS Enquiry Version** ro (grid: version, created_by_type, created_on, summary, accepted_on) |
| System | WhatsApp log (coll) | `messages` Tbl **QS Enquiry Message** ro (grid: version, event, direction, sent_on) |
Whole doc read-only once status = Accepted.

Child tables:
- **QS Enquiry Item** – row form: Item section [c1] `item_code` Lnk Item reqd · `item_name` Data ro (fetch) · `uom` Lnk UOM — [c2] `requested_qty` Flt reqd · `offered_qty` Flt · `change_flag` Sel ("", Qty changed, Price changed, Removed, Added, Alternative) ro; Price section [c1] `listed_rate` Cur ro · `offered_rate` Cur — [c2] `amount` Cur ro; Availability section [c1] `availability` Sel Available/Partial/Made to Order/Not Available/Alternative default Available · `lead_time_days` Int — [c2] `availability_note` Data · `alternative_item` Lnk Item ↓availability=Alternative.
- **QS Enquiry Version** (all ro): `version` Int · `created_by_type` Sel Buyer/Sales · `created_by` Data · `created_on` DtT · `summary` Small Text · `snapshot` JSON · `token_hash` Data idx · `token_expires` DtT · `accepted_on` DtT · `accepted_via` Sel Website/WhatsApp/Sales on behalf.
- **QS Enquiry Answer**: `question` Data · `value` Small Text.
- **QS Enquiry Message** (all ro): `version` Int · `event` Sel (enquiry_received_buyer, enquiry_alert_sales, price_sent, accepted, changes_requested, version_outdated, otp) · `direction` Sel Outgoing/Incoming · `message_id` Data idx · `whatsapp_message` Lnk WhatsApp Message · `sent_on` DtT.

### B5. Settings child tables (module QuoteShop Settings)
QS Social Link (label, url) · QS Homepage Section · QS Promo Tile · QS Trust Point (text) · QS How It Works Step (title, text) · QS Buyer Type · QS Enquiry Question — fields as listed in B1–B3.

---

## C. Roles and permissions
| DocType | System Manager | Sales Manager | Sales User | Catalog Manager (new role) |
|---|---|---|---|---|
| QS Store Settings, QS Homepage Settings | read/write | read | read | read/write |
| QS Enquiry Settings | read/write | read/write | read | – |
| QS Enquiry | all | read/write/create/report/export | read/write/create, **own or assigned only** | – |
| Item, Item Group, Item Price | (std) | (std) | (std) | read/write/create (+ delete Item Price) via Custom DocPerm |
"Own or assigned" = `assigned_to = user` OR `owner = user` OR `_assign` contains user (permission_query_conditions + has_permission). No delete on QS Enquiry except System Manager.

## D. Desk list / indicators (phase 1 scope)
- QS Enquiry list columns: buyer_name, business_name, buyer_type, total_offered, assigned_to, valid_till (+ modified); standard filters: status, buyer_type, assigned_to.
- Status colours: Draft gray · Requested blue · Price Sent orange · Changes Requested yellow · Accepted green · Lost red · Expired darkgrey. Availability pills: Available green · Partial orange · Made to Order blue · Not Available red · Alternative purple. Version by: Buyer cyan · Sales blue.
- Saved filters, Kanban, workspace, number cards, charts, primary buttons: phase 5.

---
## Delta 2026-10-05 – colour options (approved: "implement A")
- **Item → Storefront tab**: new section **Colours** (`qs_colours_section`, after Photos, before Specifications; depends_on `eval:doc.qs_published`): `qs_colours` Tbl **QS Item Colour** (grid: label, swatch). Specifications section re-chained after it.
- **QS Item Colour** (QuoteShop Catalog, child): `label` Data reqd · `swatch` Color reqd.
- **QS Item Photo**: `colour` Select (optional) after `alt_text`; grid image, alt_text, colour.
- **QS Enquiry Item**: `colour` Data ro after `uom` (Item section, column 1).
- **Sales Order Item**: `qs_colour` Data ro after `qs_requested_qty`, depends_on `eval:doc.qs_colour`.
