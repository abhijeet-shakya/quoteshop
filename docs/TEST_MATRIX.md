# QuoteShop – Test matrix

Status = planned | red | green | n/a.

## Settings & theme

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| SET-01 | 1 | QS Store Settings cached read is invalidated on save | unit, integration | `quoteshop/quoteshop_settings/tests/test_settings_cache.py::TestSettingsCache::test_store_settings_cache_cleared_on_save` | planned |
| SET-02 | 1 | QS Homepage Settings cached read is invalidated on save | unit, integration | `quoteshop/quoteshop_settings/tests/test_settings_cache.py::TestSettingsCache::test_homepage_settings_cache_cleared_on_save` | planned |
| SET-03 | 1 | QS Enquiry Settings cached read is invalidated on save | unit, integration | `quoteshop/quoteshop_settings/tests/test_settings_cache.py::TestSettingsCache::test_enquiry_settings_cache_cleared_on_save` | planned |
| SET-04 | 1 | after_install leaves WhatsApp template links empty in QS Enquiry Settings and never inserts WhatsApp Templates (no Meta call); idempotent | integration | `quoteshop/quoteshop_settings/tests/test_install.py::TestAfterInstall::test_whatsapp_template_links_left_empty`, `::test_no_whatsapp_templates_inserted` | planned |
| SET-05 | 1 | after_install idempotent: run twice → no duplicates, no errors, admin edits preserved | integration | `quoteshop/quoteshop_settings/tests/test_install.py::TestAfterInstall::test_after_install_idempotent` | planned |
| SET-06 | 1 | Brand colour contrast check correct against light theme background (AA) | unit | `quoteshop/quoteshop_settings/doctype/qs_store_settings/test_qs_store_settings.py::TestQSStoreSettings::test_brand_color_contrast_light` | planned |
| SET-07 | 1 | Brand colour contrast check correct against dark theme background (AA) | unit | `quoteshop/quoteshop_settings/doctype/qs_store_settings/test_qs_store_settings.py::TestQSStoreSettings::test_brand_color_contrast_dark` | planned |
| SET-08 | 1 | Failing brand colour warns on save, does not block (CONTRACTS §9.11) | integration | `quoteshop/quoteshop_settings/doctype/qs_store_settings/test_qs_store_settings.py::TestQSStoreSettings::test_low_contrast_brand_color_warns_not_blocks` | planned |
| SET-09 | 2 | Store/homepage settings changes (name, hero text, sections, prices toggle) reflect on the website without code | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestSettingsReflection::test_settings_change_reflects_on_home` | planned |
| SET-10 | 2 | Page/catalog caches invalidate after any settings save | rendering | `quoteshop/quoteshop_website/tests/test_cache.py::TestWebsiteCache::test_settings_save_invalidates_cache` | planned |
| SET-11 | 2 | Brand colour rendered as CSS variable for both themes | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestTheme::test_brand_color_variable_rendered` | planned |
| SET-12 | 2 | Server renders the data-theme attribute from default_theme (Auto / Light / Dark) | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestTheme::test_data_theme_attribute_from_settings` | planned |
| SET-13 | 2 | Theme toggle choice persists per browser | e2e | `cypress/integration/qs_theme.js::"toggle persists after reload"` | planned |
| SET-14 | 2 | Theme toggle hidden when allow_theme_switch is off | rendering, e2e | `quoteshop/quoteshop_website/tests/test_pages.py::TestTheme::test_toggle_hidden_when_switch_disabled`; `cypress/integration/qs_theme.js::"toggle hidden when disabled"` | planned |
| SET-15 | 2 | Auto theme follows the OS (emulated prefers-color-scheme light and dark) | e2e | `cypress/integration/qs_theme.js::"auto theme follows emulated prefers-color-scheme"` | planned |

## Catalog

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| CAT-01 | 2 | Only published items appear in listing | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_list_products_only_published` | planned |
| CAT-02 | 2 | Only published item groups appear (chips, /c); unpublished group → 404 | integration, rendering | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_only_published_groups`; `quoteshop/quoteshop_website/tests/test_pages.py::TestCategoryPage::test_unpublished_group_404` | planned |
| CAT-03 | 2 | Unpublish removes item from listing | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_unpublish_removes_from_listing` | planned |
| CAT-04 | 2 | Unpublish removes item from search | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_unpublish_removes_from_search` | planned |
| CAT-05 | 2 | Unpublished product page → 404 | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestProductPage::test_unpublished_product_404` | planned |
| CAT-06 | 2 | Unpublish invalidates catalog cache | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_cache.py::TestCatalogCache::test_item_unpublish_invalidates_cache` | planned |
| CAT-07 | 2 | Item Price change invalidates catalog cache | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_cache.py::TestCatalogCache::test_item_price_change_invalidates_cache` | planned |
| CAT-08 | 2 | Item Group change invalidates catalog cache | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_cache.py::TestCatalogCache::test_item_group_change_invalidates_cache` | planned |
| CAT-09 | 2 | Starting price comes from the configured starting_price_list only | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_starting_price_from_configured_list` | planned |
| CAT-10 | 2 | "Price on request" when show_starting_prices is off (listing + product page) | integration, rendering | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_price_on_request_when_hidden_globally`; `quoteshop/quoteshop_website/tests/test_pages.py::TestProductPage::test_price_on_request_global` | planned |
| CAT-11 | 2 | "Price on request" when item qs_hide_price is set | integration, rendering | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_price_on_request_when_hidden_per_item`; `quoteshop/quoteshop_website/tests/test_pages.py::TestProductPage::test_price_on_request_per_item` | planned |
| CAT-12 | 2 | Photo generates exactly 3 WebP sizes (400/1000/1800) | jobs | `quoteshop/quoteshop_catalog/tests/test_image_pipeline.py::TestImagePipeline::test_generates_three_webp_sizes` | planned |
| CAT-13 | 2 | Image job enqueued once per photo (job_id dedupe, after commit) | jobs | `quoteshop/quoteshop_catalog/tests/test_image_pipeline.py::TestImagePipeline::test_enqueued_once_per_photo` | planned |
| CAT-14 | 2 | Unchanged photos are not reprocessed on re-save | jobs | `quoteshop/quoteshop_catalog/tests/test_image_pipeline.py::TestImagePipeline::test_unchanged_photo_not_reprocessed` | planned |
| CAT-15 | 2 | Pagination correct (products_per_page, middle and last page) | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_pagination` | planned |
| CAT-16 | 2 | Category filter correct | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_category_filter` | planned |
| CAT-17 | 2 | Search correct | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_search` | planned |
| CAT-18 | 2 | Ordering stable across pages (qs_display_order + deterministic tiebreak) | integration | `quoteshop/quoteshop_catalog/tests/test_catalog_service.py::TestCatalogService::test_stable_ordering_across_pages` | planned |
| CAT-19 | 2 | qs_route slug generated, unique, read-only once set | unit | `quoteshop/quoteshop_catalog/tests/test_item_route.py::TestItemRoute::test_route_slug_unique` | planned |
| CAT-20 | 2 | Every catalog page as guest (/, /c, /search, /p): status, key content, theme attribute, no foreign data | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestCatalogPages::test_home_renders`, `::test_category_renders`, `::test_search_renders`, `::test_product_renders` | planned |
| CAT-21 | 2 | Guest catalog pages send cacheable headers | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestCacheHeaders::test_guest_catalog_cache_headers` | planned |

## Quote & enquiry

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| QTE-01 | 3 | Min qty 1: qty ≤ 0 rejected server-side | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_qty_below_one_rejected` | planned |
| QTE-02 | 3 | Typed qty is kept exactly | API, e2e | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_typed_qty_kept`; `cypress/integration/qs_quote_list.js::"typed qty updates list"` | planned |
| QTE-03 | 3 | Invalid input rejected (non-numeric qty, unknown item, unpublished item) | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_invalid_qty_rejected`, `::test_unknown_item_rejected`, `::test_unpublished_item_rejected` | planned |
| QTE-04 | 3 | Paste/upload matches item codes + qty | unit | `quoteshop/quoteshop_enquiry/tests/test_paste_import.py::TestPasteImport::test_matches_codes_and_qty`, `::test_upload_file_parsed` | planned |
| QTE-05 | 3 | Paste/upload reports unmatched rows | unit | `quoteshop/quoteshop_enquiry/tests/test_paste_import.py::TestPasteImport::test_reports_unmatched_rows` | planned |
| QTE-06 | 3 | OTP is 6 digits and stored hashed only | unit | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_otp_six_digits_stored_hashed` | planned |
| QTE-07 | 3 | OTP single use | unit, API | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_otp_single_use` | planned |
| QTE-08 | 3 | OTP wrong-code attempt limit | API | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_wrong_code_attempt_limit` | planned |
| QTE-09 | 3 | OTP expires after 10 min (frozen time) | unit | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_otp_expires_after_ten_minutes` | planned |
| QTE-10 | 3 | OTP send rate limit per number | API | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_send_rate_limit_per_number` | planned |
| QTE-11 | 3 | OTP send rate limit per IP | API | `quoteshop/quoteshop_enquiry/tests/test_otp.py::TestOTP::test_send_rate_limit_per_ip` | planned |
| QTE-12 | 3 | submit_enquiry requires verified OTP when otp_required | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_requires_verified_otp` | planned |
| QTE-13 | 3 | submit_enquiry re-validates items server-side | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_revalidates_items` | planned |
| QTE-14 | 3 | submit_enquiry snapshots listed_rate from the starting price list; client-sent prices ignored | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_snapshots_listed_rate`, `::test_client_price_ignored` | planned |
| QTE-15 | 3 | submit_enquiry creates a Contact for a new mobile | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_creates_contact` | planned |
| QTE-16 | 3 | submit_enquiry links an existing Contact | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_links_existing_contact` | planned |
| QTE-17 | 3 | submit_enquiry links an existing Customer by mobile | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_links_existing_customer_by_mobile` | planned |
| QTE-18 | 3 | submit_enquiry is atomic (failure → no Enquiry/Contact left) | integration | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_atomic_rollback_on_failure` | planned |
| QTE-19 | 3 | submit_enquiry guest rate limit | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_rate_limited` | planned |
| QTE-20 | 3 | Configured question answers stored | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_answers_stored` | planned |
| QTE-21 | 3 | Buyer type stored; unknown buyer type rejected | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_buyer_type_stored`, `::test_unknown_buyer_type_rejected` | planned |
| QTE-22 | 3 | Required questions enforced | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_required_question_enforced` | planned |
| QTE-23 | 3 | Required form fields per settings enforced (pincode, business name) | API | `quoteshop/quoteshop_enquiry/tests/test_api_enquiry.py::TestSubmitEnquiry::test_required_fields_per_settings` | planned |
| QTE-24 | 3 | /quote renders details form from settings (fields, questions, buyer types) | rendering | `quoteshop/quoteshop_website/tests/test_pages.py::TestQuotePage::test_form_fields_from_settings` | planned |
| QTE-25 | 1 | QS Enquiry naming series RFQ-.##### | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_naming_series` | planned |
| QTE-26 | 3 | OTP template sent once with correct variables (mocked) | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_otp_template_once_with_variables` | planned |

## CRM / assignment / WhatsApp

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| CRM-01 | 4 | Exactly one CRM Deal per enquiry with qs_enquiry set | integration | `quoteshop/quoteshop_enquiry/tests/test_crm_deal.py::TestDealCreation::test_one_deal_per_enquiry` | planned |
| CRM-02 | 4 | Deal creation idempotent (re-run job → still one Deal) | jobs | `quoteshop/quoteshop_enquiry/tests/test_crm_deal.py::TestDealCreation::test_deal_creation_idempotent` | planned |
| CRM-03 | 4 | Deal created with deal_value = total_offered; CRM products table NOT filled (CONTRACTS §9.12) | integration | `quoteshop/quoteshop_enquiry/tests/test_crm_deal.py::TestDealCreation::test_deal_value_equals_total_offered`, `::test_products_table_not_filled` | planned |
| CRM-04 | 4 | Assignment: buyer-type default_assignee wins | integration | `quoteshop/quoteshop_enquiry/tests/test_assignment.py::TestAssignment::test_buyer_type_assignee_wins` | planned |
| CRM-05 | 4 | Assignment fallback: Customer.account_manager (repeat buyer) | integration | `quoteshop/quoteshop_enquiry/tests/test_assignment.py::TestAssignment::test_account_manager_fallback` | planned |
| CRM-06 | 4 | Assignment fallback: Assignment Rule on CRM Deal | integration | `quoteshop/quoteshop_enquiry/tests/test_assignment.py::TestAssignment::test_assignment_rule_fallback` | planned |
| CRM-07 | 4 | Enquiry assigned_to matches the Deal assignee | integration | `quoteshop/quoteshop_enquiry/tests/test_assignment.py::TestAssignment::test_enquiry_assigned_to_synced` | planned |
| CRM-08 | 4 | enquiry_received_buyer sent once with correct variables (mocked) | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_enquiry_received_buyer_once` | planned |
| CRM-09 | 4 | enquiry_alert_sales sent once to the assignee with correct variables | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_enquiry_alert_sales_once` | planned |
| CRM-10 | 4 | Duplicate event/retry → no duplicate message | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_duplicate_event_single_message` | planned |
| CRM-11 | 4 | Incoming quick reply matched via reply_to_message_id → QS message log (QS Enquiry Message); button label → action; sender number must equal enquiry mobile; unknown/malformed ignored without raising | integration, jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp_incoming.py::TestIncomingQuickReply::test_matched_via_reply_to_message_id`, `::test_button_label_maps_to_action`, `::test_sender_must_match_enquiry_mobile`, `::test_unknown_reply_to_ignored_without_raising`, `::test_malformed_message_ignored_without_raising` | planned |
| CRM-12 | 5 | price_sent sent once: body variables incl. tokenised link, PDF header, static URL button + quick replies "Accept quote" / "Request changes"; message_id logged | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_price_sent_once_with_variables` | planned |
| CRM-13 | 6 | accepted message sent once with correct variables | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_accepted_message_once` | planned |
| CRM-14 | 6 | changes_requested message sent once with correct variables | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_changes_requested_message_once` | planned |

