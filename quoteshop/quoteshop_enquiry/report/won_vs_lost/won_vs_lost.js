frappe.query_reports["Won vs Lost"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "salesperson",
			label: __("Salesperson"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "buyer_type",
			label: __("Buyer Type"),
			fieldtype: "Data",
		},
	],
};
