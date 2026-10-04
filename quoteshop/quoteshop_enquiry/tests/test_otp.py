"""Phase 3 OTP (CONTRACTS §5.5, §7.2; TEST_MATRIX QTE-06..11, QTE-26): send_otp / verify_otp.

6 digits, only a hash in Redis `qs:otp:<mobile>` = {hash, expires_at, attempts}, 10-minute expiry checked
via expires_at (freeze_time), single use, 5 wrong attempts, send limits 5/hour per number + 20/hour per IP,
developer_mode logger fallback, otp_token valid 30 minutes.
"""

import logging
import re
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from quoteshop.quoteshop_enquiry import otp as otp_service
from quoteshop.quoteshop_enquiry.tests.factories import (
	EnquiryTestCase,
	call_api,
	link_wa_templates,
	make_user,
	make_website_user,
)

MOBILE = "+919811100001"
SEND = "quoteshop.quoteshop_enquiry.api.send_otp"
VERIFY = "quoteshop.quoteshop_enquiry.api.verify_otp"
CODE = 123456


class OTPTestCase(EnquiryTestCase):
	def setUp(self):
		super().setUp()
		link_wa_templates("otp")

	def send(self, mobile=MOBILE, ip="10.9.9.1", code=CODE, user="Guest"):
		"""send_otp through the API path; returns (response, enqueue mock)."""
		with (
			patch("frappe.enqueue") as enqueue,
			patch("quoteshop.quoteshop_enquiry.otp.secrets.randbelow", return_value=code),
		):
			response = call_api(SEND, mobile=mobile, ip=ip, user=user)
		return response, enqueue

	def verify(self, otp, mobile=MOBILE, ip="10.9.9.1", user="Guest"):
		return call_api(VERIFY, mobile=mobile, otp=otp, ip=ip, user=user)

	def state(self, mobile=MOBILE):
		return frappe.cache.get_value(f"qs:otp:{mobile}", expires=True)


