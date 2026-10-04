import hashlib
import hmac
import secrets
from datetime import datetime

from frappe.utils import now_datetime


def new_token() -> tuple[str, str]:
	raw = secrets.token_urlsafe(32)
	return raw, hash_token(raw)


def hash_token(raw: str) -> str:
	return hashlib.sha256(raw.encode()).hexdigest()


def is_valid_token(raw: str | None, token_hash: str | None, expires: datetime | None) -> bool:
	if not raw or not token_hash:
		return False
	return hmac.compare_digest(hash_token(raw), token_hash) and (expires is None or now_datetime() < expires)
