"""Phase 6: accept → Deal Won, Customer, ONE Sales Order (SPEC §4, CONTRACTS §2.6-2.7)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime, nowdate

from quoteshop.quoteshop_enquiry import crm, versions, whatsapp


def accept(doc, version: int, via: str) -> bool:
	"""Accept `version` if it is the latest unexpired priced version; enqueue order creation.

	`doc` must be loaded with for_update=True. Repeating an accept of the accepted version returns True."""
	latest = versions.latest_version(doc)
	if doc.status == "Accepted":
		return bool(latest and latest.version == cint(version) and latest.accepted_on)
	if (
		doc.status != "Price Sent"
		or not latest
		or latest.version != cint(version)
		or not versions.is_open(doc, latest)
	):
		return False

	versions.set_items_from_version(doc, latest)  # unsent desk edits never become part of the order
	doc.status = "Accepted"
	latest.accepted_on = now_datetime()
	latest.accepted_via = via
	doc.save(ignore_permissions=True)
	frappe.enqueue(
		"quoteshop.quoteshop_enquiry.orders.create_order",
		queue="default",
		enqueue_after_commit=True,
		job_id=f"qs-order-{doc.name}",
		deduplicate=True,
		enquiry=doc.name,
		version=latest.version,
	)
	return True


def create_order(enquiry: str, version: int) -> str | None:
	"""Job (idempotent): Deal Won, Customer found/created, ONE Sales Order, confirmation WhatsApp."""
	if frappe.session.user == "Guest":  # accepted from the website / WhatsApp webhook
		frappe.set_user("Administrator")
	doc = frappe.get_doc("QS Enquiry", enquiry, for_update=True)
	existing = doc.sales_order or frappe.db.get_value(
		"Sales Order", {"qs_enquiry": enquiry, "docstatus": ("<", 2)}
	)
	if existing:
		if not doc.sales_order:
			doc.db_set("sales_order", existing)
		return existing

	row = next((v for v in doc.versions if v.version == cint(version)), None)
	if doc.status != "Accepted" or not row or not row.accepted_on:
		frappe.log_error(
			title="QuoteShop: order not created",
			message=f"{enquiry} v{version} is not the accepted version",
			reference_doctype="QS Enquiry",
			reference_name=enquiry,
		)
		return None

	store = frappe.get_cached_doc("QS Store Settings")
	customer = _customer(doc, store)
	order = _sales_order(doc, row, customer, store)
	doc.db_set({"sales_order": order.name, "customer": customer})
	crm.sync_deal_status(doc)
	whatsapp.queue_message(enquiry, "accepted", row.version)
	return order.name


def expire_quotes() -> None:
	"""Daily: Price Sent quotes past valid_till → Expired."""
	for name in frappe.get_all(
		"QS Enquiry", filters={"status": "Price Sent", "valid_till": ("<", nowdate())}, pluck="name"
	):
		try:
			doc = frappe.get_doc("QS Enquiry", name, for_update=True)
			doc.status = "Expired"
			doc.save(ignore_permissions=True)
			crm.sync_deal_status(doc)
			frappe.db.commit()  # one enquiry per transaction: a bad one never blocks the rest
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="QuoteShop: could not expire quote", reference_doctype="QS Enquiry", reference_name=name
			)


def _customer(doc, store) -> str:
	from quoteshop.quoteshop_enquiry.api import customer_of_contact

	customer = doc.customer or customer_of_contact(doc.contact)
	if customer:
		if doc.assigned_to and not frappe.db.get_value("Customer", customer, "account_manager"):
			frappe.db.set_value("Customer", customer, "account_manager", doc.assigned_to)
		return customer

	buyer_group = next(
		(
			row.customer_group
			for row in frappe.get_cached_doc("QS Enquiry Settings").buyer_types
			if row.label == doc.buyer_type and row.customer_group
		),
		None,
	)
	new = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": doc.business_name or doc.buyer_name,
			"customer_type": "Company" if doc.business_name else "Individual",
			"customer_group": buyer_group or store.default_customer_group,
			"territory": store.default_territory,
			"account_manager": doc.assigned_to,
			# set it, or ERPNext creates a duplicate primary Contact (CONTRACTS §2.6)
			"customer_primary_contact": doc.contact,
		}
	).insert(ignore_permissions=True)
	contact = frappe.get_doc("Contact", doc.contact)
	contact.append("links", {"link_doctype": "Customer", "link_name": new.name})
	contact.save(ignore_permissions=True)
	return new.name


def _sales_order(doc, row, customer: str, store):
	today = nowdate()
	lines = [
		line
		for line in versions.snapshot(row)["lines"]
		if line.get("change_flag") != "Removed"
		and line.get("availability") != "Not Available"
		and flt(line.get("offered_qty")) > 0
	]
	if not lines:
		frappe.throw(_("Accepted quote {0} has no lines to order.").format(doc.name))

	order = frappe.new_doc("Sales Order")
	order.update(
		{
			"customer": customer,
			"company": store.default_company,
			"transaction_date": today,
			"order_type": "Sales",
			"selling_price_list": store.starting_price_list,
			"ignore_pricing_rule": 1,
			"set_warehouse": store.default_warehouse,
			"contact_person": doc.contact,
			"qs_enquiry": doc.name,
			"qs_version": row.version,
		}
	)
	for line in lines:
		order.append(
			"items",
			{
				"item_code": line["item_code"],
				"qty": flt(line["offered_qty"]),
				"uom": line.get("uom"),
				"price_list_rate": flt(line.get("listed_rate")),
				"rate": flt(line["offered_rate"]),
				"discount_percentage": 0,
				"delivery_date": add_days(today, cint(line.get("lead_time_days"))),
				"qs_requested_qty": flt(line.get("requested_qty")),
			},
		)
	order.insert(ignore_permissions=True)
	if store.auto_submit_sales_order:
		order.submit()
	return order