class TestOTP(OTPTestCase):
	def test_send_happy_path_every_role(self):
		"""Guest API; also works for logged-in users (buyer, Sales User, Sales Manager)."""
		users = (
			"Guest",
			make_website_user("_qs_buyer_otp@example.com"),
			make_user("_qs_sales_user_otp@example.com", ("Sales User",)),
			make_user("_qs_sales_manager_otp@example.com", ("Sales Manager",)),
		)
		for user in users:
			with self.subTest(user=user):
				frappe.cache.delete_keys("qs:otp")
				response, _ = self.send(user=user)
				self.assertEqual(response, {"sent": True, "expires_in": 600})

	def test_otp_six_digits_stored_hashed(self):
		"""QTE-06: zero-padded 6 digits; Redis holds only a 64-hex hash, never the code."""
		_, enqueue = self.send(code=42)
		code = enqueue.call_args.kwargs["code"]
		self.assertEqual(code, "000042")
		state = self.state()
		self.assertEqual(set(state), {"hash", "expires_at", "attempts"})
		self.assertRegex(state["hash"], r"^[0-9a-f]{64}$")
		self.assertNotIn(code, str(state))
		self.assertEqual(state["attempts"], 0)

	def test_code_never_returned_to_client(self):
		response, _ = self.send()
		self.assertNotIn(str(CODE), str(response))

	def test_otp_whatsapp_enqueued_after_commit(self):
		"""QTE-26 (queue half): the OTP template message is a job queued after commit."""
		_, enqueue = self.send()
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.args[0], "quoteshop.quoteshop_enquiry.whatsapp.send_otp_message")
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
		self.assertEqual(enqueue.call_args.kwargs["mobile"], MOBILE)
		self.assertTrue(enqueue.call_args.kwargs["job_id"])

	def test_bare_ten_digits_get_plus91(self):
		self.send(mobile="98111 00001")
		self.assertIsNotNone(self.state("+919811100001"))

	def test_invalid_mobile_rejected(self):
		for mobile in ("", "12345", "+12", "abcdefghij", "+91981110000199999"):
			with self.subTest(mobile=mobile), self.assertRaises(frappe.ValidationError):
				self.send(mobile=mobile)

	def test_verify_happy_path_returns_token_for_mobile(self):
		self.send()
		result = self.verify(str(CODE))
		self.assertTrue(result["verified"])
		self.assertEqual(otp_service.verified_mobile(result["otp_token"]), MOBILE)

	def test_otp_single_use(self):
		"""QTE-07"""
		self.send()
		self.verify(str(CODE))
		with self.assertRaises(frappe.ValidationError):
			self.verify(str(CODE))

	def test_wrong_code_attempt_limit(self):
		"""QTE-08: 4 wrong codes still allow the right one; the 5th wrong burns the code."""
		self.send()
		for _ in range(4):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		self.assertEqual(self.state()["attempts"], 4)
		self.assertTrue(self.verify(str(CODE))["verified"])

		self.send(code=654321)
		for _ in range(5):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		self.assertIsNone(self.state())
		with self.assertRaises(frappe.ValidationError):
			self.verify("654321")

	def test_failures_counted_atomically_not_from_state(self):
		"""CONTRACTS §10: a racing writer resetting the stored attempts cannot buy extra guesses;
		the 5th failure burns the code."""
		self.send()
		for _ in range(2):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		state = self.state()
		state["attempts"] = 0  # what a parallel request holding a stale copy would write back
		frappe.cache.set_value(f"qs:otp:{MOBILE}", state, expires_in_sec=600)
		for _ in range(3):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		self.assertIsNone(self.state())  # burned at the 5th failure
		with self.assertRaises(frappe.ValidationError):
			self.verify(str(CODE))

	def test_new_code_gets_fresh_attempts(self):
		self.send(code=111111)
		for _ in range(4):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		self.send(code=222222)
		for _ in range(4):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000")
		self.assertTrue(self.verify("222222")["verified"])

	def test_malformed_code_counts_as_wrong(self):
		self.send()
		for otp in ("12345", "abcdef", "1234567", ""):
			with self.subTest(otp=otp), self.assertRaises(frappe.ValidationError):
				self.verify(otp)
		self.assertEqual(self.state()["attempts"], 4)

	def test_code_for_another_number_rejected(self):
		self.send()
		with self.assertRaises(frappe.ValidationError):
			self.verify(str(CODE), mobile="+919811100002")

	def test_otp_expires_after_ten_minutes(self):
		"""QTE-09: valid at 599 s, expired at exactly 600 s (expires_at, not the Redis TTL)."""
		start = now_datetime().replace(microsecond=0)
		with self.freeze_time(start):
			self.send()
		with self.freeze_time(add_to_date(start, seconds=599)):
			self.assertTrue(self.verify(str(CODE))["verified"])

		with self.freeze_time(start):
			self.send()
		with self.freeze_time(add_to_date(start, seconds=600)), self.assertRaises(frappe.ValidationError):
			self.verify(str(CODE))

	def test_otp_token_valid_for_thirty_minutes(self):
		start = now_datetime().replace(microsecond=0)
		with self.freeze_time(start):
			self.send()
			token = self.verify(str(CODE))["otp_token"]
		with self.freeze_time(add_to_date(start, seconds=1799)):
			self.assertEqual(otp_service.verified_mobile(token), MOBILE)
		with self.freeze_time(add_to_date(start, seconds=1800)):
			self.assertIsNone(otp_service.verified_mobile(token))

	def test_otp_token_stored_hashed(self):
		self.send()
		token = self.verify(str(CODE))["otp_token"]
		self.assertIsNone(frappe.cache.get_value(f"qs:otp-ok:{token}"))
		for bad in (None, "", "x" * 43, 123):
			self.assertIsNone(otp_service.verified_mobile(bad))

	def test_new_code_replaces_old(self):
		self.send(code=111111)
		self.send(code=222222)
		with self.assertRaises(frappe.ValidationError):
			self.verify("111111")
		self.assertTrue(self.verify("222222")["verified"])


