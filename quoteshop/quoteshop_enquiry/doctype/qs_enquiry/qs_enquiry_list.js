// Copyright (c) 2026, Abhijeet Shakya and contributors
// For license information, please see license.txt

// SPEC §5 status colours; tests parse this literal, keep it on one line.
// prettier-ignore
const QS_STATUS_COLORS = { "Draft": "gray", "Requested": "blue", "Price Sent": "orange", "Changes Requested": "yellow", "Accepted": "green", "Lost": "red", "Expired": "darkgrey" };

frappe.listview_settings["QS Enquiry"] = {
	add_fields: ["status", "assigned_to", "valid_till"],
	get_indicator(doc) {
		return [__(doc.status), QS_STATUS_COLORS[doc.status] || "gray", "status,=," + doc.status];
	},
};
