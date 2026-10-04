// Copyright (c) 2026, Abhijeet Shakya and contributors
// For license information, please see license.txt

// SPEC §5 colour maps; tests parse these literals, keep each on one line.
// prettier-ignore
const QS_STATUS_COLORS = { "Draft": "gray", "Requested": "blue", "Price Sent": "orange", "Changes Requested": "yellow", "Accepted": "green", "Lost": "red", "Expired": "darkgrey" };
// prettier-ignore
const QS_AVAILABILITY_COLORS = { "Available": "green", "Partial": "orange", "Made to Order": "blue", "Not Available": "red", "Alternative": "purple" };
// prettier-ignore
const QS_VERSION_BY_COLORS = { "Buyer": "cyan", "Sales": "blue" };

const QS_VERSIONS = "quoteshop.quoteshop_enquiry.versions.";
const QS_ORDERS = "quoteshop.quoteshop_enquiry.orders.";
// Minutes after acceptance before a missing Sales Order is reported as failed (the job usually takes seconds).
const QS_ORDER_GRACE_MINUTES = 10;
// Statuses versions.py lets sales price (EDITABLE_STATUSES there).
const QS_PRICEABLE = ["Requested", "Changes Requested", "Price Sent", "Expired"];

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
		if (frm.is_new()) return;
		qs_dashboard(frm);
		qs_headline(frm);
		qs_buttons(frm);
	},
});

function qs_dashboard(frm) {
	const d = frm.doc;
	frm.dashboard.add_indicator(__("Available {0}", [d.available_count || 0]), "green");
	frm.dashboard.add_indicator(__("Partial {0}", [d.partial_count || 0]), "orange");
	frm.dashboard.add_indicator(__("Not available {0}", [d.not_available_count || 0]), "red");
	if (d.total_saved > 0) {
		const saved = format_currency(d.total_saved, frappe.boot.sysdefaults.currency);
		frm.dashboard.add_indicator(__("Saved {0} ({1}%)", [saved, flt(d.saved_pct, 2)]), "blue");
	}
}

function qs_headline(frm) {
	const d = frm.doc;
	const till = d.valid_till ? frappe.datetime.str_to_user(d.valid_till) : "";
	const so = d.sales_order ? frappe.utils.escape_html(d.sales_order) : "";
	const text = {
		Draft: __("Draft – not yet requested by the buyer."),
		Requested: __("New request. Price each line and set availability, then click Send price."),
		"Changes Requested": __(
			"The buyer requested changes. Review the flagged lines, then click Send price."
		),
		"Price Sent": __(
			"Price v{0} sent, valid till {1}. Waiting for the buyer to accept or request changes.",
			[d.current_version, till]
		),
		Accepted: so
			? __("Accepted (v{0}). Sales Order {1} created.", [d.current_version, so])
			: qs_order_pending_text(d),
		Lost: __("Lost: {0}", [frappe.utils.escape_html(d.lost_reason || "")]),
		Expired: __("The quote expired on {0}. Send a fresh price to reopen it.", [till]),
	}[d.status];
	const failed = d.status === "Accepted" && !so && qs_order_overdue(d);
	frm.dashboard.set_headline_alert(text, failed ? "red" : QS_STATUS_COLORS[d.status] || "gray");
}

function qs_accepted_on(d) {
	return (d.versions || []).find((v) => v.version === d.current_version)?.accepted_on;
}

function qs_order_overdue(d) {
	const on = qs_accepted_on(d);
	return (
		!on ||
		frappe.datetime.get_minute_diff(frappe.datetime.now_datetime(), on) >
			QS_ORDER_GRACE_MINUTES
	);
}

function qs_order_pending_text(d) {
	if (!qs_order_overdue(d)) {
		return __("Accepted (v{0}). The Sales Order is being created.", [d.current_version]);
	}
	const on = qs_accepted_on(d);
	const when = on ? frappe.datetime.comment_when(on) : "";
	return __(
		"Accepted (v{0}) {1}, but no Sales Order was created. Check the Error Log, then use Create Sales Order.",
		[d.current_version, when]
	);
}

function qs_buttons(frm) {
	const status = frm.doc.status;

	// One primary button: the next action for this status.
	const primary = {
		Requested: [__("Send price"), () => qs_send_price(frm)],
		"Changes Requested": [__("Send price"), () => qs_send_price(frm)],
		Expired: [__("Send price"), () => qs_send_price(frm)],
		"Price Sent": [__("Resend on WhatsApp"), () => qs_resend_price(frm)],
		Accepted: frm.doc.sales_order
			? [
					__("Open Sales Order"),
					() => frappe.set_route("Form", "Sales Order", frm.doc.sales_order),
			  ]
			: frappe.user.has_role(["Sales Manager", "System Manager"]) && [
					__("Create Sales Order"),
					() => qs_retry_order(frm),
			  ],
	}[status];
	if (primary) frm.add_custom_button(...primary).addClass("btn-primary");

	if (!["Accepted", "Lost"].includes(status)) {
		frm.add_custom_button(__("Mark Lost"), () => qs_mark_lost(frm));
	}

	if (QS_PRICEABLE.includes(status)) {
		const actions = __("Actions");
		if (status === "Price Sent") {
			frm.add_custom_button(__("Send updated price"), () => qs_send_price(frm), actions);
		}
		frm.add_custom_button(__("Apply discount %"), () => qs_apply_discount(frm), actions);
		frm.add_custom_button(__("Set availability"), () => qs_set_availability(frm), actions);
		frm.add_custom_button(
			__("Copy from last order"),
			() =>
				frappe.confirm(__("Copy offered rates from this buyer's last Sales Order?"), () =>
					qs_call(frm, QS_VERSIONS + "copy_from_last_order")
				),
			actions
		);
	}
}

