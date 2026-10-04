// Phase 2 e2e: TESTING.md §4 journey 1 (browse -> filter -> search -> product -> add 3 -> quote pill), theme and
// keyboard add-to-quote. Not runnable until catalog-web has built the pages and the bundles.
// Needs the seed: bench --site <site> execute quoteshop.tests.e2e_seed.seed
//
// Selectors are PROPOSED by test-lead (CONTRACTS is silent) - catalog-web must emit them or ask to change them:
const SEL = {
	card: "[data-qs-card]", // one per product, on / /c/* /search
	add: "[data-qs-add]", // <button> that adds the item to the quote list (cards and product page)
	chip: "[data-qs-chip]", // category link (href /c/<route>) in the chip row
	search: 'input[name="q"]', // search box (form GET /search)
	count: "[data-qs-quote-count]", // quote pill / floating bar counter, text = number of lines
	toggle: "[data-qs-theme-toggle]", // theme toggle button
};
const VIEWPORTS = [
	[1280, 900],
	[390, 844],
];
const THEMES = ["light", "dark"];
const FIRST_THREE = ["E2E-CUE-1", "E2E-CUE-2", "E2E-CUE-3"];

const quote = () =>
	cy.window().then((win) => JSON.parse(win.localStorage.getItem("qs-quote")));

// storage shape (CONTRACTS §8): {"v": 1, "items": [{"item_code": str, "qty": number}]}
const expectQuote = (items) =>
	quote().should("deep.equal", { v: 1, items: items.map(([item_code, qty]) => ({ item_code, qty })) });

// window events do not survive page loads: attach after every cy.visit
const recordQuoteEvents = () =>
	cy.window().then((win) => {
		win.__qsEvents = [];
		win.addEventListener("qs:quote-changed", (e) => win.__qsEvents.push(e.detail));
	});
const lastEvent = () => cy.window().then((win) => win.__qsEvents[win.__qsEvents.length - 1]);
const visiblePill = () => cy.get(SEL.count).filter(":visible").first();

const visitAs = (path, theme) =>
	cy.visit(path, {
		onBeforeLoad(win) {
			win.localStorage.setItem("qs-theme", theme);
		},
	});

VIEWPORTS.forEach(([width, height]) => {
	THEMES.forEach((theme) => {
		describe(`catalog journey ${width}x${height} ${theme}`, () => {
			beforeEach(() => cy.viewport(width, height));

			it("renders the home page in the stored theme", () => {
				visitAs("/", theme);
				cy.get("html").should("have.attr", "data-theme", theme);
				cy.get(SEL.card).should("have.length", 6);
				cy.contains("E2E hero title");
			});

			it("browse, filter by chip, search, open a product", () => {
				visitAs("/", theme);
				cy.get(SEL.chip).contains("E2E Chalk").click();
				cy.location("pathname").should("match", /^\/c\/.+/);
				cy.get(SEL.card).should("have.length", 2).and("contain.text", "E2E Chalk");

				cy.get(SEL.search).filter(":visible").first().type("gamma{enter}");
				cy.location("pathname").should("eq", "/search");
				cy.location("search").should("include", "q=gamma");
				cy.get(SEL.card).should("have.length", 1).and("contain.text", "E2E Cue Gamma");

				cy.get(SEL.card).first().find('a[href^="/p/"]').first().click();
				cy.location("pathname").should("match", /^\/p\/.+/);
				cy.get("h1").should("contain.text", "E2E Cue Gamma");
				cy.contains(/From\s*₹\s*700/);
			});

			it("adds three items; pill and event follow; storage has the contract shape", () => {
				visitAs("/", theme);
				recordQuoteEvents();
				FIRST_THREE.forEach((code, i) => {
					cy.get(SEL.add).eq(i).click();
					visiblePill().should("contain.text", String(i + 1));
					lastEvent().should("deep.equal", { count: i + 1, units: i + 1 });
				});
				expectQuote(FIRST_THREE.map((code) => [code, 1]));

				// same item again merges into one line (qty 2), count stays 3, units become 4
				cy.get(SEL.add).eq(0).click();
				lastEvent().should("deep.equal", { count: 3, units: 4 });
				expectQuote([["E2E-CUE-1", 2], ["E2E-CUE-2", 1], ["E2E-CUE-3", 1]]);
				quote().then((q) => {
					expect(Object.keys(q)).to.deep.equal(["v", "items"]);
					q.items.forEach((line) => {
						expect(Object.keys(line).sort()).to.deep.equal(["item_code", "qty"]);
						expect(line.qty).to.be.a("number");
					});
				});
			});

			it("quote list survives navigation", () => {
				visitAs("/", theme);
				cy.get(SEL.add).eq(0).click();
				cy.get(SEL.add).eq(1).click();
				visitAs("/search?q=chalk", theme);
				visiblePill().should("contain.text", "2");
				expectQuote([["E2E-CUE-1", 1], ["E2E-CUE-2", 1]]);
			});
		});
	});
});

describe("theme", () => {
	beforeEach(() => cy.viewport(1280, 900));

	it("toggle persists after reload", () => {
		cy.visit("/");
		cy.get("html")
			.invoke("attr", "data-theme")
			.then((before) => {
				const after = before === "dark" ? "light" : "dark";
				cy.get(SEL.toggle).filter(":visible").first().click();
				cy.get("html").should("have.attr", "data-theme", after);
				cy.window().its("localStorage").invoke("getItem", "qs-theme").should("eq", after);
				cy.reload();
				cy.get("html").should("have.attr", "data-theme", after);
				cy.visit("/search?q=cue");
				cy.get("html").should("have.attr", "data-theme", after);
			});
	});

	[true, false].forEach((dark) => {
		it(`auto theme follows the OS (prefers-color-scheme: ${dark ? "dark" : "light"})`, () => {
			// seed leaves default_theme = Auto and allow_theme_switch = 1; no stored choice
			cy.visit("/", {
				onBeforeLoad(win) {
					win.matchMedia = (query) => ({
						matches: query.includes("prefers-color-scheme: dark") === dark,
						media: query,
						addEventListener() {},
						removeEventListener() {},
						addListener() {},
						removeListener() {},
					});
				},
			});
			cy.get("html").should("have.attr", "data-theme", dark ? "dark" : "light");
		});
	});
});

describe("keyboard-only add to quote", () => {
	[
		[1280, 900],
		[390, 844],
	].forEach(([width, height]) => {
		it(`adds with Enter and Space on ${width}x${height}`, () => {
			cy.viewport(width, height);
			cy.visit("/");
			recordQuoteEvents();
			cy.get(SEL.add).first().should("match", "button, a, [role=button]");
			cy.get(SEL.add).first().focus();
			cy.focused().should("have.attr", "data-qs-add");
			cy.focused().type("{enter}");
			lastEvent().should("deep.equal", { count: 1, units: 1 });
			cy.focused().type(" ");
			lastEvent().should("deep.equal", { count: 1, units: 2 });
			expectQuote([["E2E-CUE-1", 2]]);
		});
	});
	// A true Tab-order walk needs cypress-real-events (cy.realPress("Tab")), which Frappe's own config loads;
	// QuoteShop's config deliberately has no support file. Tracked for the qa a11y spec (qs_a11y.js, NFR-11).
});
