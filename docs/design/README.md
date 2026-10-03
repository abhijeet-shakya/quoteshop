# QuoteShop design reference (source of truth)

Each `.dc.html` file is one screen from the approved design canvas.

| File | Screen |
|---|---|
| Main.dc.html | Website · Home & catalog |
| Item.dc.html | Website · Product detail |
| Quote.dc.html | Website · Quote request |
| QuoteDetail.dc.html | Website · Quote detail (100 items, availability) |
| Account.dc.html | Website · My account (orders & requests) |
| Mobile.dc.html | Mobile · Home |
| MobileItem.dc.html | Mobile · Product detail |
| MobileQuote.dc.html | Mobile · Quote request |
| MobileQuoteDetail.dc.html | Mobile · Quote detail |
| MobileOrders.dc.html | Mobile · My orders & requests |
| WhatsAppQuote.dc.html | WhatsApp price message (Accept / Change) |

Format notes for developers:
- Markup is plain HTML with inline styles (exact spacing, radii, font sizes, colours).
- `{{name}}` = a value computed in the `<script type="text/x-dc">` class at the bottom (`renderVals()`).
- `<sc-for list="{{x}}" as="y">` = loop; `<sc-if value="{{cond}}">` = conditional.
- `onClick="{{fn}}"` = click handler defined in `renderVals()`.
- Theme tokens are the CSS variables in `<helmet><style>` (`[data-theme="light"|"dark"]`).
- Sample data (product names, prices, quantities) is illustrative; real data comes from ERPNext.
- `[PLACEHOLDER]` text = value that comes from settings.
