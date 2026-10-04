// Copyright (c) 2026, Abhijeet Shakya and contributors
// For license information, please see license.txt

// SPEC §5 colour maps; tests parse these literals, keep each on one line.
// prettier-ignore
const QS_STATUS_COLORS = { "Draft": "gray", "Requested": "blue", "Price Sent": "orange", "Changes Requested": "yellow", "Accepted": "green", "Lost": "red", "Expired": "darkgrey" };
// prettier-ignore
const QS_AVAILABILITY_COLORS = { "Available": "green", "Partial": "orange", "Made to Order": "blue", "Not Available": "red", "Alternative": "purple" };
// prettier-ignore
const QS_VERSION_BY_COLORS = { "Buyer": "cyan", "Sales": "blue" };

// Select value -> built-in indicator pill (same markup Frappe's list view uses for Select columns).
const qs_pill = (colors) => (value) => {
	if (!value) return "";
	const label = frappe.utils.escape_html(__(value));
	return `<span class="indicator-pill ${colors[value] || "gray"} ellipsis">${label}</span>`;
};

frappe.ui.form.on("QS Enquiry", {
	setup() {
		// Frappe's custom formatter hook for Select fields (frappe/public/js/frappe/form/formatters.js).
		const dfs = frappe.meta.docfield_map;
		dfs["QS Enquiry Item"].availability.formatter = qs_pill(QS_AVAILABILITY_COLORS);
		dfs["QS Enquiry Version"].created_by_type.formatter = qs_pill(QS_VERSION_BY_COLORS);
	},
	refresh(frm) {
		// ponytail: the toolbar already sets this from listview_settings.get_indicator; kept per spec.
		// Skipped while unsaved so Frappe's "Not Saved" indicator is not overwritten.
		if (frm.doc.status && !frm.doc.__unsaved) {
			frm.page.set_indicator(__(frm.doc.status), QS_STATUS_COLORS[frm.doc.status] || "gray");
		}
	},
});