// Saves pending edits first: the server methods work on the stored document.
async function qs_call(frm, method, args = {}) {
	if (frm.is_dirty()) await frm.save();
	const r = await frappe.call({
		method,
		args: { name: frm.doc.name, ...args },
		freeze: true,
	});
	await frm.reload_doc();
	return r.message;
}

function qs_selected_rows(frm) {
	return frm.fields_dict.items.grid.get_selected_children().map((row) => row.name);
}

function qs_send_price(frm) {
	const msg = __("Send price v{0} to {1} on WhatsApp?", [
		(frm.doc.current_version || 0) + 1,
		frappe.utils.escape_html(frm.doc.buyer_name),
	]);
	frappe.confirm(msg, async () => {
		const r = await qs_call(frm, QS_VERSIONS + "send_price");
		frappe.show_alert({ message: __("Price v{0} sent", [r.version]), indicator: "green" });
	});
}

// Same version and link again; the buyer's token is not rotated.
function qs_resend_price(frm) {
	const msg = __("Resend price v{0} to {1} on WhatsApp?", [
		frm.doc.current_version,
		frappe.utils.escape_html(frm.doc.buyer_name),
	]);
	frappe.confirm(msg, async () => {
		await qs_call(frm, QS_VERSIONS + "resend_price");
		frappe.show_alert({
			message: __("Price v{0} resent", [frm.doc.current_version]),
			indicator: "green",
		});
	});
}

function qs_retry_order(frm) {
	frappe.confirm(
		__("Create the Sales Order for the accepted version v{0} now?", [frm.doc.current_version]),
		async () => {
			await qs_call(frm, QS_ORDERS + "retry_order");
			frappe.show_alert({ message: __("Sales Order creation started"), indicator: "green" });
		}
	);
}

function qs_mark_lost(frm) {
	frappe.prompt(
		{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
		({ reason }) => qs_call(frm, QS_VERSIONS + "mark_lost", { reason }),
		__("Mark Lost"),
		__("Mark Lost")
	);
}

function qs_apply_discount(frm) {
	const rows = qs_selected_rows(frm);
	const dialog = new frappe.ui.Dialog({
		title: __("Apply discount %"),
		fields: [
			{ fieldname: "percent", fieldtype: "Percent", label: __("Discount %"), reqd: 1 },
			{
				fieldname: "scope",
				fieldtype: "Select",
				label: __("Apply to"),
				options: [
					{ value: "all", label: __("All lines") },
					{ value: "selected", label: __("Selected lines ({0})", [rows.length]) },
					{ value: "category", label: __("One category") },
				],
				default: rows.length ? "selected" : "all",
				reqd: 1,
			},
			{
				fieldname: "item_group",
				fieldtype: "Link",
				options: "Item Group",
				label: __("Category"),
				depends_on: "eval:doc.scope == 'category'",
				mandatory_depends_on: "eval:doc.scope == 'category'",
			},
		],
		primary_action_label: __("Apply"),
		primary_action: async ({ percent, scope, item_group }) => {
			if (scope === "selected" && !rows.length) {
				frappe.throw(__("Select lines in the Items table first."));
			}
			dialog.hide();
			const r = await qs_call(frm, QS_VERSIONS + "apply_discount", {
				percent,
				scope,
				rows,
				item_group,
			});
			frappe.show_alert({
				message: __("{0} lines updated", [r.updated]),
				indicator: "green",
			});
		},
	});
	dialog.show();
}

function qs_set_availability(frm) {
	const rows = qs_selected_rows(frm);
	if (!rows.length) frappe.throw(__("Select lines in the Items table first."));
	const dialog = new frappe.ui.Dialog({
		title: __("Set availability for {0} lines", [rows.length]),
		fields: [
			{
				fieldname: "availability",
				fieldtype: "Select",
				label: __("Availability"),
				options: frappe.meta.get_docfield("QS Enquiry Item", "availability").options,
				reqd: 1,
			},
			{ fieldname: "note", fieldtype: "Data", label: __("Note") },
			{ fieldname: "lead_time_days", fieldtype: "Int", label: __("Lead time (days)") },
			{
				fieldname: "offered_qty",
				fieldtype: "Float",
				label: __("Offered qty"),
				description: __("Leave empty to keep each line's quantity."),
			},
		],
		primary_action_label: __("Set"),
		primary_action: async (values) => {
			dialog.hide();
			// Empty optional fields are left out so the server keeps the line's current value.
			const args = { rows, availability: values.availability };
			for (const key of ["note", "lead_time_days", "offered_qty"]) {
				if (values[key] !== undefined && values[key] !== null && values[key] !== "") {
					args[key] = values[key];
				}
			}
			const r = await qs_call(frm, QS_VERSIONS + "set_availability", args);
			frappe.show_alert({
				message: __("{0} lines updated", [r.updated]),
				indicator: "green",
			});
		},
	});
	dialog.show();
}