## Pricing & versions

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| PRC-01 | 1 | Totals (listed/offered/saved/saved_pct) exact to currency precision, 1 line | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_totals_one_line` | planned |
| PRC-02 | 1 | Totals exact to currency precision, 100 lines | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_totals_hundred_lines` | planned |
| PRC-03 | 1 | Counts: line_count, unit_count, available/partial/not_available | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_counts` | planned |
| PRC-04 | 1 | saved_pct = 0 when total_listed = 0 (no division error) | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_saved_pct_zero_listed` | planned |
| PRC-05 | 1 | Partial updates totals and partial count | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_partial_updates_totals_and_counts` | planned |
| PRC-06 | 1 | Not Available excluded from offered total, counted | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_not_available_excluded` | planned |
| PRC-07 | 1 | Alternative updates totals and counts | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_alternative_updates_totals` | planned |
| PRC-08 | 1 | Diff sets change flags: Qty changed / Price changed / Removed / Added / Alternative / "" | unit | `quoteshop/quoteshop_enquiry/tests/test_version_diff.py::TestVersionDiff::test_qty_changed`, `::test_price_changed`, `::test_removed`, `::test_added`, `::test_alternative`, `::test_unchanged_empty_flag` | planned |
| PRC-09 | 1 | Tokens random; only SHA-256 stored; verify valid / reject wrong / reject expired | unit | `quoteshop/quoteshop_enquiry/tests/test_tokens.py::TestQuoteToken::test_token_random_hash_only_stored`, `::test_verify_valid_token`, `::test_wrong_token_rejected`, `::test_expired_token_rejected` | planned |
| PRC-10 | 5 | Bulk discount on all lines | unit, integration | `quoteshop/quoteshop_enquiry/tests/test_bulk_tools.py::TestBulkDiscount::test_discount_all_lines` | planned |
| PRC-11 | 5 | Bulk discount on selected lines | unit, integration | `quoteshop/quoteshop_enquiry/tests/test_bulk_tools.py::TestBulkDiscount::test_discount_selected_lines` | planned |
| PRC-12 | 5 | Bulk discount by category | unit, integration | `quoteshop/quoteshop_enquiry/tests/test_bulk_tools.py::TestBulkDiscount::test_discount_by_category` | planned |
| PRC-13 | 5 | create_version stores snapshot of current lines | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestCreateVersion::test_snapshot` | planned |
| PRC-14 | 5 | create_version sets diff flags vs previous version | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestCreateVersion::test_change_flags_set` | planned |
| PRC-15 | 5 | create_version rotates token (old token invalid, new valid) | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestCreateVersion::test_token_rotation_old_invalid` | planned |
| PRC-16 | 5 | create_version resets validity (today + quote_validity_days, frozen time) | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestCreateVersion::test_validity_reset` | planned |
| PRC-17 | 5 | create_version writes summary; version number + created_by_type set | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestCreateVersion::test_summary_and_version_meta` | planned |
| PRC-18 | 5 | PDF renders for 1 line and is attached | integration | `quoteshop/quoteshop_enquiry/tests/test_pdf.py::TestQuotePDF::test_pdf_one_line_attached` | planned |
| PRC-19 | 5 | PDF renders for 100 lines and is attached | integration | `quoteshop/quoteshop_enquiry/tests/test_pdf.py::TestQuotePDF::test_pdf_hundred_lines_attached` | planned |
| PRC-20 | 5 | Send price enqueued once after commit (job_id) | jobs | `quoteshop/quoteshop_enquiry/tests/test_send_price.py::TestSendPrice::test_enqueued_once` | planned |
| PRC-21 | 6 | Buyer can change qty, remove and add lines | API | `quoteshop/quoteshop_enquiry/tests/test_api_quote.py::TestBuyerChanges::test_change_qty`, `::test_remove_line`, `::test_add_line` | planned |
| PRC-22 | 6 | Buyer price change rejected by API | API | `quoteshop/quoteshop_enquiry/tests/test_api_quote.py::TestBuyerChanges::test_price_change_rejected` | planned |

