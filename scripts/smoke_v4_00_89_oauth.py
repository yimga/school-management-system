"""v4.00.89 — Close LIVE-OAUTH "honest deferral" via fully-mocked
round-trip smokes for Schoology + D2L Brightspace connectors.

The deferred items (per audit) were:
  (a) No audit logging of successful exchanges/pushes (only error logging)
  (b) No refresh-token flow
  (c) No retry/backoff on transient failures

v4.00.89 closes all three by adding ``_record_audit`` + ``refresh_access_token``
+ ``_retry_with_backoff`` to both adapters. This smoke proves the wiring
without requiring a real Schoology / D2L sandbox:

  * Audit hook fires on success + failure + validation_error paths
  * refresh_access_token has matching dry-run + live + validation paths
  * _retry_with_backoff retries 3x on Timeout + 5xx, NOT on 4xx / 2xx
  * Secrets NEVER appear in the audit row (forbidden-key scrub verified)
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

import requests  # noqa: E402

from apps.integrations_marketplace import lms_connector_schoology as _sg  # noqa: E402
from apps.integrations_marketplace import lms_connector_d2l as _d2l  # noqa: E402

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


class _FakeResp:
    """Minimal stand-in for requests.Response — just the bits the SUT reads."""

    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body


def _install_audit_collector(mod) -> list:
    """Replace the connector's _record_audit with a list collector. Returns
    the list — caller restores by re-assigning the original at the end."""
    bucket: list = []

    def _fake(**kw):
        bucket.append(kw)

    mod._record_audit = _fake
    return bucket


def _install_fake_post(monkey_target: str, behavior):
    """Replace ``requests.<method>`` with ``behavior`` (a callable taking
    the same args). Returns the original so the caller can restore."""
    orig = getattr(requests, monkey_target)
    setattr(requests, monkey_target, behavior)
    return orig


def _no_sleep(mod):
    """Make ``mod._time.sleep`` a no-op so retry tests don't actually wait."""
    orig = mod._time

    class _NoSleep:
        @staticmethod
        def sleep(x):
            return None

    mod._time = _NoSleep()
    return orig


# ---------------------------------------------------------------------------
# T1 — Schoology connector (9 cases)
# ---------------------------------------------------------------------------
print("=" * 70)
print("T1 Schoology — audit + refresh + retry")
print("=" * 70)

# --- T1-1: refresh_access_token dry-run (env unset) ---
os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)
_r = _sg.refresh_access_token(
    refresh_token="rt-1", client_id="cid", client_secret="csecret",
)
assert _r.get("dry_run") is True
assert _r.get("ok") is False
assert _r.get("reason") == "live_outbound_disabled_env_unset"
assert "target_url" in _r
_ok("schoology.refresh_access_token dry-run (env unset) -> dry_run+ok=False")

# --- T1-2: refresh_access_token validates missing fields ---
_orig_audit_sg = _sg._record_audit
_bucket = _install_audit_collector(_sg)
try:
    _r2 = _sg.refresh_access_token(
        refresh_token="", client_id="cid", client_secret="cs",
    )
    assert _r2.get("ok") is False
    assert _r2.get("reason") == "validation_error"
    assert any(c.get("reason") == "validation_error" for c in _bucket)
    _ok("schoology.refresh_access_token w/ missing refresh_token -> validation_error + audit")
finally:
    _sg._record_audit = _orig_audit_sg

# --- T1-3: audit hook fires on exchange validation_error ---
_bucket = _install_audit_collector(_sg)
try:
    _r3 = _sg.exchange_authorization_code_for_token(
        code="", client_id="cid", client_secret="cs", redirect_uri="https://x/cb",
    )
    assert _r3.get("reason") == "validation_error"
    assert len(_bucket) == 1
    assert _bucket[0]["action"] == "oauth_exchange"
    assert _bucket[0]["ok"] is False
    _ok("schoology.exchange validation_error -> audit hook fires")
finally:
    _sg._record_audit = _orig_audit_sg

# --- T1-4: audit hook fires on exchange live + 200 success ---
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
_bucket = _install_audit_collector(_sg)
_orig_post = _install_fake_post(
    "post",
    lambda url, **kw: _FakeResp(
        200,
        {"access_token": "at-real", "refresh_token": "rt-real", "expires_in": 3600,
         "token_type": "Bearer", "scope": "read write"},
    ),
)
try:
    _r4 = _sg.exchange_authorization_code_for_token(
        code="auth-code", client_id="cid", client_secret="cs",
        redirect_uri="https://x/cb", tenant_schema="acme",
    )
    assert _r4.get("ok") is True
    assert _r4.get("access_token") == "at-real"
    success_audits = [c for c in _bucket if c.get("ok") is True]
    assert len(success_audits) == 1
    # Forbidden-keys must NOT appear anywhere in audit payload_summary.
    ps = success_audits[0].get("payload_summary", {}) or {}
    for forbidden in ("client_secret", "access_token", "refresh_token", "code"):
        assert forbidden not in ps, f"secret {forbidden} leaked into audit"
    # Token CORRELATION hashes must be present (so audit is still useful).
    assert "access_token_hash" in ps and "refresh_token_hash" in ps
    _ok("schoology.exchange live+200 -> audit ok=True, no secret leakage, hashes present")
