# QuoteShop

Configurable storefront: catalog website, quote list, enquiries, CRM Deal creation and assignment, Deal Won -> Customer + Sales Order, WhatsApp alerts.

## Dependencies

- `erpnext`
- `crm`
- `frappe_whatsapp`
- `erp_custom`

## Install order

Install apps on a site in exactly this order:

```
erpnext -> hrms -> crm -> frappe_whatsapp -> erp_custom -> quoteshop
```

```bash
bench --site <site> install-app quoteshop
```

## Modules

- QuoteShop Settings (`quoteshop/quoteshop_settings/`)
- QuoteShop Catalog (`quoteshop/quoteshop_catalog/`)
- QuoteShop Enquiry (`quoteshop/quoteshop_enquiry/`)
- QuoteShop Website (`quoteshop/quoteshop_website/`)

Customisations on standard DocTypes (custom fields, property setters) are versioned as
`<module>/custom/<doctype>.json` via **Customize Form -> Actions -> Export Customizations**
(or `bench --site <site> export-customizations`) — not fixtures.

## Rules

- Never edit standard apps (frappe, erpnext, hrms, crm, frappe_whatsapp).
- One owner per custom field / hook: never define the same field in two apps.
- No circular dependencies (e.g. `erp_custom` never depends on `quoteshop`).
- Client-specific changes only go in client apps (e.g. `jbb_custom`).
- Business data (brand, products, settings) is entered on the site, not hard-coded.

## License

GPLv3
