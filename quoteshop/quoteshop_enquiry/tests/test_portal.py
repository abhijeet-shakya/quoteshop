"""Phase 7 - passwordless buyer portal: login, isolation, totals, savings, reorder (TESTING §3 Portal)."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from quoteshop.quoteshop_enquiry import portal, quote_view, versions
from quoteshop.quoteshop_enquiry.tests.factories import (
	accept_and_order,
	make_buyer_contact,
	make_enquiry_settings,
	make_order_settings,
	make_otp_token,
	make_quote,
	make_user,
	send_quote,
)

BUYER_1 = "+919800000201"
BUYER_2 = "+919800000202"
DESK_USER = "qs-b-portal-desk@example.com"


def line(code, qty, listed, **extra):
	return {"item_code": code, "requested_qty": qty, "listed_rate": listed, **extra}


def login(mobile, token=None):
	"""portal_login as Guest; returns (result, user the login manager was asked to log in)."""
	manager = MagicMock()
	with patch.object(frappe.local, "login_manager", manager, create=True):
		user = frappe.session.user
		frappe.set_user("Guest")
		try:
			result = portal.portal_login(mobile, token if token is not None else make_otp_token(mobile))
		finally:
			frappe.set_user(user)
	return result, manager.login_as.call_args.args[0]


def portal_user(mobile):
	return f"{mobile.lstrip('+')}@buyers.invalid"


class PortalTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_order_settings()
		make_enquiry_settings()

	@classmethod
	def order_for(cls, mobile, lines, discount=10):
		doc = make_quote(lines, mobile=mobile, buyer_name=f"_QS Buyer {mobile[-3:]}")
		versions.apply_discount(doc.name, discount, "all")
		order = accept_and_order(doc.name, send_quote(doc.name).token)
		return frappe.get_doc("QS Enquiry", doc.name), order


class TestPortalLogin(PortalTestCase):
	def test_otp_login_links_contact(self):
		contact = make_buyer_contact("+919800000211")
		result, logged_in = login("+919800000211")
		user = portal_user("+919800000211")
		self.assertEqual(result, {"redirect": "/account"})
		self.assertEqual(logged_in, user)
		self.assertEqual(frappe.db.get_value("User", user, ["user_type", "enabled"]), ("Website User", 1))
		self.assertEqual(frappe.db.get_value("Contact", contact, "user"), user)
		# frappe's User.on_update create_contact must not leave a second Contact on the same user
		self.assertEqual(frappe.get_all("Contact", filters={"user": user}, pluck="name"), [contact])

	def test_unknown_number_gets_contact(self):
		_result, user = login("+919800000212")
		self.assertEqual(frappe.db.get_value("Contact", {"mobile_no": "+919800000212"}, "user"), user)

	def test_bare_ten_digit_number_normalised(self):
		_result, user = login("9800000213", make_otp_token("+919800000213"))
		self.assertEqual(user, portal_user("+919800000213"))

	def test_no_password_stored(self):
		_result, user = login("+919800000214")
		self.assertFalse(
			frappe.db.exists("__Auth", {"doctype": "User", "name": user, "fieldname": "password"})
		)

	def test_second_login_reuses_user_and_contact(self):
		login("+919800000215")
		login("+919800000215")
		self.assertEqual(frappe.db.count("User", {"name": portal_user("+919800000215")}), 1)
		self.assertEqual(frappe.db.count("Contact", {"mobile_no": "+919800000215"}), 1)

	def test_bad_otp_token_rejected(self):
		for token in ("forged", "", make_otp_token("+919800000299")):
			with self.subTest(token=token), self.assertRaises(frappe.AuthenticationError):
				login("+919800000216", token)
		self.assertFalse(frappe.db.exists("User", portal_user("+919800000216")))

	def test_desk_user_never_handed_out(self):
		make_user(DESK_USER, ["Sales User"])
		frappe.db.set_value("Contact", make_buyer_contact("+919800000217"), "user", DESK_USER)
		with self.assertRaises(frappe.AuthenticationError):
			login("+919800000217")

	def test_non_quoteshop_website_user_refused(self):
		"""CONTRACTS §10: a Contact linked to a user QuoteShop didn't create keeps its own sign-in."""
		from quoteshop.quoteshop_enquiry.tests.factories import make_website_user

		make_website_user("qs-b-erp-portal@example.com", mobile="+919800000218")
		with self.assertRaises(frappe.AuthenticationError):
			login("+919800000218")