## Accept & order

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| ACC-01 | 6 | Latest unexpired version accepts via website token | API | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_accept_latest_via_website` | planned |
| ACC-02 | 6 | Expired version rejected (frozen time) | API | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_expired_version_rejected` | planned |
| ACC-03 | 6 | Non-latest version rejected | API | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_old_version_rejected` | planned |
| ACC-04 | 6 | Wrong / old token rejected | API | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_wrong_token_rejected` | planned |
| ACC-05 | 6 | WhatsApp accept from the registered number accepted | integration | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_accept_via_whatsapp_registered_number` | planned |
| ACC-06 | 6 | WhatsApp accept from other numbers rejected | integration | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_whatsapp_other_number_rejected` | planned |
| ACC-07 | 6 | Old version via WhatsApp → version_outdated reply with the new link | integration, jobs | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_old_version_whatsapp_gets_version_outdated` | planned |
| ACC-08 | 6 | Old version link on website → "updated" message with the new link | rendering | `quoteshop/quoteshop_website/tests/test_q_page.py::TestQPage::test_old_version_shows_updated_link` | planned |
| ACC-09 | 6 | Double click accept → one Sales Order | integration | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_double_accept_one_sales_order` | planned |
| ACC-10 | 6 | Duplicate webhook → one Sales Order | jobs | `quoteshop/quoteshop_enquiry/tests/test_accept.py::TestAccept::test_duplicate_webhook_one_sales_order` | planned |
| ACC-11 | 6 | Sales Order selling_price_list = starting price list | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_price_list` | planned |
| ACC-12 | 6 | price_list_rate = listed, rate = offered (to precision) | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_rates` | planned |
| ACC-13 | 6 | Only offered_qty > 0 lines | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_only_offered_lines` | planned |
| ACC-14 | 6 | Per-line delivery_date from lead_time_days (frozen time) | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_delivery_dates` | planned |
| ACC-15 | 6 | qs fields set (qs_enquiry, qs_version, qs_requested_qty, qs_price_summary_html) | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_qs_fields` | planned |
| ACC-16 | 6 | Draft when auto_submit_sales_order off | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_draft_when_auto_submit_off` | planned |
| ACC-17 | 6 | Submitted when auto_submit_sales_order on | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_submitted_when_auto_submit_on` | planned |
| ACC-18 | 6 | Deal → Won | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_deal_won` | planned |
| ACC-19 | 6 | New Customer: group from buyer type, default territory, account_manager = assignee | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_customer_created` | planned |
| ACC-20 | 6 | Existing Customer reused (account_manager not overwritten) | integration | `quoteshop/quoteshop_enquiry/tests/test_order.py::TestSalesOrderCreation::test_customer_reused` | planned |
| ACC-21 | 6 | Enquiry read-only after accept | integration | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry.py::TestQSEnquiry::test_read_only_after_accept` | planned |
| ACC-22 | 6 | Expired job: Price Sent past valid_till → Expired; other statuses untouched | jobs | `quoteshop/quoteshop_enquiry/tests/test_expiry_job.py::TestExpiryJob::test_expires_past_validity`, `::test_leaves_valid_and_other_statuses` | planned |
| ACC-23 | 6 | Expired job idempotent | jobs | `quoteshop/quoteshop_enquiry/tests/test_expiry_job.py::TestExpiryJob::test_idempotent` | planned |
| ACC-24 | 6 | /q page renders for a valid token; invalid token denied | rendering | `quoteshop/quoteshop_website/tests/test_q_page.py::TestQPage::test_renders_with_valid_token`, `::test_invalid_token_denied` | planned |
| ACC-25 | 6 | version_outdated template sent once with correct variables + new link (mocked) | jobs | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_version_outdated_once_with_new_link` | planned |

## Portal

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| POR-01 | 7 | OTP passwordless login links Website User to Contact | API | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalLogin::test_otp_login_links_contact` | planned |
| POR-02 | 7 | No password stored for portal users | integration | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalLogin::test_no_password_stored` | planned |
| POR-03 | 7 | /account shows only own enquiries and orders | rendering | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalIsolation::test_only_own_data` | planned |
| POR-04 | 7 | Direct URLs to another buyer's records denied (/q, PDF, order) | API, rendering | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalIsolation::test_direct_url_other_buyer_denied` | planned |
| POR-05 | 7 | Listed / final / saved match the Sales Order | rendering | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalOrders::test_totals_match_sales_order` | planned |
| POR-06 | 7 | Savings hidden when show_savings_to_buyer is off | rendering | `quoteshop/quoteshop_website/tests/test_portal.py::TestPortalOrders::test_savings_hidden_when_setting_off` | planned |
| POR-07 | 7 | Reorder refills the quote list | API, e2e | `quoteshop/quoteshop_website/tests/test_portal.py::TestReorder::test_reorder_payload`; `cypress/integration/qs_portal.js::"reorder refills quote list"` | planned |

## Desk

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| DSK-01 | 1 | Enquiry status indicator mapping (list get_indicator + form) per SPEC §5, asserted server-side from meta / the list JS mapping file | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry_indicators.py::TestEnquiryIndicators::test_status_indicator_mapping` | planned |
| DSK-02 | 1 | Availability pill colour mapping in grid formatter | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry_indicators.py::TestEnquiryIndicators::test_availability_colour_mapping` | planned |
| DSK-03 | 1 | Version-by colour mapping (Buyer cyan, Sales blue) | unit | `quoteshop/quoteshop_enquiry/doctype/qs_enquiry/test_qs_enquiry_indicators.py::TestEnquiryIndicators::test_version_by_colour_mapping` | planned |
| DSK-04 | 4 | CRM Deal status colours aligned to the same meanings | integration | `quoteshop/quoteshop_enquiry/tests/test_crm_layout.py::TestCRMLayout::test_status_colours` | planned |
| DSK-05 | 4 | CRM "Enquiry" layout section present; setup idempotent | integration | `quoteshop/quoteshop_enquiry/tests/test_crm_layout.py::TestCRMLayout::test_enquiry_section_idempotent` | planned |
| DSK-06 | 5 | One correct primary button per status; Mark Lost secondary | e2e | `cypress/integration/qs_desk_enquiry.js::"primary button per status"` | planned |
| DSK-07 | 5 | Kanban "Enquiry Pipeline" on status with correct counts | integration, e2e | `quoteshop/quoteshop_enquiry/tests/test_workspace.py::TestWorkspace::test_kanban_on_status`; `cypress/integration/qs_desk_enquiry.js::"kanban counts"` | planned |
| DSK-08 | 5 | Workspace number cards count correctly on a known dataset | integration | `quoteshop/quoteshop_enquiry/tests/test_workspace.py::TestWorkspace::test_number_card_counts` | planned |
| DSK-09 | 5 | Saved filters (Needs pricing, Waiting for buyer, Expiring in 3 days) return correct records | integration | `quoteshop/quoteshop_enquiry/tests/test_workspace.py::TestWorkspace::test_saved_filters` | planned |
| DSK-10 | 1 | Sales User list shows own/assigned only (permission_query_conditions) | integration | `quoteshop/quoteshop_enquiry/tests/test_permissions.py::TestEnquiryPermissions::test_sales_user_list_own_assigned` | planned |
| DSK-11 | 1 | Sales User denied other users' enquiry (has_permission) | integration | `quoteshop/quoteshop_enquiry/tests/test_permissions.py::TestEnquiryPermissions::test_sales_user_doc_denied` | planned |
| DSK-12 | 1 | Sales Manager sees all | integration | `quoteshop/quoteshop_enquiry/tests/test_permissions.py::TestEnquiryPermissions::test_sales_manager_sees_all` | planned |
| DSK-13 | 1 | Catalog Manager role can edit Storefront fields, not enquiries | integration | `quoteshop/quoteshop_enquiry/tests/test_permissions.py::TestEnquiryPermissions::test_catalog_manager_role` | planned |
| DSK-14 | 1 | Layout: Item "Storefront" tab per approved map | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_item_storefront_layout` | planned |
| DSK-15 | 1 | Layout: Item Group "Storefront" tab | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_item_group_layout` | planned |
| DSK-16 | 1 | Layout: Sales Order "Storefront" tab; Sales Order Item qs_requested_qty after qty, not in list view | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_sales_order_layout`, `::test_sales_order_item_layout` | planned |
| DSK-17 | 1 | Layout: CRM Deal Desk "Storefront" tab (one 3-col read-only section) | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_crm_deal_layout` | planned |
| DSK-18 | 1 | Layout: QS Enquiry tabs/sections/columns and grid list columns | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_qs_enquiry_layout` | planned |
| DSK-19 | 1 | Layout: settings DocType tabs | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_settings_tabs` | planned |
| DSK-20 | 1 | QS Enquiry list view columns and standard filters | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout::test_enquiry_list_view` | planned |
| DSK-21 | 2 | Visual check of status / availability / version-by colours in Desk (follow-up to DSK-01–DSK-03) | e2e, visual | `cypress/integration/qs_desk_enquiry.js::"indicator colours render"` | planned |

