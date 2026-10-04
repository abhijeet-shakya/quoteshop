"""Phase 3 submit_enquiry (CONTRACTS §7.2, §2.5, §2.6; TEST_MATRIX QTE-01..03, QTE-12..23, NFR-03).

Re-validates items, snapshots listed_rate, finds/creates the Contact by E.164 mobile, links that Contact's
Customer, enforces settings fields/questions/buyer types and the OTP token, one transaction; WhatsApp after commit.
"""

from unittest.mock import patch

import frappe

from quoteshop.quoteshop_enquiry.tests.factories import (
	STARTING_PRICE_LIST,
	EnquiryTestCase,
	call_api,
	make_buyer_contact,
	make_colours,
	make_enquiry_settings,
	make_item_price,
	make_otp_token,
	make_published_item,
	make_qs_customer,
	make_user,
	make_website_user,
)

SUBMIT = "quoteshop.quoteshop_enquiry.api.submit_enquiry"
MOBILE = "+919811200001"
A, B, C = "_QS S-A", "_QS S-B", "_QS S-C"
HIDDEN, DISABLED, TEMPLATE = "_QS S-Unpublished", "_QS S-Disabled", "_QS S-Template"
WA_JOB = "quoteshop.quoteshop_enquiry.whatsapp.send_message"


class SubmitTestCase(EnquiryTestCase):
	def setUp(self):
		super().setUp()
		make_published_item(A, rate=150)
		make_published_item(B, rate=99.5)
		make_published_item(C, qs_min_qty=10)  # no starting price
		make_published_item(HIDDEN, rate=10, published=0)
		make_published_item(DISABLED, rate=10, disabled=1)
		make_published_item(TEMPLATE)
		frappe.db.set_value("Item", TEMPLATE, "has_variants", 1)

	def payload(self, mobile=MOBILE, **overrides):
		return {
			"items": [{"item_code": A, "qty": 2}, {"item_code": B, "qty": 3}],
			"buyer_name": "_QS Test Buyer S",
			"mobile": mobile,
			"otp_token": make_otp_token(mobile),
			**overrides,
		}

	def submit(self, data=None, user="Guest", ip="10.7.0.1", **overrides):
		"""POST submit_enquiry; returns the QS Enquiry doc. self.enqueue holds the frappe.enqueue mock."""
		with patch("frappe.enqueue") as self.enqueue:
			result = call_api(
				SUBMIT, user=user, ip=ip, data=self.payload(**overrides) if data is None else data
			)
		self.assertEqual(set(result), {"name"})
		return frappe.get_doc("QS Enquiry", result["name"])

	def assertRejected(self, exc=frappe.ValidationError, **overrides):
		before = frappe.db.count("QS Enquiry")
		with self.assertRaises(exc):
			self.submit(**overrides)
		self.assertEqual(frappe.db.count("QS Enquiry"), before)


class TestSubmitEnquiry(SubmitTestCase):
	def test_happy_path(self):
		doc = self.submit(email="buyer@example.com", business_name="_QS Biz", notes="call me")
		self.assertEqual(
			(doc.status, doc.mobile, doc.buyer_name, doc.email, doc.business_name, doc.notes),
			("Requested", MOBILE, "_QS Test Buyer S", "buyer@example.com", "_QS Biz", "call me"),
		)
		self.assertEqual(
			[(r.item_code, r.requested_qty, r.offered_qty, r.listed_rate) for r in doc.items],
			[(A, 2.0, 2.0, 150.0), (B, 3.0, 3.0, 99.5)],
		)
		self.assertEqual((doc.total_listed, doc.total_offered, doc.line_count), (598.5, 598.5, 2))
		self.assertTrue(doc.contact)
		self.assertTrue(doc.crm_deal)

	def test_every_role(self):
		"""Guest, Sales User and Sales Manager with an otp_token; a signed-in buyer by Contact.user."""
		for i, user in enumerate(
			(
				"Guest",
				make_user("_qs_sales_user_s@example.com", ("Sales User",)),
				make_user("_qs_sales_manager_s@example.com", ("Sales Manager",)),
			)
		):
			with self.subTest(user=user):
				mobile = f"+91981130000{i}"
				self.assertEqual(self.submit(user=user, mobile=mobile).mobile, mobile)
		buyer = make_website_user("_qs_buyer_s@example.com", mobile=MOBILE)
		self.assertEqual(self.submit(user=buyer, otp_token=None).mobile, MOBILE)

	def test_json_string_payload(self):
		self.assertEqual(self.submit(data=frappe.as_json(self.payload())).mobile, MOBILE)

	def test_post_only(self):
		with self.assertRaises(frappe.PermissionError):
			call_api(SUBMIT, http_method="GET", data=self.payload())

	def test_malformed_json_is_a_validation_error(self):
		"""Malformed JSON must be a clean ValidationError, not an unhandled decode error (HTTP 500)."""
		self.assertRejected(data="{not json")

	def test_invalid_data_shape_rejected(self):
		for data in ("[]", "123", frappe.as_json([self.payload()])):
			with self.subTest(data=data):
				self.assertRejected(data=data)


