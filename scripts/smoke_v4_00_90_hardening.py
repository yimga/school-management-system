"""v4.00.90 Wave 22 — OAuth live-path hardening (RFC-6749 + Retry-After +
token expiry) for Schoology + D2L. Builds on v4.00.89 deferral closure.

Three new capabilities exercised:
  T1: ``decode_oauth2_error_response`` — RFC-6749 § 5.2 taxonomy
  T2: ``parse_retry_after`` — RFC-7231 § 7.1.3 (delta-sec + HTTP-date)
  T3: ``is_token_expired`` — issued_at + safety window
  T4: 429 with Retry-After header retried by both connectors
  T5: 4xx upstream error decoded into oauth_error_code field
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import django  # noqa: E402

django.setup()

import datetime as _dt  # noqa: E402

import requests  # noqa: E402

from apps.integrations_marketplace import lms_connector_d2l as _d2l  # noqa: E402
from apps.integrations_marketplace import lms_connector_schoology as _sg  # noqa: E402
from apps.integrations_marketplace import oauth_live_path_helpers as _h  # noqa: E402

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


class _FakeResp:
    def __init__(self, status_code: int, body=None, headers: dict | None = None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


# ---------------------------------------------------------------------------
# T1 — RFC-6749 § 5.2 error response decoder
# ---------------------------------------------------------------------------
print("=" * 70)
print("T1 RFC-6749 error decoder")
print("=" * 70)

# T1-1: invalid_grant standard code
r = _h.decode_oauth2_error_response({"error": "invalid_grant",
                                     "error_description": "Code expired"})
assert r["error_code"] == "invalid_grant"
assert r["error_description"] == "Code expired"
_ok("invalid_grant standard code decoded")

# T1-2: invalid_client standard code
r = _h.decode_oauth2_error_response({"error": "invalid_client"})
assert r["error_code"] == "invalid_client"
_ok("invalid_client standard code decoded")

# T1-3: unknown vendor extension folds to upstream_error_unknown
r = _h.decode_oauth2_error_response({"error": "vendor_proprietary_thing"})
assert r["error_code"] == "upstream_error_unknown"
assert r["raw_error"] == "vendor_proprietary_thing"
_ok("vendor extension folds to upstream_error_unknown w/ raw_error preserved")

# T1-4: non-dict body (text/plain or text/html) returns safe defaults
r = _h.decode_oauth2_error_response("<html>Forbidden</html>")
assert r["error_code"] == "upstream_error_unknown"
assert "Forbidden" in r["raw_error"]
_ok("non-dict body folds safely with raw_error captured")

# T1-5: None body returns clean defaults
r = _h.decode_oauth2_error_response(None)
assert r["error_code"] == "upstream_error_unknown"
assert r["raw_error"] == ""
_ok("None body returns clean defaults")

# T1-6: error_description control-char stripping + 256 cap
long_desc = "a" * 500 + "\x00\x01\x02"
r = _h.decode_oauth2_error_response({"error": "invalid_grant",
                                     "error_description": long_desc})
assert len(r["error_description"]) <= 256
assert "\x00" not in r["error_description"]
_ok("error_description truncated + control-chars stripped")

# T1-7: has_error_uri surfaced
r = _h.decode_oauth2_error_response({"error": "invalid_grant",
                                     "error_uri": "https://docs.example.com/x"})
assert r["has_error_uri"] is True
_ok("has_error_uri surfaced when error_uri present")

# T1-8: case-insensitive + space-folding for error code
r = _h.decode_oauth2_error_response({"error": "Invalid Grant"})
assert r["error_code"] == "invalid_grant"
_ok("error code normalized case-insensitive + space-folded")


# ---------------------------------------------------------------------------
# T2 — Retry-After parser
# ---------------------------------------------------------------------------
print("=" * 70)
print("T2 Retry-After parser")
print("=" * 70)

# T2-1: delta-seconds integer
assert _h.parse_retry_after("120") == 120.0
_ok("delta-seconds '120' -> 120.0")

# T2-2: delta-seconds decimal (some upstreams send float)
assert _h.parse_retry_after("30.5") == 30.5
_ok("delta-seconds '30.5' -> 30.5")

# T2-3: HTTP-date in the future
future = _dt.datetime(2026, 5, 30, 13, 0, 0, tzinfo=_dt.timezone.utc)
now_fixed = _dt.datetime(2026, 5, 30, 12, 0, 0, tzinfo=_dt.timezone.utc)
http_date = "Sat, 30 May 2026 13:00:00 GMT"
parsed = _h.parse_retry_after(http_date, now=now_fixed)
assert 3590 <= parsed <= 3610, f"expected ~3600s, got {parsed}"
_ok(f"HTTP-date '{http_date}' -> ~3600s")

# T2-4: HTTP-date in the past clamped to 0
past_date = "Sat, 30 May 2026 11:00:00 GMT"
parsed = _h.parse_retry_after(past_date, now=now_fixed)
assert parsed == 0.0
_ok("HTTP-date in past clamped to 0")

# T2-5: empty / None returns None
assert _h.parse_retry_after("") is None
assert _h.parse_retry_after(None) is None
_ok("empty/None returns None")

# T2-6: malformed returns None
assert _h.parse_retry_after("not a date or number") is None
_ok("malformed input returns None")

# T2-7: negative delta clamped to 0
assert _h.parse_retry_after("-10") == 0.0
_ok("negative delta clamped to 0")


# ---------------------------------------------------------------------------
# T3 — Token expiry helper
# ---------------------------------------------------------------------------
print("=" * 70)
print("T3 is_token_expired")
print("=" * 70)

now_fixed = _dt.datetime(2026, 5, 30, 12, 0, 0, tzinfo=_dt.timezone.utc)
issued = "2026-05-30T11:00:00+00:00"

# T3-1: fresh token, plenty of life, returns False
assert _h.is_token_expired(issued_at_iso=issued,
                           expires_in_seconds=7200,
                           safety_window_seconds=60,
                           now=now_fixed) is False
_ok("fresh token (1h elapsed of 2h life) -> not expired")

# T3-2: token within safety window returns True
assert _h.is_token_expired(issued_at_iso=issued,
                           expires_in_seconds=3600,
                           safety_window_seconds=60,
                           now=now_fixed) is True  # elapsed == expires_in
_ok("token at 60s-before-expiry safety window -> expired (refresh now)")

# T3-3: long-expired token returns True
old = "2026-05-30T10:00:00+00:00"
assert _h.is_token_expired(issued_at_iso=old,
                           expires_in_seconds=3600,
                           safety_window_seconds=60,
                           now=now_fixed) is True
_ok("2h-old token w/ 1h life -> expired")

# T3-4: missing issued_at returns True (safer)
assert _h.is_token_expired(issued_at_iso="",
                           expires_in_seconds=3600) is True
_ok("missing issued_at_iso -> treated as expired (safe default)")

# T3-5: malformed issued_at returns True
assert _h.is_token_expired(issued_at_iso="not-an-iso-date",
                           expires_in_seconds=3600) is True
_ok("malformed issued_at_iso -> treated as expired")

# T3-6: zero/negative expires_in returns True
assert _h.is_token_expired(issued_at_iso=issued, expires_in_seconds=0) is True
assert _h.is_token_expired(issued_at_iso=issued, expires_in_seconds=-100) is True
_ok("expires_in_seconds <= 0 -> treated as expired")

# T3-7: 'Z'-suffix ISO (common upstream format) works
issued_z = "2026-05-30T11:00:00Z"
assert _h.is_token_expired(issued_at_iso=issued_z,
                           expires_in_seconds=7200,
                           safety_window_seconds=60,
                           now=now_fixed) is False
_ok("Z-suffix ISO timestamp parsed correctly")


# ---------------------------------------------------------------------------
# T4 — 429 with Retry-After retried by Schoology + D2L
# ---------------------------------------------------------------------------
print("=" * 70)
print("T4 429 Retry-After retry behavior")
print("=" * 70)


def _no_sleep(mod):
    orig = mod._time

    class _NS:
        @staticmethod
        def sleep(x):
            return None

    mod._time = _NS()
    return orig


# T4-1: Schoology retries on 429 with Retry-After header
sg_attempts = [0]
def _sg_429_then_ok():
    sg_attempts[0] += 1
    if sg_attempts[0] == 1:
        return _FakeResp(429, {}, {"Retry-After": "5"})
    return _FakeResp(200, {"ok": "yes"})


orig_sg_time = _no_sleep(_sg)
try:
    r = _sg._retry_with_backoff(_sg_429_then_ok, max_attempts=3, base_delay=0.001)
    assert r.status_code == 200
    assert sg_attempts[0] == 2, f"expected 2 attempts, got {sg_attempts[0]}"
    _ok("Schoology retries 429 w/ Retry-After header")
finally:
    _sg._time = orig_sg_time

# T4-2: Schoology does NOT retry 429 without Retry-After header
sg_attempts = [0]
def _sg_429_no_header():
    sg_attempts[0] += 1
    return _FakeResp(429, {}, {})  # no Retry-After


orig_sg_time = _no_sleep(_sg)
try:
    r = _sg._retry_with_backoff(_sg_429_no_header, max_attempts=3, base_delay=0.001)
    assert r.status_code == 429
    assert sg_attempts[0] == 1, "should not retry 429 w/o Retry-After"
    _ok("Schoology does NOT retry 429 w/o Retry-After header")
finally:
    _sg._time = orig_sg_time

# T4-3: D2L retries on 429 with Retry-After
d2l_attempts = [0]
def _d2l_429_then_ok():
    d2l_attempts[0] += 1
    if d2l_attempts[0] == 1:
        return _FakeResp(429, {}, {"Retry-After": "2"})
    return _FakeResp(200, {})


orig_d2l_time = _no_sleep(_d2l)
try:
    r = _d2l._retry_with_backoff(_d2l_429_then_ok, max_attempts=3, base_delay=0.001)
    assert r.status_code == 200
    assert d2l_attempts[0] == 2
    _ok("D2L retries 429 w/ Retry-After header")
finally:
    _d2l._time = orig_d2l_time

# T4-4: D2L does NOT retry 429 without Retry-After
d2l_attempts = [0]
def _d2l_429_no_header():
    d2l_attempts[0] += 1
    return _FakeResp(429, {}, {})


orig_d2l_time = _no_sleep(_d2l)
try:
    r = _d2l._retry_with_backoff(_d2l_429_no_header, max_attempts=3, base_delay=0.001)
    assert r.status_code == 429
    assert d2l_attempts[0] == 1
    _ok("D2L does NOT retry 429 w/o Retry-After header")
finally:
    _d2l._time = orig_d2l_time


# ---------------------------------------------------------------------------
# T5 — 4xx upstream error decoded into oauth_error_code field
# ---------------------------------------------------------------------------
print("=" * 70)
print("T5 RFC-6749 error decoded into structured response")
print("=" * 70)

# T5-1: Schoology exchange w/ 400 + invalid_grant body -> oauth_error_code surfaces
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
orig_post = requests.post

def _sg_invalid_grant(url, **kw):
    return _FakeResp(400, {"error": "invalid_grant",
                           "error_description": "Authorization code expired"})


requests.post = _sg_invalid_grant
orig_audit = _sg._record_audit
audit_bucket = []
_sg._record_audit = lambda **kw: audit_bucket.append(kw)
try:
    r = _sg.exchange_authorization_code_for_token(
        code="bad-code", client_id="cid", client_secret="cs",
        redirect_uri="https://x/cb",
    )
    assert r["ok"] is False
    assert r["reason"] == "upstream_error"
    assert r["http_status"] == 400
    assert r["oauth_error_code"] == "invalid_grant"
    assert r["oauth_error_description"] == "Authorization code expired"
    # Audit payload should have oauth_error_code (not the description, to
    # keep audit rows compact).
    assert audit_bucket[0]["payload_summary"]["oauth_error_code"] == "invalid_grant"
    _ok("Schoology 400 + invalid_grant -> oauth_error_code=invalid_grant in result + audit")
finally:
    requests.post = orig_post
    _sg._record_audit = orig_audit
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

# T5-2: D2L refresh w/ 401 + invalid_client body -> oauth_error_code surfaces
os.environ["RMC_D2L_OAUTH_LIVE_OUTBOUND"] = "1"
orig_post = requests.post

def _d2l_invalid_client(url, **kw):
    return _FakeResp(401, {"error": "invalid_client"})


requests.post = _d2l_invalid_client
orig_audit = _d2l._record_audit
audit_bucket = []
_d2l._record_audit = lambda **kw: audit_bucket.append(kw)
try:
    r = _d2l.refresh_access_token(
        refresh_token="rt", client_id="cid", client_secret="cs",
    )
    assert r["ok"] is False
    assert r["http_status"] == 401
    assert r["oauth_error_code"] == "invalid_client"
    assert audit_bucket[0]["payload_summary"]["oauth_error_code"] == "invalid_client"
    _ok("D2L refresh 401 + invalid_client -> oauth_error_code=invalid_client in result + audit")
finally:
    requests.post = orig_post
    _d2l._record_audit = orig_audit
    os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)

# T5-3: Schoology exchange success now carries issued_at_iso
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
orig_post = requests.post

def _sg_ok(url, **kw):
    return _FakeResp(200, {"access_token": "at", "refresh_token": "rt",
                           "expires_in": 3600, "token_type": "Bearer"})


requests.post = _sg_ok
orig_audit = _sg._record_audit
_sg._record_audit = lambda **kw: None
try:
    r = _sg.exchange_authorization_code_for_token(
        code="ok-code", client_id="cid", client_secret="cs",
        redirect_uri="https://x/cb",
    )
    assert r["ok"] is True
    assert "issued_at_iso" in r
    assert r["issued_at_iso"].startswith("2026")
    _ok("Schoology exchange success carries issued_at_iso ISO-8601")
finally:
    requests.post = orig_post
    _sg._record_audit = orig_audit
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

# T5-4: D2L refresh success carries issued_at_iso
os.environ["RMC_D2L_OAUTH_LIVE_OUTBOUND"] = "1"
orig_post = requests.post

def _d2l_ok(url, **kw):
    return _FakeResp(200, {"access_token": "at", "refresh_token": "rt",
                           "expires_in": 3600, "token_type": "Bearer"})


requests.post = _d2l_ok
orig_audit = _d2l._record_audit
_d2l._record_audit = lambda **kw: None
try:
    r = _d2l.refresh_access_token(
        refresh_token="rt", client_id="cid", client_secret="cs",
    )
    assert r["ok"] is True
    assert "issued_at_iso" in r
    _ok("D2L refresh success carries issued_at_iso ISO-8601")
finally:
    requests.post = orig_post
    _d2l._record_audit = orig_audit
    os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)


print("=" * 70)
print(f"v4.00.90 Wave 22 hardening — {CASES} CASES OK")
print("=" * 70)