class TestPortalData(PortalTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enq_1, cls.so_1 = cls.order_for(BUYER_1, [line("_QS-P-A", 4, 250), line("_QS-P-B", 3, 99.99)])
		cls.enq_2, cls.so_2 = cls.order_for(BUYER_2, [line("_QS-P-C", 1, 5000)])
		cls.open_1 = make_quote([line("_QS-P-A", 1, 250)], mobile=BUYER_1)
		cls.user_1 = login(BUYER_1)[1]
		cls.user_2 = login(BUYER_2)[1]

	def data(self, user):
		with self.set_user(user):
			return portal.get_account_data()

	def test_only_own_data(self):
		for user, so, enquiries in (
			(self.user_1, self.so_1, {self.enq_1.name, self.open_1.name}),
			(self.user_2, self.so_2, {self.enq_2.name}),
		):
			data = self.data(user)
			self.assertEqual([o.name for o in data["orders"]], [so])
			self.assertEqual({r.name for r in data["requests"]}, enquiries)

	def test_direct_calls_to_other_buyer_denied(self):
		with self.set_user(self.user_1):
			self.assertEqual(quote_view.get_quote_view(self.enq_1.name)["name"], self.enq_1.name)
			for call in (
				lambda: quote_view.get_quote_view(self.enq_2.name),
				lambda: quote_view.download_quote(self.enq_2.name, None, "xlsx"),
				lambda: quote_view.accept_quote(self.enq_2.name),
				lambda: portal.reorder(self.so_2),
			):
				with self.assertRaises(frappe.PermissionError):
					call()

	def test_guest_and_other_users_denied(self):
		make_user(DESK_USER, ["Sales User"])
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			portal.get_account_data()
		for user in ("Guest", DESK_USER):
			with self.subTest(user=user), self.set_user(user), self.assertRaises(frappe.PermissionError):
				portal.reorder(self.so_1)
		try:  # a desk user may have frappe's own user Contact: then they see nothing, never a buyer's data
			data = self.data(DESK_USER)
		except frappe.PermissionError:
			return
		self.assertEqual((data["orders"], data["requests"]), ([], []))

	def test_totals_match_sales_order(self):
		order = self.data(self.user_1)["orders"][0]
		so = frappe.get_doc("Sales Order", self.so_1)
		listed = sum(flt(r.price_list_rate) * r.qty for r in so.items)
		self.assertEqual(flt(order["listed"], 2), flt(listed, 2))
		self.assertEqual(order["net_total"], so.net_total)
		self.assertEqual(flt(order["saved"], 2), flt(listed - so.net_total, 2))
		# and the Sales Order matches what the buyer accepted
		self.assertEqual((flt(listed, 2), so.net_total), (self.enq_1.total_listed, self.enq_1.total_offered))
		self.assertEqual(order["saved_pct"], self.enq_1.saved_pct)
		totals = self.data(self.user_1)["totals"]
		self.assertEqual((totals["orders"], totals["requests"], totals["open_requests"]), (1, 2, 1))
		self.assertEqual(flt(totals["final"], 2), so.net_total)

	def test_savings_shown_when_setting_on(self):
		from quoteshop.quoteshop_website.tests.helpers import render

		page = render("/account", user=self.user_1)
		self.assertEqual(page.status, 200)
		self.assertIn("You saved", page.text)
		self.assertIn(self.so_1, page.text)
		self.assertNotIn(self.so_2, page.text)

	def test_savings_hidden_when_setting_off(self):
		from quoteshop.quoteshop_website.tests.helpers import render

		with self.change_settings("QS Store Settings", show_savings_to_buyer=0):
			page = render("/account", user=self.user_1)
		self.assertEqual(page.status, 200)
		self.assertIn(self.so_1, page.text)
		for text in ("You saved", "Saved vs listed prices"):
			self.assertNotIn(text, page.text)

	def test_listed_prices_hidden_when_setting_off(self):
		"""With savings off the struck-through listed total/rates must not appear either (as on /q)."""
		from quoteshop.quoteshop_website.tests.helpers import render

		with self.change_settings("QS Store Settings", show_savings_to_buyer=0):
			page = render("/account", user=self.user_1)
		self.assertIn(self.so_1, page.text)  # the order is listed at all
		struck = [s.get_text(strip=True) for s in page.soup.find_all("s")]
		self.assertEqual([s for s in struck if s and s != "—"], [])


class TestReorder(PortalTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enq, cls.so = cls.order_for(
			BUYER_1, [line("_QS-R-A", 6, 10), line("_QS-R-B", 2, 20), line("_QS-R-GONE", 1, 30)]
		)
		cls.user = login(BUYER_1)[1]
		frappe.db.set_value("Item", "_QS-R-GONE", "qs_published", 0)

	def test_reorder_payload(self):
		with self.set_user(self.user):
			items = portal.reorder(self.so)["items"]
		self.assertEqual(
			sorted(items, key=lambda i: i["item_code"]),
			[{"item_code": "_QS-R-A", "qty": 6.0}, {"item_code": "_QS-R-B", "qty": 2.0}],
		)

	def test_unknown_order_denied(self):
		with self.set_user(self.user), self.assertRaises(frappe.PermissionError):
			portal.reorder("SAL-ORD-NOPE")