class TestOTPRequirement(SubmitTestCase):
	def test_requires_verified_otp(self):
		"""QTE-12: missing / garbage / other number's token → PermissionError; nothing created."""
		for token in (None, "", "garbage", make_otp_token("+919811299999")):
			with self.subTest(token=token):
				self.assertRejected(frappe.PermissionError, otp_token=token)

	def test_token_for_bare_ten_digit_number(self):
		doc = self.submit(mobile="9811200001", otp_token=make_otp_token(MOBILE))
		self.assertEqual(doc.mobile, MOBILE)

	def test_other_buyers_portal_login_does_not_prove_number(self):
		other = make_website_user("_qs_buyer_other_s@example.com", mobile="+919811299998")
		self.assertRejected(frappe.PermissionError, user=other, otp_token=None)

	def test_not_required_when_setting_off(self):
		make_enquiry_settings(otp_required=0)
		self.assertEqual(self.submit(otp_token=None).status, "Requested")

	def test_login_required_mode(self):
		make_enquiry_settings(login_mode="Required")
		self.assertRejected(frappe.PermissionError)
		buyer = make_website_user("_qs_buyer_login_s@example.com", mobile=MOBILE)
		self.assertEqual(self.submit(user=buyer).status, "Requested")


class TestItemValidation(SubmitTestCase):
	def test_typed_qty_kept(self):
		"""QTE-02"""
		doc = self.submit(items=[{"item_code": A, "qty": 7}, {"item_code": B, "qty": "13"}])
		self.assertEqual([r.requested_qty for r in doc.items], [7.0, 13.0])

	def test_qty_below_one_rejected(self):
		"""QTE-01"""
		for qty in (0, -1, 0.5):
			with self.subTest(qty=qty):
				self.assertRejected(items=[{"item_code": A, "qty": qty}])

	def test_invalid_qty_rejected(self):
		"""QTE-03: non-numeric / missing qty"""
		for row in ({"item_code": A, "qty": "abc"}, {"item_code": A}, {"item_code": A, "qty": None}):
			with self.subTest(row=row):
				self.assertRejected(items=[row])

	def test_min_qty_enforced(self):
		self.assertRejected(items=[{"item_code": C, "qty": 9}])
		self.assertEqual(self.submit(items=[{"item_code": C, "qty": 10}]).items[0].requested_qty, 10.0)

	def test_unknown_item_rejected(self):
		self.assertRejected(items=[{"item_code": A, "qty": 1}, {"item_code": "_QS no such", "qty": 1}])

	def test_unpublished_item_rejected(self):
		"""QTE-03 / tampered input: unpublished, disabled and template items."""
		for code in (HIDDEN, DISABLED, TEMPLATE):
			with self.subTest(code=code):
				self.assertRejected(items=[{"item_code": code, "qty": 1}])

	def test_revalidates_items(self):
		"""QTE-13: an item unpublished after it was added to the browser list is rejected at submit."""
		frappe.db.set_value("Item", B, "qs_published", 0)
		self.assertRejected()

	def test_duplicates_merged(self):
		doc = self.submit(items=[{"item_code": A, "qty": 2}, {"item_code": A, "qty": 3}])
		self.assertEqual([(r.item_code, r.requested_qty) for r in doc.items], [(A, 5.0)])

	def test_price_fields_in_input_rejected(self):
		"""QTE-14 / tampered input: any rate/price field on a line is rejected, not ignored."""
		for field in ("rate", "listed_rate", "offered_rate", "price", "amount"):
			with self.subTest(field=field):
				self.assertRejected(items=[{"item_code": A, "qty": 1, field: 1}])

	def test_items_required(self):
		for items in (
			None,
			[],
			"A",
			[A],
			[{"qty": 1}],
			[{"item_code": "", "qty": 1}],
			[{"item_code": 5, "qty": 1}],
		):
			with self.subTest(items=items):
				self.assertRejected(items=items)

	def test_max_500_lines(self):
		self.assertRejected(items=[{"item_code": f"_QS bulk {i}", "qty": 1} for i in range(501)])

	def test_more_than_500_items_rejected_before_iterating(self):
		"""CONTRACTS §10: the 500-item cap is checked first (also for duplicates / junk rows)."""
		for items in ([{"item_code": A, "qty": 1}] * 501, ["junk"] * 501):
			with self.subTest(first=items[0]), self.assertRaisesRegex(frappe.ValidationError, "at most 500"):
				self.submit(items=items)

	def test_qty_must_be_finite_and_capped(self):
		"""CONTRACTS §10: NaN / inf / > 100000 rejected (also when duplicates add up past the cap)."""
		for qty in ("nan", "NaN", "inf", "-inf", "1e309", 100001):
			with self.subTest(qty=qty):
				self.assertRejected(items=[{"item_code": A, "qty": qty}])
		self.assertRejected(items=[{"item_code": A, "qty": 60000}, {"item_code": A, "qty": 40001}])
		self.assertEqual(
			self.submit(items=[{"item_code": A, "qty": 100000}]).items[0].requested_qty, 100000.0
		)


