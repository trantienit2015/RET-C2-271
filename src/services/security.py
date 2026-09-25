"""S-2 deterministic credential/PII scanner + S-1 input sanitizer for RET-C2-271.

Pure, stateless domain helpers (NOT framework gate methods). The credential/PII
scan is a static regex check, not an LLM judgment.
"""

from __future__ import annotations

import re

_HTML_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_MAX_LENGTH = 8000

# Bearer/JWT, credential JSON fields, My Number (12-digit), email, phone.
_BEARER_JWT_RE = re.compile(r"(Bearer\s+[A-Za-z0-9._-]{10,}|eyJ[A-Za-z0-9._-]{10,})")
_CRED_FIELD_RE = re.compile(r'"(?:password|credential|client_secret|api_key|access_token)"\s*:', re.IGNORECASE)
_MYNUMBER_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)0\d{1,3}-?\d{2,4}-?\d{4}(?!\d)")


def sanitize_query(query: str, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """Strip HTML tags (injection/markup guard) and cap length."""
    return _HTML_TAG_RE.sub("", query)[:max_length]


def scan_for_sensitive(payload: str) -> str | None:
    """Return a violation reason if payload embeds a credential/PII, else None."""
    if not payload:
        return None
    if _BEARER_JWT_RE.search(payload):
        return "embedded bearer token / JWT detected in content metadata"
    if _CRED_FIELD_RE.search(payload):
        return "embedded credential field detected in content metadata"
    if _MYNUMBER_RE.search(payload):
        return "embedded My Number (12-digit) pattern detected in content metadata"
    if _EMAIL_RE.search(payload):
        return "embedded email address detected in content metadata"
    if _PHONE_RE.search(payload):
        return "embedded phone number detected in content metadata"
    return None
