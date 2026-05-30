"""v4.00.91 Wave 24 — OAuth security hardening (RFC-6749 § 10.4 + § 3.3 +
redirect_uri post-exchange validation) for Schoology + D2L.

Three new defenses exercised:
  H1: Refresh-token rotation tracking via per-provider ring buffer.
      * Issuance recorded (hash only).
      * Rotation detected when upstream returns a NEW refresh_token.
      * is_refresh_token_rotated() lets downstream callers flag replay.
  H2: redirect_uri post-exchange consistency check (scheme / host / path).
      * Failure downgrades ok=False, reason="redirect_uri_mismatch".
      * Audit row carries redirect_uri_used_hash + sub_reason.
  H3: Scope-mismatch detection (RFC-6749 § 3.3).
      * granted < requested -> match=False + missing[] (legit downscope).
      * granted > requested -> match=False + extra[] (suspicious creep).
      * Mismatch is AUDIT-ONLY, never fails the request.
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
# H1 — Refresh-token rotation tracking
# ---------------------------------------------------------------------------
print("=" * 70)
print("H1 Refresh-token rotation tracking (RFC-6749 sec 10.4)")
print("=" * 70)

# H1-1: track_refresh_token_issuance puts an entry in the ring buffer
_h._reset_refresh_token_rings_for_tests()
_h.track_refresh_token_issuance(
    provider="schoology", tenant_schema="school_a",
    refresh_token_hash="abc123def456",
    issued_at_iso="2026-05-30T12:00:00+00:00",
    expires_in_seconds=3600,
)
_snap = _h._refresh_token_ring_snapshot("schoology")
assert len(_snap) == 1
assert _snap[0]["hash"] == "abc123def456"
assert _snap[0]["rotated"] is False
assert _snap[0]["expires_in_seconds"] == 3600
# Tenant schema is hashed before storage — raw schema never persisted.
assert _snap[0]["tenant_schema_hash"] != "school_a"
assert len(_snap[0]["tenant_schema_hash"]) == 12
_ok("track_refresh_token_issuance records entry; tenant_schema hashed")

# H1-2: is_refresh_token_rotated returns False for never-seen hash
assert _h.is_refresh_token_rotated(
    provider="schoology", refresh_token_hash="never_seen_hash",
) is False
# And False for a known-but-not-rotated hash too.
assert _h.is_refresh_token_rotated(
    provider="schoology", refresh_token_hash="abc123def456",
) is False
_ok("is_refresh_token_rotated returns False for never-seen + known-not-rotated")

# H1-3: refresh_access_token marks old as rotated when new is issued
_h._reset_refresh_token_rings_for_tests()
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
_orig_post = requests.post
_orig_audit = _sg._record_audit
_audit_rows: list[dict] = []
_sg._record_audit = lambda **kw: _audit_rows.append(kw)


def _sg_refresh_with_new_rt(url, **kw):
    return _FakeResp(200, {
        "access_token": "new-at",
        "refresh_token": "new-rt-bytes",  # NEW refresh token -> rotation
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "read write",
    })


requests.post = _sg_refresh_with_new_rt
try:
    r = _sg.refresh_access_token(
        refresh_token="old-rt-bytes", client_id="cid", client_secret="cs",
        tenant_schema="school_a",
    )
    assert r["ok"] is True
    # An audit row with action="refresh_token_rotation" must exist with BOTH
    # old + new hashes.
    rotation_rows = [a for a in _audit_rows
                     if a.get("action") == "refresh_token_rotation"]
    assert len(rotation_rows) == 1, f"expected 1 rotation row, got {len(rotation_rows)}"
    summary = rotation_rows[0]["payload_summary"]
    assert "old_refresh_token_hash" in summary
    assert "new_refresh_token_hash" in summary
    assert summary["old_refresh_token_hash"] != summary["new_refresh_token_hash"]
    # And neither value is the raw token string.
    assert summary["old_refresh_token_hash"] != "old-rt-bytes"
    assert summary["new_refresh_token_hash"] != "new-rt-bytes"
    # And the standard oauth_refresh row carries the same correlation pair.
    refresh_rows = [a for a in _audit_rows
                    if a.get("action") == "oauth_refresh"]
    assert len(refresh_rows) >= 1
    rsum = refresh_rows[0]["payload_summary"]
    assert rsum["old_refresh_token_hash"] == summary["old_refresh_token_hash"]
    assert rsum["refresh_token_hash"] == summary["new_refresh_token_hash"]
    _ok("Schoology refresh_access_token writes refresh_token_rotation audit row w/ old + new hashes (raw tokens never logged)")
finally:
    requests.post = _orig_post
    _sg._record_audit = _orig_audit
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)

# H1-4: is_refresh_token_rotated returns True after rotation
# The previous test populated the ring buffer w/ both old + new tokens. The
# OLD hash should now be flagged as rotated. The NEW hash should be present
# but NOT rotated yet.
import hashlib as _hashlib_test
_old_expected = _hashlib_test.sha256(b"old-rt-bytes").hexdigest()[:12]
_new_expected = _hashlib_test.sha256(b"new-rt-bytes").hexdigest()[:12]
assert _h.is_refresh_token_rotated(
    provider="schoology", refresh_token_hash=_old_expected,
) is True, "old token should be flagged as rotated"
assert _h.is_refresh_token_rotated(
    provider="schoology", refresh_token_hash=_new_expected,
) is False, "new token should NOT yet be flagged as rotated"
_ok("is_refresh_token_rotated returns True for rotated, False for fresh")


# ---------------------------------------------------------------------------
# H2 — validate_redirect_uri_consistency
# ---------------------------------------------------------------------------
print("=" * 70)
print("H2 redirect_uri post-exchange validation")
print("=" * 70)

# H2-1: clean case — no echo from upstream means we can't detect drift; ok.
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"access_token": "at", "expires_in": 3600},
)
assert ok_ is True
assert reason == "ok"
# And the case where the echo matches exactly.
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"redirect_uri": "https://app.example.com/oauth/cb"},
)
assert ok_ is True
assert reason == "ok"
_ok("validate_redirect_uri_consistency: clean case (no echo OR matching echo)")

# H2-2: scheme mismatch detected
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"redirect_uri": "http://app.example.com/oauth/cb"},
)
assert ok_ is False
assert reason == "scheme_mismatch"
_ok("validate_redirect_uri_consistency catches scheme mismatch (https vs http)")

# H2-3: host mismatch detected
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"redirect_uri": "https://evil.example.org/oauth/cb"},
)
assert ok_ is False
assert reason == "host_mismatch"
# Also catch nested-form metadata.
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"request": {"redirect_uri": "https://evil.example.org/oauth/cb"}},
)
assert ok_ is False
assert reason == "host_mismatch"
# Path mismatch detected.
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="https://app.example.com/oauth/cb",
    response_metadata={"redirect_uri": "https://app.example.com/oauth/elsewhere"},
)
assert ok_ is False
assert reason == "path_mismatch"
# Invalid requested URI is its own taxonomy.
ok_, reason = _h.validate_redirect_uri_consistency(
    requested_uri="", response_metadata={"redirect_uri": "https://x/y"},
)
assert ok_ is False
assert reason == "invalid_requested_uri"
_ok("validate_redirect_uri_consistency catches host_mismatch + path_mismatch + invalid_requested_uri")

# H2-4: connector audit row carries redirect_uri_used_hash + downgrades on mismatch
os.environ["RMC_D2L_OAUTH_LIVE_OUTBOUND"] = "1"
_orig_post = requests.post
_orig_audit = _d2l._record_audit
_audit_rows: list[dict] = []
_d2l._record_audit = lambda **kw: _audit_rows.append(kw)


def _d2l_exchange_with_evil_echo(url, **kw):
    # Brightspace echoes back a redirect_uri pointing at a different host.
    return _FakeResp(200, {
        "access_token": "at",
        "refresh_token": "rt",
        "expires_in": 3600,
        "token_type": "Bearer",
        "redirect_uri": "https://evil.brightspace.com/oauth/cb",
    })


requests.post = _d2l_exchange_with_evil_echo
try:
    r = _d2l.exchange_authorization_code_for_token(
        code="ok-code", client_id="cid", client_secret="cs",
        redirect_uri="https://app.example.com/oauth/cb",
        tenant_schema="school_b",
    )
    # Result was DOWNGRADED to ok=False because of the host mismatch.
    assert r["ok"] is False
    assert r["reason"] == "redirect_uri_mismatch"
    assert r["redirect_uri_mismatch_sub_reason"] == "host_mismatch"
    # Audit row carries redirect_uri_used_hash (12-char SHA-256[:12], NOT raw URI).
    assert _audit_rows, "expected at least one audit row"
    summary = _audit_rows[-1]["payload_summary"]
    assert "redirect_uri_used_hash" in summary
    assert len(summary["redirect_uri_used_hash"]) == 12
    assert summary["redirect_uri_used_hash"] != "https://app.example.com/oauth/cb"
    assert summary["redirect_uri_mismatch_sub_reason"] == "host_mismatch"
    _ok("D2L exchange audit row carries redirect_uri_used_hash + downgrades on host_mismatch")
finally:
    requests.post = _orig_post
    _d2l._record_audit = _orig_audit
    os.environ.pop("RMC_D2L_OAUTH_LIVE_OUTBOUND", None)


# ---------------------------------------------------------------------------
# H3 — compare_scopes
# ---------------------------------------------------------------------------
print("=" * 70)
print("H3 Scope-mismatch detection (RFC-6749 sec 3.3)")
print("=" * 70)

# H3-1: match=True when granted EQUALS requested
r = _h.compare_scopes(
    requested_scopes=("read", "write"),
    granted_scopes="read write",
)
assert r == {"match": True}, r
# And match=True when granted is a SUPERSET (subset of requested in granted).
# Per spec text: "granted >= requested" means we got everything we asked for.
# However the W24 contract treats any non-equal set as match=False so both
# operator-relevant signals (downscoping + scope-creep) surface together.
# So a granted superset of requested -> match=False w/ extra populated.
r = _h.compare_scopes(
    requested_scopes=("read", "write"),
    granted_scopes="read write admin",
)
assert r["match"] is False
assert r["extra"] == ["admin"]
assert r["missing"] == []
_ok("compare_scopes: match=True when sets equal; broader granted -> match=False w/ extra")

# H3-2: match=False w/ missing list when granted is narrower (downscoping)
r = _h.compare_scopes(
    requested_scopes=("read", "write", "admin"),
    granted_scopes="read",
)
assert r["match"] is False
assert r["missing"] == ["admin", "write"]
assert r["extra"] == []
_ok("compare_scopes: granted narrower -> match=False w/ missing list (downscoping)")

# H3-3: match=False w/ extra list when granted is broader (scope creep)
r = _h.compare_scopes(
    requested_scopes=["read"],
    granted_scopes=["read", "write", "delete"],
)
assert r["match"] is False
assert r["missing"] == []
assert r["extra"] == ["delete", "write"]
# Empty-string inputs are tolerated (no-op).
r = _h.compare_scopes(requested_scopes="", granted_scopes="")
assert r == {"match": True}
# None-inputs tolerated.
r = _h.compare_scopes(requested_scopes=None, granted_scopes=None)
assert r == {"match": True}
_ok("compare_scopes: granted broader -> match=False w/ extra; empty/None tolerated")

# H3-4: connector result carries scope_match + scope_missing fields
os.environ["RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"] = "1"
_orig_post = requests.post
_orig_audit = _sg._record_audit
_audit_rows: list[dict] = []
_sg._record_audit = lambda **kw: _audit_rows.append(kw)


def _sg_exchange_with_narrow_scope(url, **kw):
    # Schoology granted ONLY "read" when we asked for "read write".
    return _FakeResp(200, {
        "access_token": "at",
        "refresh_token": "rt",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "read",
    })


requests.post = _sg_exchange_with_narrow_scope
try:
    r = _sg.exchange_authorization_code_for_token(
        code="ok-code", client_id="cid", client_secret="cs",
        redirect_uri="https://app.example.com/oauth/cb",
        tenant_schema="school_c",
    )
    # Scope mismatch is AUDIT-ONLY, never fails the request — ok must still be True.
    assert r["ok"] is True
    # But the result dict carries the mismatch signal.
    assert r["scope_match"] is False
    assert r["scope_missing"] == ["write"]
    assert r["scope_extra"] == []
    # And the audit summary carries the same fields.
    success_rows = [a for a in _audit_rows
                    if a.get("action") == "oauth_exchange" and a.get("ok") is True]
    assert len(success_rows) == 1
    summary = success_rows[0]["payload_summary"]
    assert summary["scope_match"] is False
    assert summary["scope_missing"] == ["write"]
    _ok("Schoology exchange: scope_match + scope_missing surfaced in result + audit (request NOT failed)")
finally:
    requests.post = _orig_post
    _sg._record_audit = _orig_audit
    os.environ.pop("RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND", None)


print("=" * 70)
print(f"v4.00.91 Wave 24 OAuth security hardening — {CASES} CASES OK")
print("=" * 70)
