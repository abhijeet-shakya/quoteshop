# QuoteShop QA

## Design baselines (TESTING.md §2 item 10, visual comparison)

The design files (`apps/quoteshop/docs/design/*.dc.html`) need the design tool runtime `./support.js`, which is not in the export. `render/support.js` is a small stand-in written for QA so the files render in a normal browser.

### Re-render (one command, from the bench root)

```sh
node apps/quoteshop/docs/qa/render/baselines.mjs
```

The script:
1. Copies `docs/design/*.dc.html` into `render/`. The design sources are never changed.
2. Adds the canonical light tokens from CONTRACTS §8 to the copies whose light theme has self-referencing tokens: Item, Main, Mobile, MobileItem, MobileQuote, Quote.
3. Serves `render/` with `python3 -m http.server` on a free localhost port, and stops it at the end.
4. Screenshots each file twice, with `?dark=0` and `?dark=1`, at its `$preview` viewport (desktop 1280 wide, mobile 390 wide). Each screenshot is a full-page PNG.
5. Checks every render and exits 1 on any failure. A render passes when:
   - no `{{` and no `sc-for`/`sc-if`/`helmet` tags are left
   - `data-theme` matches the theme requested
   - every `var(--x)` used resolves
   - each visible loop has as many items as its data list
   - there are no JS errors
   - a click on Main's theme toggle switches it to dark

The script needs Playwright 1.62.1, which it loads from `apps/crm/node_modules/playwright`; set `PLAYWRIGHT_PATH` to use another copy. It also needs Chromium in `~/Library/Caches/ms-playwright`; install it with `node apps/crm/node_modules/playwright/cli.js install chromium`.

To view a design in a browser: `cd apps/quoteshop/docs/qa/render && python3 -m http.server`, then open `http://localhost:8000/Main.dc.html?dark=1`. Any prop can be set in the query, e.g. `&showPrices=0&accent=%23B4372A`.

### Baselines (`design-baselines/`)

22 core PNGs, 11 screens × light/dark:

| Screen | Viewport | Light | Dark |
|---|---|---|---|
| Account | 1280×900 | Account-light.png | Account-dark.png |
| Item | 1280×1360 | Item-light.png | Item-dark.png |
| Main | 1280×2680 | Main-light.png | Main-dark.png |
| Quote | 1280×1000 | Quote-light.png | Quote-dark.png |
| QuoteDetail | 1280×1500 (page 1887) | QuoteDetail-light.png | QuoteDetail-dark.png |
| Mobile | 390×844 | Mobile-light.png | Mobile-dark.png |
| MobileItem | 390×844 | MobileItem-light.png | MobileItem-dark.png |
| MobileOrders | 390×844 | MobileOrders-light.png | MobileOrders-dark.png |
| MobileQuote | 390×844 | MobileQuote-light.png | MobileQuote-dark.png |
| MobileQuoteDetail | 390×844 | MobileQuoteDetail-light.png | MobileQuoteDetail-dark.png |
| WhatsAppQuote | 390×844 | WhatsAppQuote-light.png | WhatsAppQuote-dark.png |

The mobile designs are 390×844 phone frames that scroll inside the frame. The extra `*-unrolled.png` files show the whole scrolled content with the frame's inner scroll removed. Compare these against a real mobile page, which scrolls the whole document. There are 8 of them: Mobile, MobileItem, MobileQuote and MobileQuoteDetail, each in light and dark. MobileOrders and WhatsAppQuote have no overflow, so they have no unrolled version.

### Renderer limitations
- Expressions are property paths plus `true`/`false`/`null`/number/string literals. That covers every expression in the current files; arbitrary JS is not supported.
- Every `setState` re-renders the whole tree. As a result, a focused input loses focus after each keystroke, e.g. the search field filters but you have to click it again.
- Under `file://` the template is read from the parsed DOM, and the parser moves `<sc-for>` out of `<tbody>`, which breaks Account and QuoteDetail. Always serve the files over http.
- `onChange` on input/textarea is wired to the `input` event (React semantics). Other `onX` attributes are wired to the event `x`.
- Screenshots show the default state of each design: the cart, open groups and active tab all come from the initial state. Sticky bars appear where they sit at the end of the scroll.
- WhatsAppQuote has no theme prop, so its light and dark PNGs are identical.
- Loop-count checks cover loops that are not nested inside another loop. Nested loops (`o.lines`, `g.lines`) were checked by eye.