class TestColourLines(SubmitTestCase):
	"""CONTRACTS §11: a line is an (item_code, colour) pair; colour must be one of the item's labels or empty."""

	def setUp(self):
		super().setUp()
		make_colours(A, "Red", ("Blue", "#0000ff"))

	def lines(self, doc):
		return [(r.item_code, r.colour or "", r.requested_qty) for r in doc.items]

	def test_two_colours_of_one_item_are_two_lines(self):
		doc = self.submit(
			items=[{"item_code": A, "qty": 2, "colour": "Red"}, {"item_code": A, "qty": 3, "colour": "Blue"}]
		)
		self.assertEqual(self.lines(doc), [(A, "Red", 2.0), (A, "Blue", 3.0)])
		self.assertEqual((doc.line_count, doc.total_listed), (2, 750.0))
		self.assertEqual([r.listed_rate for r in doc.items], [150.0, 150.0])

	def test_same_colour_merged(self):
		doc = self.submit(
			items=[
				{"item_code": A, "qty": 2, "colour": "Red"},
				{"item_code": A, "qty": 3, "colour": "Red"},
				{"item_code": A, "qty": 1, "colour": "Blue"},
			]
		)
		self.assertEqual(self.lines(doc), [(A, "Red", 5.0), (A, "Blue", 1.0)])

	def test_no_colour_chosen_is_allowed_and_none_equals_empty(self):
		doc = self.submit(
			items=[
				{"item_code": A, "qty": 1},
				{"item_code": A, "qty": 1, "colour": ""},
				{"item_code": A, "qty": 1, "colour": None},
				{"item_code": A, "qty": 4, "colour": "Red"},
			]
		)
		self.assertEqual(self.lines(doc), [(A, "", 3.0), (A, "Red", 4.0)])

	def test_item_without_colours_has_empty_colour(self):
		doc = self.submit(items=[{"item_code": B, "qty": 1}, {"item_code": B, "qty": 1, "colour": ""}])
		self.assertEqual(self.lines(doc), [(B, "", 2.0)])

	def test_invalid_colour_rejected(self):
		for colour in ("Green", "red", "RED", " Red", "Red ", "#FF0000", 5, ["Red"], {"label": "Red"}):
			with self.subTest(colour=colour):
				self.assertRejected(items=[{"item_code": A, "qty": 1, "colour": colour}])

	def test_one_invalid_colour_rejects_the_whole_quote(self):
		self.assertRejected(
			items=[{"item_code": A, "qty": 1, "colour": "Red"}, {"item_code": A, "qty": 1, "colour": "Green"}]
		)

	def test_colour_on_item_without_colours_rejected(self):
		self.assertRejected(items=[{"item_code": B, "qty": 1, "colour": "Red"}])

	def test_colour_removed_since_added_rejected(self):
		make_colours(A, "Blue")  # Red was dropped after the buyer picked it
		self.assertRejected(items=[{"item_code": A, "qty": 1, "colour": "Red"}])

	def test_price_and_other_keys_rejected_with_colour(self):
		for field in ("rate", "listed_rate", "offered_rate", "price", "amount", "swatch", "colours", "name"):
			with self.subTest(field=field):
				self.assertRejected(items=[{"item_code": A, "qty": 1, "colour": "Red", field: 1}])

	def test_min_qty_applies_per_colour_line(self):
		make_colours(C, "Red", "Blue")  # min qty 10
		self.assertRejected(items=[{"item_code": C, "qty": 6, "colour": "Red"}])
		self.assertRejected(  # colours are separate lines: 6 + 6 does not make 12 for one of them
			items=[{"item_code": C, "qty": 6, "colour": "Red"}, {"item_code": C, "qty": 6, "colour": "Blue"}]
		)
		doc = self.submit(
			items=[
				{"item_code": C, "qty": 10, "colour": "Red"},
				{"item_code": C, "qty": 10, "colour": "Blue"},
			]
		)
		self.assertEqual(self.lines(doc), [(C, "Red", 10.0), (C, "Blue", 10.0)])

	def test_submit_100_lines_with_colours_in_budget(self):
		"""NFR-03: colours add no per-line reads (one colour query for all items)."""
		items = []
		for i in range(50):
			code = make_published_item(f"_QS SC-{i:03d}", rate=10 + i)
			for n, label in enumerate(("Red", "Blue"), 1):
				frappe.get_doc(
					{
						"doctype": "QS Item Colour",
						"parent": code,
						"parenttype": "Item",
						"parentfield": "qs_colours",
						"idx": n,
						"label": label,
						"swatch": "#112233",
					}
				).insert(ignore_permissions=True)
				items.append({"item_code": code, "qty": 1, "colour": label})
		with self.assertQueryCount(85, query_type=("select",)):
			doc = self.submit(items=items)
		self.assertEqual(doc.line_count, 100)
		self.assertEqual({r.colour for r in doc.items}, {"Red", "Blue"})


