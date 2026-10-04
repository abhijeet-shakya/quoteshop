// __(text, [args]) → translation of an English string from the page's #qs-i18n JSON (built from JS_STRINGS in
// quoteshop_website/context.py; add new strings there too). Named like Frappe's __ so `bench` string
// extraction finds them.
let strings;

export function __(text, args = []) {
	if (!strings) {
		try {
			strings = JSON.parse(document.getElementById("qs-i18n")?.textContent || "{}");
		} catch (e) {
			strings = {};
		}
	}
	return (strings[text] || text).replace(/\{(\d+)\}/g, (m, i) => (args[i] ?? m));
}