## Reports

Reports move to quoteshop (module QuoteShop Enquiry) pending approval of CONTRACTS §9.7.

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| REP-01 | 8 | Listed vs Sold by Item totals reconcile with source records (known dataset) | integration | `quoteshop/quoteshop_enquiry/report/listed_vs_sold_by_item/test_listed_vs_sold_by_item.py::TestListedVsSoldByItem::test_totals_reconcile` | planned |
| REP-02 | 8 | Discount by Salesperson totals reconcile | integration | `quoteshop/quoteshop_enquiry/report/discount_by_salesperson/test_discount_by_salesperson.py::TestDiscountBySalesperson::test_totals_reconcile` | planned |
| REP-03 | 8 | Discount by Buyer Type totals reconcile | integration | `quoteshop/quoteshop_enquiry/report/discount_by_buyer_type/test_discount_by_buyer_type.py::TestDiscountByBuyerType::test_totals_reconcile` | planned |
| REP-04 | 8 | Won vs Lost with reasons totals reconcile | integration | `quoteshop/quoteshop_enquiry/report/won_vs_lost/test_won_vs_lost.py::TestWonVsLost::test_totals_reconcile` | planned |
| REP-05 | 8 | Most-requested Not Available counts reconcile | integration | `quoteshop/quoteshop_enquiry/report/most_requested_not_available/test_most_requested_not_available.py::TestMostRequestedNotAvailable::test_counts_reconcile` | planned |