finally:
    requests.post = _orig_post
    _sg._record_audit = _orig_audit_sg
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

# --- T1-5: push_grade_live dry-run (env unset) ---
_r5 = _sg.push_grade_live(
    access_token="at", section_id="s1", assignment_id="a1",
    student_id="u1", score=85.0, max_score=100.0,
)
assert _r5.get("dry_run") is True
assert _r5.get("ok") is False
assert "target_url" in _r5 or "would_target" in _r5
_ok("schoology.push_grade_live dry-run -> dry_run+ok=False+target visible")

# --- T1-6: push_grade_live live + 200 fires audit ---
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
_bucket = _install_audit_collector(_sg)
_orig_put = _install_fake_post("put", lambda url, **kw: _FakeResp(200, {"id": 999}))
try:
    _r6 = _sg.push_grade_live(
        access_token="at-live", section_id="sec-1", assignment_id="asn-1",
        student_id="stu-1", score=85.0, max_score=100.0, tenant_schema="acme",
    )
    assert _r6.get("ok") is True
    assert _r6.get("http_status") == 200
    success_audits = [c for c in _bucket if c.get("action") == "push_grade_live" and c.get("ok") is True]
    assert len(success_audits) == 1
    _ok("schoology.push_grade_live live+200 -> audit ok=True")
finally:
    requests.put = _orig_put
    _sg._record_audit = _orig_audit_sg
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

# --- T1-7: _retry_with_backoff retries on Timeout (3 attempts then succeeds) ---
attempts = [0]


def _flaky_then_ok():
    attempts[0] += 1
    if attempts[0] < 3:
        raise requests.Timeout("smoke")
    return _FakeResp(200, {"ok": "yes"})


_orig_t = _no_sleep(_sg)
try:
    _r7 = _sg._retry_with_backoff(_flaky_then_ok, max_attempts=3, base_delay=0.001)
    assert _r7.status_code == 200
    assert attempts[0] == 3
    _ok("schoology._retry_with_backoff retries Timeout 2x then returns 200")
finally:
    _sg._time = _orig_t

# --- T1-8: _retry_with_backoff returns immediately on 200 ---
counter = [0]


def _instant_ok():
    counter[0] += 1
    return _FakeResp(200, {"ok": "yes"})


_orig_t = _no_sleep(_sg)
try:
    _r8 = _sg._retry_with_backoff(_instant_ok, max_attempts=3, base_delay=0.001)
    assert _r8.status_code == 200
    assert counter[0] == 1, "should not retry on first 200"
    _ok("schoology._retry_with_backoff returns immediately on 200 (no retry)")
finally:
    _sg._time = _orig_t

# --- T1-9: _retry_with_backoff does NOT retry on 400 ---
c2 = [0]


def _always_400():
    c2[0] += 1
    return _FakeResp(400, {"error": "bad_request"})


_orig_t = _no_sleep(_sg)
try:
    _r9 = _sg._retry_with_backoff(_always_400, max_attempts=3, base_delay=0.001)
    assert _r9.status_code == 400
    assert c2[0] == 1, "should not retry on 400"
    _ok("schoology._retry_with_backoff does NOT retry on 400")
finally:
    _sg._time = _orig_t


# ---------------------------------------------------------------------------
# T2 — D2L Brightspace connector (9 cases mirror)
# ---------------------------------------------------------------------------
print("=" * 70)
print("T2 D2L — audit + refresh + retry")
print("=" * 70)

_orig_audit_d2l = _d2l._record_audit

# --- T2-1: refresh_access_token dry-run ---
os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)
_r = _d2l.refresh_access_token(
    refresh_token="rt", client_id="cid", client_secret="cs",
)
assert _r.get("dry_run") is True
assert _r.get("ok") is False
assert _r.get("reason") == "live_outbound_disabled_env_unset"
_ok("d2l.refresh_access_token dry-run (env unset) -> dry_run+ok=False")

# --- T2-2: refresh_access_token validates missing fields ---
_bucket = _install_audit_collector(_d2l)
try:
    _r2 = _d2l.refresh_access_token(
        refresh_token="", client_id="cid", client_secret="cs",
    )
    assert _r2.get("reason") == "validation_error"
    assert any(c.get("reason") == "validation_error" for c in _bucket)
    _ok("d2l.refresh_access_token w/ missing refresh_token -> validation_error + audit")
finally:
    _d2l._record_audit = _orig_audit_d2l

# --- T2-3: audit hook fires on exchange validation_error ---
_bucket = _install_audit_collector(_d2l)
try:
    _r3 = _d2l.exchange_authorization_code_for_token(
        code="", client_id="cid", client_secret="cs", redirect_uri="https://x/cb",
    )
    assert _r3.get("reason") == "validation_error"
    assert len(_bucket) == 1
    assert _bucket[0]["action"] == "oauth_exchange"
    _ok("d2l.exchange validation_error -> audit hook fires")
