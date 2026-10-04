// Storefront tab: the website's starting price for this item (CONTRACTS §2.4 rule), or "Price on request".
frappe.ui.form.on("Item", {
	refresh: qs_starting_price,
	qs_published: qs_starting_price,
	qs_hide_price: qs_starting_price,
});

async function qs_starting_price(frm) {
	const field = frm.fields_dict.qs_starting_price_html;
	if (!field || frm.is_new() || !frm.doc.qs_published) return;
	if (!frappe.model.can_read("Item Price") || !frappe.model.can_read("QS Store Settings")) return;

	const price = frm.doc.qs_hide_price ? null : await qs_find_starting_price(frm.doc);
	const text = price
		? __("From {0}", [format_currency(price.price_list_rate, price.currency)])
		: __("Price on request");
	field.html(`<p class="text-muted">${text}</p>`);
}

async function qs_find_starting_price(item) {
	const price_list = await frappe.db.get_single_value("QS Store Settings", "starting_price_list");
	if (!price_list) return null;
	const today = frappe.datetime.get_today();
	// ponytail: a handful of rows per item+list+uom; validity is checked here to keep NULL valid_from valid.
	const rows = await frappe.db.get_list("Item Price", {
		fields: ["price_list_rate", "currency", "customer", "valid_from", "valid_upto"],
		filters: { item_code: item.name, price_list, uom: item.stock_uom, selling: 1 },
		order_by: "valid_from desc",
		limit: 20,
	});
	return rows.find(
		(r) =>
			!r.customer &&
			(r.valid_from || "") <= today &&
			(!r.valid_upto || r.valid_upto >= today)
	);
}
