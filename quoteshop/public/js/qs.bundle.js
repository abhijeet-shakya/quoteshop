// QuoteShop website bundle: one vanilla script for every QS page (CONTRACTS §8).
import { initTheme } from "./qs/theme.js";
import { initCounts, init as initCatalog } from "./qs/catalog.js";
import { init as initQuote } from "./qs/quote.js";
import { init as initQuoteView } from "./qs/quote_view.js";
import { init as initAccount } from "./qs/account.js";

const PAGES = { quote: initQuote, quote_view: initQuoteView, account: initAccount };

initTheme();
initCounts();
(PAGES[document.body.dataset.qsPage] || initCatalog)();
