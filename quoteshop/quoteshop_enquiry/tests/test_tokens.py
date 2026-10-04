"""CONTRACTS §5.5 / §6.3 - quote link tokens: random raw token, only the SHA-256 hex is stored."""

import hashlib
from datetime import datetime

from frappe.tests import UnitTestCase

from quoteshop.quoteshop_enquiry.tokens import hash_token, is_valid_token, new_token

NOW = "2026-06-15 12:00:00"
EXPIRES = datetime(2026, 6, 15, 12, 0, 0)


class TestQuoteToken(UnitTestCase):
	def test_new_token_returns_raw_and_sha256(self):
		raw, token_hash = new_token()
		self.assertIsInstance(raw, str)
		self.assertEqual(len(raw), 43)  # secrets.token_urlsafe(32)
		self.assertEqual(token_hash, hashlib.sha256(raw.encode()).hexdigest())

	def test_raw_never_equals_hash(self):
		raw, token_hash = new_token()
		self.assertNotEqual(raw, token_hash)
		self.assertNotIn(raw, token_hash)

	def test_tokens_random(self):
		self.assertEqual(len({new_token()[0] for _ in range(20)}), 20)

	def test_hash_token_deterministic(self):
		self.assertEqual(hash_token("abc"), hash_token("abc"))
		self.assertEqual(
			hash_token("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
		)
		self.assertNotEqual(hash_token("abc"), hash_token("abd"))

	def test_valid_token(self):
		raw, token_hash = new_token()
		with self.freeze_time("2026-06-15 11:59:59"):
			self.assertIs(is_valid_token(raw, token_hash, EXPIRES), True)

	def test_wrong_token_rejected(self):
		_, token_hash = new_token()
		other_raw, _ = new_token()
		with self.freeze_time("2026-06-15 11:00:00"):
			self.assertIs(is_valid_token(other_raw, token_hash, EXPIRES), False)
			self.assertIs(is_valid_token("", token_hash, EXPIRES), False)
			# the stored hash itself is not a valid token
			self.assertIs(is_valid_token(token_hash, token_hash, EXPIRES), False)

	def test_expired_token_rejected(self):
		raw, token_hash = new_token()
		with self.freeze_time("2026-06-15 12:00:01"):
			self.assertIs(is_valid_token(raw, token_hash, EXPIRES), False)

	def test_token_invalid_at_exact_expiry(self):
		raw, token_hash = new_token()
		with self.freeze_time(NOW):  # now == expires → not < expires
			self.assertIs(is_valid_token(raw, token_hash, EXPIRES), False)

	def test_none_expiry_never_expires(self):
		raw, token_hash = new_token()
		with self.freeze_time("2099-01-01 00:00:00"):
			self.assertIs(is_valid_token(raw, token_hash, None), True)
			self.assertIs(is_valid_token("wrong", token_hash, None), False)

	# Trust boundary (§6.3): empty/None raw or token_hash -> False, never raises.

	def test_none_raw_rejected(self):
		_, token_hash = new_token()
		self.assertIs(is_valid_token(None, token_hash, None), False)
		self.assertIs(is_valid_token(None, None, None), False)

	def test_empty_raw_rejected_even_if_hash_matches(self):
		# a stored sha256("") must never let an empty token through
		self.assertIs(is_valid_token("", hash_token(""), None), False)

	def test_none_hash_rejected(self):
		raw, _ = new_token()
		self.assertIs(is_valid_token(raw, None, None), False)

	def test_empty_hash_rejected(self):
		raw, _ = new_token()
		self.assertIs(is_valid_token(raw, "", None), False)
		self.assertIs(is_valid_token("", "", None), False)
