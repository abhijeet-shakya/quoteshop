// Storefront tab: listed vs final price from the QS Enquiry this order came from (never stored).
frappe.ui.form.on("Sales Order", {
	async refresh(frm) {
		const field = frm.fields_dict.qs_price_summary_html;
		if (!field || !frm.doc.qs_enquiry || !frappe.model.can_read("QS Enquiry")) return;

		// get_value applies the enquiry permission rules: {} when this user may not read it.
		const { message: e } = await frappe.db.get_value("QS Enquiry", frm.doc.qs_enquiry, [
			"total_listed",
			"total_offered",
			"total_saved",
			"saved_pct",
			"line_count",
			"unit_count",
		]);
		if (!e || e.total_offered === undefined) return;

		const money = (v) => format_currency(v, frm.doc.currency);
		const rows = [
			[__("Listed total"), `<s class="text-muted">${money(e.total_listed)}</s>`],
			[__("Final total"), `<b>${money(e.total_offered)}</b>`],
			e.total_saved > 0 && [
				__("Saved"),
				`<span class="indicator-pill green">${money(e.total_saved)} (${flt(e.saved_pct, 2)}%)</span>`,
			],
			[__("Lines"), __("{0} lines · {1} pcs", [e.line_count, e.unit_count])],
		].filter(Boolean);

		field.html(`<table class="table table-bordered table-sm">
			${rows.map(([label, value]) => `<tr><td class="text-muted">${label}</td><td class="text-right">${value}</td></tr>`).join("")}
		</table>`);
	},
});