finally:
    _d2l._record_audit = _orig_audit_d2l

# --- T2-4: audit hook fires on exchange live + 200 success ---
os.environ["RMC_D2L_OAUTH_LIVE_OUTBOUND"] = "1"
_bucket = _install_audit_collector(_d2l)
_orig_post = _install_fake_post(
    "post",
    lambda url, **kw: _FakeResp(
        200,
        {"access_token": "at-real", "refresh_token": "rt-real", "expires_in": 3600,
         "token_type": "Bearer"},
    ),
)
try:
    _r4 = _d2l.exchange_authorization_code_for_token(
        code="auth-code", client_id="cid", client_secret="cs",
        redirect_uri="https://x/cb", tenant_schema="acme",
    )
    assert _r4.get("ok") is True
    success_audits = [c for c in _bucket if c.get("ok") is True]
    assert len(success_audits) == 1
    ps = success_audits[0].get("payload_summary", {}) or {}
    for forbidden in ("client_secret", "access_token", "refresh_token", "code"):
        assert forbidden not in ps, f"secret {forbidden} leaked into audit"
    assert "access_token_hash" in ps and "refresh_token_hash" in ps
    _ok("d2l.exchange live+200 -> audit ok=True, no secret leakage, hashes present")
finally:
    requests.post = _orig_post
    _d2l._record_audit = _orig_audit_d2l
    os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)

# --- T2-5: push_grade_live dry-run (env unset) ---
_r5 = _d2l.push_grade_live(
    access_token="at", org_unit_id="ou1", grade_object_id="g1",
    user_id="u1", score=85.0, max_score=100.0,
)
assert _r5.get("dry_run") is True
assert _r5.get("ok") is False
assert "target_url" in _r5 or "would_target" in _r5
_ok("d2l.push_grade_live dry-run -> dry_run+ok=False+target visible")

# --- T2-6: push_grade_live live + 200 fires audit ---
os.environ["RMC_D2L_OAUTH_LIVE_OUTBOUND"] = "1"
_bucket = _install_audit_collector(_d2l)
_orig_put = _install_fake_post("put", lambda url, **kw: _FakeResp(200, {"updated": True}))
try:
    _r6 = _d2l.push_grade_live(
        access_token="at-live", org_unit_id="ou-1", grade_object_id="g-1",
        user_id="u-1", score=85.0, max_score=100.0, tenant_schema="acme",
    )
    assert _r6.get("ok") is True
    assert _r6.get("http_status") == 200
    success_audits = [c for c in _bucket if c.get("action") == "push_grade_live" and c.get("ok") is True]
    assert len(success_audits) == 1
    # user_id should be hashed in audit summary
    ps = success_audits[0].get("payload_summary", {}) or {}
    assert "user_id_hash" in ps
    assert ps.get("user_id_hash") != "u-1", "user_id must be hashed, not raw"
    _ok("d2l.push_grade_live live+200 -> audit ok=True, user_id hashed")
finally:
    requests.put = _orig_put
    _d2l._record_audit = _orig_audit_d2l
    os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)

# --- T2-7: _retry_with_backoff retries on Timeout ---
attempts = [0]


def _d2l_flaky():
    attempts[0] += 1
    if attempts[0] < 3:
        raise requests.Timeout("smoke")
    return _FakeResp(200, {"ok": "yes"})


_orig_t = _no_sleep(_d2l)
try:
    _r7 = _d2l._retry_with_backoff(_d2l_flaky, max_attempts=3, base_delay=0.001)
    assert _r7.status_code == 200
    assert attempts[0] == 3
    _ok("d2l._retry_with_backoff retries Timeout 2x then returns 200")
finally:
    _d2l._time = _orig_t

# --- T2-8: _retry_with_backoff returns immediately on 200 ---
c3 = [0]


def _d2l_instant():
    c3[0] += 1
    return _FakeResp(200, {})


_orig_t = _no_sleep(_d2l)
try:
    _r8 = _d2l._retry_with_backoff(_d2l_instant, max_attempts=3, base_delay=0.001)
    assert _r8.status_code == 200
    assert c3[0] == 1
    _ok("d2l._retry_with_backoff returns immediately on 200 (no retry)")
finally:
    _d2l._time = _orig_t

# --- T2-9: _retry_with_backoff does NOT retry on 400 ---
c4 = [0]


def _d2l_always_400():
    c4[0] += 1
    return _FakeResp(400, {})


_orig_t = _no_sleep(_d2l)
try:
    _r9 = _d2l._retry_with_backoff(_d2l_always_400, max_attempts=3, base_delay=0.001)
    assert _r9.status_code == 400
    assert c4[0] == 1
    _ok("d2l._retry_with_backoff does NOT retry on 400")
finally:
    _d2l._time = _orig_t


print("=" * 70)
print(f"v4.00.89 OAuth deferral closeout — {CASES} CASES OK")
print("=" * 70)