## E2E journeys

Each journey runs at desktop 1280 + mobile 390, light + dark.

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| E2E-01 | 3 | Guest browse → filter → search → product → add 3 → quote → OTP → send → success reference | e2e | `cypress/integration/qs_journey_01_guest_quote.js` | planned |
| E2E-02 | 5 | Salesperson Needs pricing → price, 1 partial, 1 not available, 8% bulk → Send price → mocked WhatsApp summary/buttons correct | e2e | `cypress/integration/qs_journey_02_sales_pricing.js` | planned |
| E2E-03 | 6 | Buyer link → Changes filter → reduce qty, remove item → v3 → re-price v4 → accept on website → one correct Sales Order → confirmation | e2e | `cypress/integration/qs_journey_03_buyer_change_accept.js` | planned |
| E2E-04 | 6 | As E2E-03 with WhatsApp quick-reply accept, then duplicate reply → still one Sales Order | e2e | `cypress/integration/qs_journey_04_whatsapp_accept.js` | planned |
| E2E-05 | 6 | Old v2 link after v4 → "updated" message with the new link | e2e | `cypress/integration/qs_journey_05_old_link.js` | planned |
| E2E-06 | 7 | Repeat buyer → auto-assigned to account manager → portal shows both orders with correct savings | e2e | `cypress/integration/qs_journey_06_repeat_buyer.js` | planned |
| E2E-07 | 6 | 100-line paste → submit → bulk pricing → buyer view groups / Show all / filters → accept → correct Sales Order lines | e2e | `cypress/integration/qs_journey_07_hundred_lines.js` | planned |
| E2E-08 | 3 | Admin changes brand colour, hero text, hides prices, adds buyer type + question → website updates immediately | e2e | `cypress/integration/qs_journey_08_admin_settings.js` | planned |

