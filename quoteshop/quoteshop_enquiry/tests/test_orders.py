"""Phase 6 - create_order: ONE Sales Order, Customer, Deal Won; expiry job (CONTRACTS §2.6-2.7, §7.2)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from quoteshop.quoteshop_enquiry import orders, versions
from quoteshop.quoteshop_enquiry.tests.factories import (
	make_customer_group,
	make_enquiry_settings,
	make_item_price,
	make_order_settings,
	make_quote,
	make_user,
	send_quote,
	accept_and_order,
)

ASSIGNEE = "qs-b-order-sales@example.com"
OTHER_MANAGER = "qs-b-order-manager@example.com"
TRADE_GROUP = "_QS Test Trade Group"
DAY = "2026-06-10 10:00:00"


def line(code, qty, listed, **extra):
	return {"item_code": code, "requested_qty": qty, "listed_rate": listed, **extra}


class OrderTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(ASSIGNEE, ["Sales User"])
		make_user(OTHER_MANAGER, ["Sales User"])
		cls.store = make_order_settings()
		make_enquiry_settings(
			buyer_types=[
				{"label": "Retailer", "customer_group": make_customer_group(TRADE_GROUP)},
				{"label": "Club"},
			]
		)

	def ordered(self, mobile, lines=None, discount=None, **fields):
		"""Quote → priced (optional per-line edits) → sent → accepted → order job. Returns (enquiry, SO name)."""
		doc = make_quote(lines or [line("_QS-O-A", 4, 250), line("_QS-O-B", 2, 99.5)], mobile=mobile, **fields)
		if discount:
			versions.apply_discount(doc.name, discount, "all")
		order = accept_and_order(doc.name, send_quote(doc.name).token)
		return frappe.get_doc("QS Enquiry", doc.name), order


class TestSalesOrderCreation(OrderTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.lines = [
			line("_QS-O-L1", 10, 120, lead_time_days=7),  # listed 120 snapshot; Item Price later 150
			line("_QS-O-L2", 4, 75.5, availability="Partial", offered_qty=3),
			line("_QS-O-L3", 2, 60, availability="Not Available"),
			line("_QS-O-L4", 5, 10, offered_qty=0),
			line("_QS-O-L5", 1, 1000),
		]
		with cls.freeze_time(DAY):
			cls.doc = make_quote(cls.lines, mobile="+919800000101", assigned_to=ASSIGNEE, buyer_type="Retailer", deal=True)
			versions.apply_discount(cls.doc.name, 10, "all")
			make_item_price("_QS-O-L1", 150)  # price list moved after the request
			cls.order_name = accept_and_order(cls.doc.name, send_quote(cls.doc.name).token)
		cls.doc.reload()
		cls.so = frappe.get_doc("Sales Order", cls.order_name)
		cls.so_lines = {r.item_code: r for r in cls.so.items}

	def test_header(self):
		self.assertEqual(self.so.selling_price_list, self.store.starting_price_list)
		self.assertEqual(self.so.company, self.store.default_company)
		self.assertEqual(self.so.order_type, "Sales")
		self.assertEqual(self.so.ignore_pricing_rule, 1)
		self.assertEqual(self.so.contact_person, self.doc.contact)
		self.assertEqual(getdate(self.so.transaction_date), getdate("2026-06-10"))

	def test_rates(self):
		expected = {"_QS-O-L1": (120.0, 108.0), "_QS-O-L2": (75.5, 67.95), "_QS-O-L5": (1000.0, 900.0)}
		self.assertEqual({c: (r.price_list_rate, r.rate) for c, r in self.so_lines.items()}, expected)
		self.assertEqual(self.so.net_total, self.doc.total_offered)
		self.assertEqual(self.so.net_total, 10 * 108 + 3 * 67.95 + 900.0)

	def test_only_offered_lines(self):
		self.assertEqual(sorted(self.so_lines), ["_QS-O-L1", "_QS-O-L2", "_QS-O-L5"])
		self.assertEqual({c: r.qty for c, r in self.so_lines.items()}, {"_QS-O-L1": 10, "_QS-O-L2": 3, "_QS-O-L5": 1})

	def test_delivery_dates(self):
		self.assertEqual(getdate(self.so_lines["_QS-O-L1"].delivery_date), getdate("2026-06-17"))
		self.assertEqual(getdate(self.so_lines["_QS-O-L5"].delivery_date), getdate("2026-06-10"))
		self.assertEqual(getdate(self.so.delivery_date), getdate("2026-06-17"))

	def test_qs_fields(self):
		self.assertEqual((self.so.qs_enquiry, self.so.qs_version), (self.doc.name, 1))
		self.assertEqual({c: r.qs_requested_qty for c, r in self.so_lines.items()}, {"_QS-O-L1": 10, "_QS-O-L2": 4, "_QS-O-L5": 1})
		self.assertEqual(self.doc.sales_order, self.so.name)

	def test_draft_when_auto_submit_off(self):
		self.assertEqual(self.so.docstatus, 0)

	def test_submitted_when_auto_submit_on(self):
		with self.change_settings("QS Store Settings", auto_submit_sales_order=1):
			_doc, order = self.ordered("+919800000102")
		self.assertEqual(frappe.db.get_value("Sales Order", order, "docstatus"), 1)

	def test_deal_won(self):
		status = frappe.db.get_value("CRM Deal", self.doc.crm_deal, "status")
		self.assertEqual(frappe.db.get_value("CRM Deal Status", status, "type"), "Won")
		self.assertEqual(frappe.db.get_value("CRM Deal", self.doc.crm_deal, "deal_value"), self.doc.total_offered)

	def test_customer_created(self):
		customer = frappe.get_doc("Customer", self.so.customer)
		self.assertEqual(self.doc.customer, customer.name)
		self.assertEqual(customer.customer_group, TRADE_GROUP)
		self.assertEqual(customer.territory, self.store.default_territory)
		self.assertEqual(customer.account_manager, ASSIGNEE)
		self.assertEqual(customer.customer_primary_contact, self.doc.contact)
		links = frappe.get_all(
			"Dynamic Link", filters={"parenttype": "Contact", "parent": self.doc.contact, "link_doctype": "Customer"}, pluck="link_name"
		)
		self.assertEqual(links, [customer.name])

	def test_no_duplicate_contact(self):
		self.assertEqual(frappe.db.count("Contact", {"mobile_no": "+919800000101"}), 1)
		self.assertEqual(
			frappe.db.count("Dynamic Link", {"parenttype": "Contact", "link_doctype": "Customer", "link_name": self.so.customer}), 1
		)

	def test_customer_group_default_without_buyer_type(self):
		doc, order = self.ordered("+919800000103", buyer_type="Club")
		customer = frappe.db.get_value("Sales Order", order, "customer")
		self.assertEqual(frappe.db.get_value("Customer", customer, "customer_group"), self.store.default_customer_group)

	def test_customer_reused(self):
		first, order1 = self.ordered("+919800000104", assigned_to=ASSIGNEE)
		frappe.db.set_value("Customer", first.customer, "account_manager", OTHER_MANAGER)
		customers = frappe.db.count("Customer")
		second, order2 = self.ordered("+919800000104", assigned_to=ASSIGNEE)
		self.assertEqual(second.customer, first.customer)
		self.assertEqual(frappe.db.get_value("Sales Order", order2, "customer"), first.customer)
		self.assertEqual(frappe.db.count("Customer"), customers)
		self.assertEqual(frappe.db.get_value("Customer", first.customer, "account_manager"), OTHER_MANAGER)
		self.assertEqual(frappe.db.count("Contact", {"mobile_no": "+919800000104"}), 1)

	def test_create_order_idempotent(self):
		self.assertEqual(orders.create_order(self.doc.name, 1), self.so.name)
		with self.set_user("Guest"):
			self.assertEqual(orders.create_order(self.doc.name, 1), self.so.name)
		self.assertEqual(frappe.db.count("Sales Order", {"qs_enquiry": self.doc.name}), 1)

	def test_order_job_queues_accepted_message_once(self):
		doc = make_quote([line("_QS-O-M", 1, 10)], mobile="+919800000105")
		token = send_quote(doc.name).token
		with patch("frappe.enqueue"), self.set_user("Guest"):
			from quoteshop.quoteshop_enquiry import quote_view

			quote_view.accept_quote(doc.name, token)
		with patch("frappe.enqueue") as enqueue:
			orders.create_order(doc.name, 1)
			orders.create_order(doc.name, 1)
		events = [c.kwargs["event"] for c in enqueue.call_args_list]
		self.assertEqual(events, ["accepted"])

	def test_unaccepted_version_creates_nothing(self):
		doc = make_quote([line("_QS-O-N", 1, 10)], mobile="+919800000106")
		send_quote(doc.name)
		self.assertIsNone(orders.create_order(doc.name, 1))
		self.assertFalse(frappe.db.exists("Sales Order", {"qs_enquiry": doc.name}))

	def test_enquiry_read_only_after_accept(self):
		doc = frappe.get_doc("QS Enquiry", self.doc.name)
		doc.notes = "edited after accept"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		doc.reload()
		doc.items[0].offered_rate = 1
		with self.assertRaises(frappe.ValidationError):
			doc.save()


class TestExpiryJob(OrderTestCase):
	def run_job(self):
		with patch.object(frappe.db.__class__, "commit"), patch("frappe.enqueue"):  # the job commits per enquiry
			orders.expire_quotes()

	def test_expires_past_validity_only(self):
		with self.freeze_time(DAY):
			past = make_quote([line("_QS-O-X1", 1, 10)], deal=True)
			send_quote(past.name)  # valid till 2026-06-25
		with self.freeze_time("2026-06-20 10:00:00"):
			fresh = make_quote([line("_QS-O-X2", 1, 10)])
			send_quote(fresh.name)  # valid till 2026-07-05
		requested = make_quote([line("_QS-O-X3", 1, 10)])
		frappe.db.set_value("QS Enquiry", requested.name, "valid_till", "2026-01-01")

		with self.freeze_time("2026-06-26 08:00:00"):
			self.run_job()
		status = lambda d: frappe.db.get_value("QS Enquiry", d.name, "status")  # noqa: E731
		self.assertEqual((status(past), status(fresh), status(requested)), ("Expired", "Price Sent", "Requested"))
		self.assertEqual(frappe.db.get_value("CRM Deal", frappe.db.get_value("QS Enquiry", past.name, "crm_deal"), "status"), "Expired")

		with self.freeze_time("2026-06-25 08:00:00"):  # valid_till day itself is still valid
			other = make_quote([line("_QS-O-X4", 1, 10)])
			frappe.db.set_value("QS Enquiry", other.name, {"status": "Price Sent", "valid_till": "2026-06-25"})
			self.run_job()
			self.assertEqual(status(other), "Price Sent")

	def test_idempotent(self):
		with self.freeze_time(DAY):
			doc = make_quote([line("_QS-O-X5", 1, 10)])
			send_quote(doc.name)
		with self.freeze_time("2026-07-01 08:00:00"):
			self.run_job()
			modified = frappe.db.get_value("QS Enquiry", doc.name, "modified")
			self.run_job()
		self.assertEqual(frappe.db.get_value("QS Enquiry", doc.name, ["status", "modified"]), ("Expired", modified))

	def test_expired_quote_cannot_be_accepted_but_can_be_repriced(self):
		with self.freeze_time(DAY):
			doc = make_quote([line("_QS-O-X6", 1, 10)])
			token = send_quote(doc.name).token
		with self.freeze_time("2026-07-01 08:00:00"):
			self.run_job()
			with self.set_user("Guest"):
				from quoteshop.quoteshop_enquiry import quote_view

				self.assertTrue(quote_view.accept_quote(doc.name, token)["outdated"])
			resent = send_quote(doc.name)
		self.assertEqual((resent.version, frappe.db.get_value("QS Enquiry", doc.name, "status")), (2, "Price Sent"))
		self.assertEqual(getdate(frappe.db.get_value("QS Enquiry", doc.name, "valid_till")), getdate(add_days("2026-07-01", 15)))


class TestOrderFixes(OrderTestCase):
	"""CONTRACTS §10: Alternative lines, create_order as Administrator / never raises, retry_order."""

	def test_alternative_line_orders_the_alternative_item(self):
		from quoteshop.quoteshop_enquiry.tests.factories import make_item

		make_item("_QS-O-ALT", item_name="_QS Alt Item", stock_uom="Box")
		doc = make_quote([line("_QS-O-ORIG", 3, 200), line("_QS-O-KEEP", 1, 50)], mobile="+919800000110")
		row = next(r for r in doc.items if r.item_code == "_QS-O-ORIG")
		versions.set_availability(doc.name, [row.name], "Alternative", note="Box of 3")
		frappe.db.set_value("QS Enquiry Item", row.name, {"alternative_item": "_QS-O-ALT", "offered_rate": 180})
		order = accept_and_order(doc.name, send_quote(doc.name).token)
		lines = {r.item_code: r for r in frappe.get_doc("Sales Order", order).items}
		self.assertEqual(sorted(lines), ["_QS-O-ALT", "_QS-O-KEEP"])
		alt = lines["_QS-O-ALT"]
		self.assertEqual((alt.item_name, alt.uom, alt.qty), ("_QS Alt Item", "Box", 3))
		self.assertEqual((alt.price_list_rate, alt.rate, alt.qs_requested_qty), (200.0, 180.0, 3))

	def accepted(self, mobile):
		doc = make_quote([line("_QS-O-F", 2, 10)], mobile=mobile)
		token = send_quote(doc.name).token
		with patch("frappe.enqueue"), self.set_user("Guest"):
			from quoteshop.quoteshop_enquiry import quote_view

			quote_view.accept_quote(doc.name, token)
		return doc.name

	def test_create_order_runs_as_administrator(self):
		name = self.accepted("+919800000111")
		with self.set_user("Guest"), patch("frappe.enqueue"):
			order = orders.create_order(name, 1)
			self.assertEqual(frappe.session.user, "Guest")  # caller's user restored
		self.assertEqual(frappe.db.get_value("Sales Order", order, "owner"), "Administrator")

	def test_create_order_never_raises(self):
		name = self.accepted("+919800000112")
		errors = frappe.db.count("Error Log", {"method": "QuoteShop: Sales Order not created"})
		with patch.object(orders, "_sales_order", side_effect=frappe.ValidationError("boom <b>")), patch("frappe.enqueue"):
			self.assertIsNone(orders.create_order(name, 1))
		self.assertFalse(frappe.db.exists("Sales Order", {"qs_enquiry": name}))
		self.assertFalse(frappe.db.get_value("QS Enquiry", name, "sales_order"))
		self.assertEqual(frappe.db.count("Error Log", {"method": "QuoteShop: Sales Order not created"}), errors + 1)
		comments = frappe.get_all(
			"Comment", filters={"reference_doctype": "QS Enquiry", "reference_name": name, "comment_type": "Comment"}, pluck="content"
		)
		self.assertTrue(any("Sales Order could not be created" in c and "&lt;b&gt;" in c for c in comments), comments)
		# savepoint rollback: the Customer created before the failure is gone too
		contact = frappe.db.get_value("QS Enquiry", name, "contact")
		self.assertFalse(
			frappe.db.exists("Dynamic Link", {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"})
		)
		self.assertEqual(frappe.db.get_value("QS Enquiry", name, "status"), "Accepted")

	def test_retry_order(self):
		manager = "qs-b-order-sm@example.com"
		make_user(manager, ["Sales User", "Sales Manager"])
		name = self.accepted("+919800000113")
		with patch.object(orders, "_sales_order", side_effect=frappe.ValidationError("boom")), patch("frappe.enqueue"):
			orders.create_order(name, 1)

		with self.set_user(ASSIGNEE), self.assertRaises(frappe.PermissionError):
			orders.retry_order(name)
		with self.set_user(manager), patch("frappe.enqueue") as enqueue:
			self.assertEqual(orders.retry_order(name), {"queued": True})
		call = enqueue.call_args
		self.assertEqual((call.args[0], call.kwargs["job_id"]), ("quoteshop.quoteshop_enquiry.orders.create_order", f"qs-order-{name}"))
		self.assertEqual((call.kwargs["enquiry"], call.kwargs["version"]), (name, 1))

		with patch("frappe.enqueue"):
			orders.create_order(name, 1)
		with self.set_user(manager), self.assertRaises(frappe.ValidationError):
			orders.retry_order(name)  # already has a Sales Order

	def test_retry_order_needs_accepted(self):
		doc = make_quote([line("_QS-O-G", 1, 10)], mobile="+919800000114")
		send_quote(doc.name)
		with self.assertRaises(frappe.ValidationError):
			orders.retry_order(doc.name)
