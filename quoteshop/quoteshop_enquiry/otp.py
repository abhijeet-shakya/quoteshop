"""WhatsApp OTP: 6 digits, SHA-256 in Redis, 10-minute TTL (CONTRACTS §5.5, §7.2)."""

import re
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from quoteshop.quoteshop_enquiry.tokens import hash_token, new_token

OTP_TTL = 600
OTP_OK_TTL = 1800
MAX_ATTEMPTS = 5
SENDS_PER_HOUR = 5


def normalize_mobile(mobile: str | None) -> str:
	"""E.164 with leading "+"; a bare 10-digit number gets "+91". Raises on anything else."""
	value = re.sub(r"[\s\-().]", "", str(mobile or ""))
	if re.fullmatch(r"\d{10}", value):
		value = "+91" + value
	if not re.fullmatch(r"\+\d{8,15}", value):
		frappe.throw(_("Enter a valid mobile number with country code."), frappe.ValidationError)
	return value


def issue(mobile: str) -> None:
	"""Create a code for `mobile` and send it on WhatsApp (enqueued)."""
	from quoteshop.quoteshop_enquiry import whatsapp

	# per normalised number: the decorator key is the raw form value, which formatting can vary
	_count_or_throw(f"qs:otp-sends:{mobile}", SENDS_PER_HOUR, 3600)
	can_send = whatsapp.can_send("otp")
	if not can_send and not frappe.conf.developer_mode:
		frappe.throw(_("Verification by WhatsApp is not configured. Please contact us."))

	code = f"{secrets.randbelow(10**6):06d}"
	frappe.cache.set_value(
		_key(mobile),
		{
			"hash": _hash(mobile, code),
			"expires_at": str(add_to_date(now_datetime(), seconds=OTP_TTL)),
			"attempts": 0,
		},
		expires_in_sec=OTP_TTL,
	)
	if can_send:
		whatsapp.queue_otp(mobile, code)
	else:
		frappe.logger("quoteshop").info(
			f"QS OTP for {mobile}: {code} (developer_mode, WhatsApp not configured)"
		)


def verify(mobile: str, code: str) -> str:
	"""Check `code`; on success return an otp_token proving `mobile` for 30 minutes."""
	key = _key(mobile)
	state = frappe.cache.get_value(key, expires=True)
	if not state or now_datetime() >= get_datetime(state["expires_at"]):
		frappe.cache.delete_value(key)
		frappe.throw(_("The code has expired. Please request a new one."))

	if not re.fullmatch(r"\d{6}", str(code or "")) or not secrets.compare_digest(
		_hash(mobile, str(code)), state["hash"]
	):
		state["attempts"] += 1
		if state["attempts"] >= MAX_ATTEMPTS:
			frappe.cache.delete_value(key)
			frappe.throw(_("Too many wrong attempts. Please request a new code."))
		frappe.cache.set_value(key, state, expires_in_sec=OTP_TTL)
		frappe.throw(_("Wrong code. Please try again."))

	frappe.cache.delete_value(key)
	raw, token_hash = new_token()
	frappe.cache.set_value(
		f"qs:otp-ok:{token_hash}",
		{"mobile": mobile, "expires_at": str(add_to_date(now_datetime(), seconds=OTP_OK_TTL))},
		expires_in_sec=OTP_OK_TTL,
	)
	return raw


def verified_mobile(otp_token: str | None) -> str | None:
	"""Mobile proven by `otp_token`, or None."""
	if not otp_token or not isinstance(otp_token, str):
		return None
	state = frappe.cache.get_value(f"qs:otp-ok:{hash_token(otp_token)}", expires=True)
	if not state or now_datetime() >= get_datetime(state["expires_at"]):
		return None
	return state["mobile"]


def _key(mobile: str) -> str:
	return f"qs:otp:{mobile}"


def _hash(mobile: str, code: str) -> str:
	return hash_token(f"{mobile}:{code}")


def _count_or_throw(key: str, limit: int, seconds: int) -> None:
	# ponytail: fixed window via INCR + EXPIRE on first hit, same model as frappe.rate_limiter
	key = frappe.cache.make_key(key)
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, seconds)
	if count > limit:
		frappe.throw(_("Too many codes requested. Please try again later."), frappe.RateLimitExceededError)
