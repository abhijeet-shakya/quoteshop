"""Phase 6: accept → Deal Won, Customer, ONE Sales Order, a line per (item, colour) (CONTRACTS §2.6-2.7, §11)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, flt, now_datetime, nowdate

from quoteshop.quoteshop_enquiry import crm, versions, whatsapp
from quoteshop.quoteshop_enquiry.api import colour_swatches, customer_of_contact


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
	doc.flags.qs_status_change = True
	latest.accepted_on = now_datetime()
	latest.accepted_via = via
	doc.save(ignore_permissions=True)
	_enqueue_order(doc.name, latest.version)
	return True


@frappe.whitelist(methods=["POST"])
def retry_order(name: str) -> dict:
	"""Re-queue the order job for an Accepted enquiry whose Sales Order could not be created."""
	frappe.only_for(("Sales Manager", "System Manager"))
	doc = frappe.get_doc("QS Enquiry", name)
	accepted = next((v for v in doc.versions if v.accepted_on), None)
	if doc.status != "Accepted" or not accepted:
		frappe.throw(_("Only an accepted enquiry can be ordered."))
	if doc.sales_order or frappe.db.exists("Sales Order", {"qs_enquiry": name, "docstatus": ("<", 2)}):
		frappe.throw(_("Enquiry {0} already has a Sales Order.").format(name))
	_enqueue_order(name, accepted.version)
	return {"queued": True}


def _enqueue_order(enquiry: str, version: int) -> None:
	frappe.enqueue(
		"quoteshop.quoteshop_enquiry.orders.create_order",
		queue="default",
		enqueue_after_commit=True,
		job_id=f"qs-order-{enquiry}",
		deduplicate=True,
		enquiry=enquiry,
		version=version,
	)


def create_order(enquiry: str, version: int) -> str | None:
	"""Job (idempotent): Deal Won, Customer found/created, ONE Sales Order, confirmation WhatsApp.

	Always runs as Administrator. A failure is rolled back, logged and noted on the enquiry
	(retry with `retry_order`); it never raises."""
	user = frappe.session.user
	frappe.set_user("Administrator")
	frappe.db.savepoint("qs_create_order")
	try:
		return _create_order(enquiry, version)
	except Exception as e:
		frappe.db.rollback(save_point="qs_create_order")
		frappe.log_error(
			title="QuoteShop: Sales Order not created", reference_doctype="QS Enquiry", reference_name=enquiry
		)
		frappe.get_doc("QS Enquiry", enquiry).add_comment(
			"Comment",
			_("Sales Order could not be created: {0}").format(escape_html(str(e) or repr(e))),
		)
		return None
	finally:
		frappe.set_user(user)


def _create_order(enquiry: str, version: int) -> str | None:
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
			doc.flags.qs_status_change = True
			doc.save(ignore_permissions=True)
			crm.sync_deal_status(doc)
			frappe.db.commit()  # one enquiry per transaction: a bad one never blocks the rest
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="QuoteShop: could not expire quote", reference_doctype="QS Enquiry", reference_name=name
			)


def _customer(doc, store) -> str:
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

	# an Alternative line orders the offered alternative item at the quoted rate (listed_rate kept)
	codes = {_alternative(line) or line["item_code"] for line in lines}
	items = {
		item.name: item
		for item in frappe.get_all(
			"Item",
			filters={"name": ("in", list(codes))},
			fields=["name", "item_name", "stock_uom", "description"],
		)
	}
	alternative_colours = colour_swatches([line["alternative_item"] for line in lines if _alternative(line)])
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
		alt = items.get(_alternative(line))
		ordered = alt or items.get(line["item_code"])
		# the colour carries over to an alternative only when it also comes in that colour
		colour = line.get("colour") or ""
		if alt and colour not in alternative_colours.get(alt.name, {}):
			colour = ""
		row = {
			"item_code": alt.name if alt else line["item_code"],
			"item_name": alt.item_name if alt else line.get("item_name"),
			"qty": flt(line["offered_qty"]),
			"uom": alt.stock_uom if alt else line.get("uom"),
			"price_list_rate": flt(line.get("listed_rate")),
			"rate": flt(line["offered_rate"]),
			"discount_percentage": 0,
			"delivery_date": add_days(today, cint(line.get("lead_time_days"))),
			"qs_requested_qty": flt(line.get("requested_qty")),
			"qs_colour": colour,
		}
		if colour:  # setting the description stops ERPNext filling it from the Item, so keep that text
			base = (ordered.description or ordered.item_name) if ordered else row["item_name"]
			row["description"] = f"{base}<br>{_('Colour')}: {escape_html(colour)}"
		order.append("items", row)
	order.insert(ignore_permissions=True)
	if store.auto_submit_sales_order:
		order.submit()
	return order


def _alternative(line: dict) -> str | None:
	return line.get("alternative_item") if line.get("availability") == "Alternative" else None