class TestOTPRateLimits(OTPTestCase):
	def test_send_rate_limit_per_number(self):
		"""QTE-10: the 6th send for one number within the hour is refused, even from new IPs."""
		for i in range(5):
			self.send(ip=f"10.1.0.{i}")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.send(ip="10.1.0.99")
		self.send(mobile="+919811100002", ip="10.1.0.99")  # control: another number is fine

	def test_send_rate_limit_per_number_any_format(self):
		"""Formatting variants of one number share the per-number limit."""
		for mobile in ("+919811100001", "9811100001", "98111 00001", "+91 98111-00001", "(981) 1100001"):
			self.send(mobile=mobile, ip="10.2.0.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.send(mobile="+91-9811100001", ip="10.2.0.2")

	def test_send_rate_limit_per_ip(self):
		"""QTE-11: 20 sends per IP per hour across different numbers; the 21st is refused."""
		for i in range(20):
			self.send(mobile=f"+9198222{i:05d}", ip="10.3.0.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.send(mobile="+919833300000", ip="10.3.0.1")
		self.send(mobile="+919833300000", ip="10.3.0.2")  # control: another IP is fine

	def test_verify_rate_limited_per_ip(self):
		self.send()
		for i in range(30):  # distinct numbers: the per-number limit (10/h) must not trip first
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000", mobile=f"+9198111{i:05d}", ip="10.4.0.1")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.verify(str(CODE), ip="10.4.0.1")

	def test_verify_rate_limited_per_number(self):
		"""CONTRACTS §10: 10 verify calls per number per hour, whatever the IP."""
		self.send()
		for i in range(10):
			with self.assertRaises(frappe.ValidationError):
				self.verify("000000", mobile="+919811100008", ip=f"10.4.1.{i}")
		with self.assertRaises(frappe.RateLimitExceededError):
			self.verify("000000", mobile="+919811100008", ip="10.4.1.99")
		self.assertTrue(self.verify(str(CODE), ip="10.4.1.99")["verified"])  # control: other number

	def test_only_post_allowed(self):
		with self.assertRaises(frappe.PermissionError):
			call_api(SEND, http_method="GET", mobile=MOBILE)


class TestOTPNotConfigured(EnquiryTestCase):
	"""No otp_template / no WhatsApp Account."""

	def test_clear_error_without_whatsapp(self):
		with patch.dict(frappe.conf, {"developer_mode": 0}), patch("frappe.enqueue") as enqueue:
			with self.assertRaises(frappe.ValidationError) as ctx:
				call_api(SEND, mobile=MOBILE)
		self.assertIn("not configured", str(ctx.exception))
		enqueue.assert_not_called()

	def test_developer_mode_logs_code_never_returns_it(self):
		"""developer_mode without WhatsApp: the code goes to the `quoteshop` logger (any level), never to the client."""
		logger = frappe.logger("quoteshop")
		with (
			patch.dict(frappe.conf, {"developer_mode": 1}),
			patch("frappe.enqueue") as enqueue,
			patch.object(logger, "_log") as log,
			patch("frappe.logger", return_value=logger),
		):
			response = call_api(SEND, mobile=MOBILE)
		enqueue.assert_not_called()
		self.assertEqual(response, {"sent": True, "expires_in": 600})
		messages = [str(c.args[1]) % tuple(c.args[2]) if c.args[2] else str(c.args[1]) for c in log.call_args_list]
		logged = [m for m in messages if MOBILE in m and re.search(r"\b\d{6}\b", m)]
		self.assertEqual(len(logged), 1, messages)
		levels = [c.args[0] for c in log.call_args_list if MOBILE in str(c.args[1]) + str(c.args[2])]
		self.assertEqual(levels, [logging.WARNING])  # CONTRACTS §10: dev log level drops INFO
		code = re.search(r"\b(\d{6})\b", logged[0].replace(MOBILE, ""))[1]
		self.assertNotIn(code, str(response))
		self.assertTrue(call_api(VERIFY, mobile=MOBILE, otp=code)["verified"])