class TestListedRateSnapshot(SubmitTestCase):
	def test_snapshots_listed_rate(self):
		"""QTE-14: listed_rate = current starting price (newest valid_from); none → 0."""
		make_item_price(A, 140, valid_from=frappe.utils.add_days(frappe.utils.today(), -1))
		make_item_price(A, 999, price_list="_QS Other List")
		doc = self.submit(items=[{"item_code": A, "qty": 1}, {"item_code": C, "qty": 10}])
		self.assertEqual([r.listed_rate for r in doc.items], [140.0, 0.0])
		self.assertEqual(doc.items[0].offered_rate, 140.0)

	def test_client_price_ignored(self):
		"""Rates never come from the client: a top-level price field has no effect."""
		doc = self.submit(total_offered=1, total_listed=1, status="Accepted", assigned_to="Administrator")
		self.assertEqual((doc.total_listed, doc.status), (598.5, "Requested"))

	def test_snapshot_not_changed_by_later_price(self):
		doc = self.submit()
		make_item_price(A, 1, valid_from=frappe.utils.today())
		doc.reload()
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.items[0].listed_rate, 150.0)
		self.assertEqual(STARTING_PRICE_LIST, frappe.get_cached_doc("QS Store Settings").starting_price_list)


class TestContactAndCustomer(SubmitTestCase):
	def test_creates_contact(self):
		"""QTE-15"""
		doc = self.submit(email="new@example.com", business_name="_QS New Biz")
		contact = frappe.get_doc("Contact", doc.contact)
		self.assertEqual(
			(contact.mobile_no, contact.first_name, contact.email_id, contact.company_name),
			(MOBILE, "_QS Test Buyer S", "new@example.com", "_QS New Biz"),
		)

	def test_links_existing_contact(self):
		"""QTE-16: found by exact E.164 mobile_no; no duplicate Contact on repeat enquiries."""
		existing = make_buyer_contact(MOBILE, "_QS Existing")
		first = self.submit()
		second = self.submit(mobile="9811200001", otp_token=make_otp_token(MOBILE))
		self.assertEqual((first.contact, second.contact), (existing, existing))
		self.assertEqual(frappe.db.count("Contact", {"mobile_no": MOBILE}), 1)

	def test_links_existing_customer_by_mobile(self):
		"""QTE-17"""
		contact = make_buyer_contact(MOBILE)
		customer = make_qs_customer("_QS Test Customer S", contact=contact)
		self.assertEqual(self.submit().customer, customer)

	def test_no_customer_for_new_buyer(self):
		self.assertFalse(self.submit().customer)

	def test_atomic_rollback_on_failure(self):
		"""QTE-18: a failure after Contact/Enquiry insert commits nothing and queues no message;
		the request's rollback (simulated with a savepoint) leaves no Enquiry, Contact or Deal."""
		deals = frappe.db.count("CRM Deal")
		frappe.db.savepoint("qs_atomic")
		with (
			patch("quoteshop.quoteshop_enquiry.crm.create_deal", side_effect=frappe.ValidationError("boom")),
			patch.object(frappe.db, "commit") as commit,
			patch("frappe.enqueue") as enqueue,
			self.assertRaises(frappe.ValidationError),
		):
			call_api(SUBMIT, data=self.payload())
		commit.assert_not_called()
		self.assertFalse([c for c in enqueue.call_args_list if c.args and c.args[0] == WA_JOB])
		frappe.db.rollback(save_point="qs_atomic")
		self.assertFalse(frappe.db.exists("QS Enquiry", {"mobile": MOBILE}))
		self.assertFalse(frappe.db.exists("Contact", {"mobile_no": MOBILE}))
		self.assertEqual(frappe.db.count("CRM Deal"), deals)

	def test_whatsapp_messages_enqueued_after_commit(self):
		doc = self.submit()
		calls = [c for c in self.enqueue.call_args_list if c.args and c.args[0] == WA_JOB]
		self.assertEqual(
			sorted((c.kwargs["event"], c.kwargs["job_id"]) for c in calls),
			[
				("enquiry_alert_sales", f"qs-wa-{doc.name}-0-enquiry_alert_sales"),
				("enquiry_received_buyer", f"qs-wa-{doc.name}-0-enquiry_received_buyer"),
			],
		)
		self.assertTrue(all(c.kwargs["enqueue_after_commit"] for c in calls))