## Non-functional

Query-count limits are fixed maximums asserted with `assertQueryCount` (proposed values; confirmed when the RED test is written).

| ID | Phase | Criterion | Layer(s) | Test(s) | Status |
|---|---|---|---|---|---|
| NFR-01 | 2 | list_products (24 items): ≤ 5 queries cold cache, ≤ 1 warm | query-count | `quoteshop/quoteshop_catalog/tests/test_query_counts.py::TestCatalogQueryCounts::test_list_products_24` | planned |
| NFR-02 | 2 | get_product: ≤ 8 queries cold cache, ≤ 1 warm | query-count | `quoteshop/quoteshop_catalog/tests/test_query_counts.py::TestCatalogQueryCounts::test_get_product` | planned |
| NFR-03 | 3 | submit_enquiry (100 lines): ≤ 40 queries, same count as 1 line (no N+1) | query-count | `quoteshop/quoteshop_enquiry/tests/test_query_counts.py::TestEnquiryQueryCounts::test_submit_enquiry_100_lines` | planned |
| NFR-04 | 6 | /q page (100 lines): ≤ 15 queries | query-count | `quoteshop/quoteshop_website/tests/test_query_counts.py::TestPageQueryCounts::test_q_page_100_lines` | planned |
| NFR-05 | 7 | /account orders: ≤ 15 queries, independent of order count | query-count | `quoteshop/quoteshop_website/tests/test_query_counts.py::TestPageQueryCounts::test_account_orders` | planned |
| NFR-06 | 1 | Coverage ≥ 85% lines for quoteshop Python | CI | `.github/workflows/ci.yml` job `tests`, step "Coverage gate" | planned |
| NFR-07 | 1 | Coverage 100% for money, version, token, accept and order logic | CI | `.github/workflows/ci.yml` job `tests`, step "Coverage gate" (per-module `--include`) | planned |
| NFR-08 | 2 | Lighthouse mobile performance ≥ 90 on home, category, product | e2e | qa: Lighthouse mobile run on `/`, `/c/<route>`, `/p/<route>` | planned |
| NFR-09 | 2 | Bundle budget: first catalog page < 120 KB gzipped excl. images | rendering | `quoteshop/quoteshop_website/tests/test_bundle_budget.py::TestBundleBudget::test_first_catalog_page_under_budget` | planned |
| NFR-10 | 2 | Accessibility: automated check, no critical issues, every page | e2e | `cypress/integration/qs_a11y.js::"no critical issues"` | planned |
| NFR-11 | 3 | Accessibility: keyboard-only quote journey | e2e | `cypress/integration/qs_a11y.js::"keyboard-only quote journey"` | planned |
| NFR-12 | 2 | Visual comparison vs docs/design at 1280 and 390, light and dark, every page | visual | qa: screenshot comparison per page vs `docs/design/*.dc.html` | planned |
| NFR-13 | 1 | Layout assertion from DocType meta (see DSK-14 to DSK-20) | layout | `quoteshop/quoteshop_settings/tests/test_layout.py::TestLayout` | planned |
| NFR-14 | 3 | Every whitelisted method tested as Guest, buyer, Sales User, Sales Manager | API | `quoteshop/quoteshop_website/tests/test_api_permission_matrix.py::TestAPIPermissionMatrix::test_whitelisted_methods_by_role` | planned |
| NFR-15 | 1 | No network in tests: WhatsApp send/webhook mocked at frappe_whatsapp boundary | unit | `quoteshop/quoteshop_enquiry/tests/test_whatsapp.py::TestWhatsAppMessages::test_no_network_calls` | planned |
| NFR-16 | 1 | No unexplained skipped tests; whole suite green in CI | CI | `.github/workflows/ci.yml` job `tests` | planned |
| NFR-17 | 1 | Tests never depend on site data: Company / Fiscal Year / Warehouse / Price List come from factories | unit, integration | `quoteshop/quoteshop_enquiry/tests/factories.py` used by all QS tests; review gate | planned |
