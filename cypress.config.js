// QuoteShop's own Cypress config (not Frappe's): `bench --site <site> run-ui-tests quoteshop` runs from this
// directory and injects CYPRESS_baseUrl. Seed the site first:
//   bench --site <site> execute quoteshop.tests.e2e_seed.seed
const { defineConfig } = require("cypress");

module.exports = defineConfig({
	video: false,
	viewportWidth: 1280,
	viewportHeight: 900,
	defaultCommandTimeout: 10000,
	retries: { runMode: 1, openMode: 0 },
	e2e: {
		baseUrl: process.env.CYPRESS_baseUrl || "http://localhost:8000",
		specPattern: "cypress/integration/qs_*.js",
		supportFile: false,
		// testIsolation stays on: every test starts with empty localStorage (no leaked quote list or theme).
	},
});