class TestFormSettings(SubmitTestCase):
	def test_buyer_name_required_and_email_validated(self):
		self.assertRejected(buyer_name="  ")
		self.assertRejected(email="not-an-email")

	def test_required_fields_per_settings(self):
		"""QTE-23: pincode required only when shown and required."""
		make_enquiry_settings(show_pincode=1, require_pincode=1)
		self.assertRejected()
		self.assertEqual(self.submit(pincode="400001").pincode, "400001")

	def test_hidden_fields_not_stored(self):
		make_enquiry_settings(show_pincode=0, show_business_name=0, show_notes=0)
		doc = self.submit(pincode="400001", business_name="_QS Biz", notes="x")
		self.assertEqual((doc.pincode, doc.business_name, doc.notes), (None, None, None))

	def test_answers_stored(self):
		"""QTE-20"""
		make_enquiry_settings(
			questions=[
				{"label": "Club name", "fieldtype": "Data"},
				{"label": "Tables", "fieldtype": "Select", "options": "1\n2-5\n6+"},
				{"label": "Need install", "fieldtype": "Check"},
				{"label": "Needed by", "fieldtype": "Date"},
			]
		)
		doc = self.submit(
			answers=[
				{"question": "Club name", "value": " Ace "},
				{"question": "Tables", "value": "2-5"},
				{"question": "Need install", "value": True},
				{"question": "Needed by", "value": "2026-12-01"},
				{"question": "Injected", "value": "ignored"},
			]
		)
		self.assertEqual(
			[(a.question, a.value) for a in doc.answers],
			[("Club name", "Ace"), ("Tables", "2-5"), ("Need install", "1"), ("Needed by", "2026-12-01")],
		)

	def test_required_question_enforced(self):
		"""QTE-22"""
		make_enquiry_settings(
			questions=[
				{"label": "Club name", "fieldtype": "Data", "required": 1},
				{"label": "Agree", "fieldtype": "Check", "required": 1},
			]
		)
		self.assertRejected(answers=[{"question": "Agree", "value": "1"}])
		self.assertRejected(
			answers=[{"question": "Club name", "value": "Ace"}, {"question": "Agree", "value": "0"}]
		)
		doc = self.submit(
			answers=[{"question": "Club name", "value": "Ace"}, {"question": "Agree", "value": "on"}]
		)
		self.assertEqual(len(doc.answers), 2)

	def test_invalid_answers_rejected(self):
		make_enquiry_settings(
			questions=[
				{"label": "Tables", "fieldtype": "Select", "options": "1\n2-5"},
				{"label": "Needed by", "fieldtype": "Date"},
			]
		)
		self.assertRejected(answers=[{"question": "Tables", "value": "99"}])
		self.assertRejected(answers=[{"question": "Needed by", "value": "not a date"}])

	def test_buyer_type_stored(self):
		"""QTE-21"""
		make_enquiry_settings(buyer_types=[{"label": "Club owner"}, {"label": "Retailer"}])
		self.assertEqual(self.submit(buyer_type="Retailer").buyer_type, "Retailer")

	def test_unknown_buyer_type_rejected(self):
		make_enquiry_settings(buyer_types=[{"label": "Club owner"}])
		self.assertRejected(buyer_type="Hacker")


class TestRateLimitAndBudget(SubmitTestCase):
	def test_rate_limited(self):
		"""QTE-19: 10 per hour per IP (failed attempts count too)."""
		for _ in range(10):
			with self.assertRaises(frappe.ValidationError):
				call_api(SUBMIT, ip="10.8.0.1", data={"items": []})
		with self.assertRaises(frappe.RateLimitExceededError):
			call_api(SUBMIT, ip="10.8.0.1", data=self.payload())
		self.assertTrue(self.submit(ip="10.8.0.2").name)  # control: another IP

	def test_submit_enquiry_100_lines(self):
		"""NFR-03 (CONTRACTS §9.9): no per-line reads. Frappe inserts each child row with its own INSERT (100
		writes, inherent) and CRM Deal / frappe_whatsapp hooks add a fixed ~70 SELECTs, so the budget is on
		SELECTs and sits just above that fixed cost: any per-line query (link validation was one) adds 100."""
		codes = [make_published_item(f"_QS SQ-{i:03d}", rate=10 + i) for i in range(100)]
		items = [{"item_code": code, "qty": 1} for code in codes]
		with self.assertQueryCount(85, query_type=("select",)):
			doc = self.submit(items=items)
		self.assertEqual(doc.line_count, 100)
