"""v4.00.91 — Wave 24 SAML 2.0 security hardening smoke.

Exercises three audit-gap closures shipped in ``apps/api/saml.py``:

* **H4** — RSA-SHA1 rejection (configurable).
  ``_is_signature_algorithm_allowed`` enforces a policy ceiling on every
  inbound signature-algorithm URI. Default rejects rsa-sha1; opt-in via
  ``RMC_SAML_ALLOW_RSA_SHA1=1`` for legacy IdPs. Unknown URIs always
  reject.

* **H5** — Clock-skew tolerance on Conditions/@NotBefore + @NotOnOrAfter.
  ``_is_within_validity_window`` admits assertions within +/- the env
  ``RMC_SAML_CLOCK_SKEW_SECONDS`` (default 300, clamped to [0, 3600])
  so NTP drift between SP and IdP can't 401 a valid login.

* **H6** — Assertion-ID one-time-use cache (replay defense).
  ``_register_assertion_id`` rejects the second-and-subsequent sighting
  of an Assertion ID inside the 24h TTL window. Lock-protected; evicts
  oldest 100 entries when capped at 10000. Bypass via
  ``RMC_SAML_REPLAY_DEFENSE_ENABLED=0``.

All H4/H5/H6 helpers are pure-Python (stdlib only) — they exercise
without any optional deps. The lxml/cryptography SKIP guard is here for
consistency with prior-wave smokes (and in case future hardening adds
deps-dependent cases inside the same script).

Reason strings asserted match the contracts in ``apps/api/saml.py``:

    H4 _is_signature_algorithm_allowed:
        ok / legacy_sha1_allowed_by_env / rsa_sha1_rejected_by_policy /
        unknown_signature_algorithm
    H5 _is_within_validity_window:
        ok / ok_no_constraint / not_yet_valid / expired / malformed_iso
    H6 _register_assertion_id:
        first_seen / replay_detected / missing_id_skipped
"""
import os, sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import django  # noqa: E402
django.setup()

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# ---------------------------------------------------------------------------
# Optional-dep SKIP guard (mirrors smoke_v4_00_89_saml.py pattern).
# ---------------------------------------------------------------------------
_SKIP_OPTIONAL = False
_SKIP_REASON = ""
try:
    import lxml.etree as _et  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa  # noqa: F401
except ImportError as _e:
    _SKIP_OPTIONAL = True
    _SKIP_REASON = str(_e)

if _SKIP_OPTIONAL:
    print(f"[NOTE] lxml/cryptography not installed locally — the pure-Python "
          f"H4/H5/H6 helper cases still run; only deps-dependent extras "
          f"would skip: {_SKIP_REASON}")


from apps.api import saml as _saml  # noqa: E402


def _restore(name, prev):
    if prev is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = prev


# ---------------------------------------------------------------------------
# H4 — RSA-SHA1 rejection policy
# ---------------------------------------------------------------------------
print("=" * 70)
print("H4: signature-algorithm policy (rsa-sha1 rejection)")
print("=" * 70)

_URI_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
_URI_SHA384 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384"
_URI_SHA512 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512"
_URI_ECDSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"
_URI_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
_URI_BOGUS = "http://www.w3.org/2001/04/xmldsig-more#fake-md5"

_orig_h4 = os.environ.get("RMC_SAML_ALLOW_RSA_SHA1")
try:
    # --- H4-1: SHA256 allowed when env unset ---
    os.environ.pop("RMC_SAML_ALLOW_RSA_SHA1", None)
    ok, reason = _saml._is_signature_algorithm_allowed(_URI_SHA256)
    assert ok is True and reason == "ok", f"H4-1 got ({ok!r}, {reason!r})"
    _ok("H4-1 rsa-sha256 -> (True, ok) when env unset")

    # --- H4-1b extra coverage: SHA-384, SHA-512, ECDSA-SHA256 also OK ---
    for _uri in (_URI_SHA384, _URI_SHA512, _URI_ECDSA_SHA256):
        ok, reason = _saml._is_signature_algorithm_allowed(_uri)
        assert ok is True and reason == "ok", f"H4-1b {_uri} got ({ok!r}, {reason!r})"
    _ok("H4-1b rsa-sha384 / rsa-sha512 / ecdsa-sha256 -> (True, ok)")

    # --- H4-2: SHA1 rejected when env unset (default) ---
    ok, reason = _saml._is_signature_algorithm_allowed(_URI_SHA1)
    assert ok is False and reason == "rsa_sha1_rejected_by_policy", \
        f"H4-2 got ({ok!r}, {reason!r})"
    _ok("H4-2 rsa-sha1 -> (False, rsa_sha1_rejected_by_policy) by default")

    # --- H4-3: SHA1 allowed when env=1 ---
    os.environ["RMC_SAML_ALLOW_RSA_SHA1"] = "1"
    ok, reason = _saml._is_signature_algorithm_allowed(_URI_SHA1)
    assert ok is True and reason == "legacy_sha1_allowed_by_env", \
        f"H4-3 got ({ok!r}, {reason!r})"
    _ok("H4-3 rsa-sha1 -> (True, legacy_sha1_allowed_by_env) when env=1")

    # --- H4-3b: env=0 still rejects ---
    os.environ["RMC_SAML_ALLOW_RSA_SHA1"] = "0"
    ok, reason = _saml._is_signature_algorithm_allowed(_URI_SHA1)
    assert ok is False and reason == "rsa_sha1_rejected_by_policy", \
        f"H4-3b got ({ok!r}, {reason!r})"
    _ok("H4-3b rsa-sha1 -> rejected when env explicitly 0")

    # --- H4-4: Unknown alg rejected (env independent) ---
    os.environ.pop("RMC_SAML_ALLOW_RSA_SHA1", None)
    ok, reason = _saml._is_signature_algorithm_allowed(_URI_BOGUS)
    assert ok is False and reason == "unknown_signature_algorithm", \
        f"H4-4 got ({ok!r}, {reason!r})"
    # And empty string is treated as unknown too.
    ok, reason = _saml._is_signature_algorithm_allowed("")
    assert ok is False and reason == "unknown_signature_algorithm", \
        f"H4-4b got ({ok!r}, {reason!r})"
    _ok("H4-4 unknown alg URI + empty string -> (False, unknown_signature_algorithm)")
finally:
    _restore("RMC_SAML_ALLOW_RSA_SHA1", _orig_h4)


# ---------------------------------------------------------------------------
# H5 — Clock-skew tolerance on validity window
# ---------------------------------------------------------------------------
print("=" * 70)
print("H5: validity-window check w/ clock-skew tolerance")
print("=" * 70)

from datetime import datetime, timedelta, timezone

_orig_h5 = os.environ.get("RMC_SAML_CLOCK_SKEW_SECONDS")
try:
    # Use default skew (300s) for H5-1..H5-3.
    os.environ.pop("RMC_SAML_CLOCK_SKEW_SECONDS", None)
    assert _saml._clock_skew_seconds() == 300, "default skew must be 300"
    # Clamp checks.
    os.environ["RMC_SAML_CLOCK_SKEW_SECONDS"] = "9999"
    assert _saml._clock_skew_seconds() == 3600, "high clamp must be 3600"
    os.environ["RMC_SAML_CLOCK_SKEW_SECONDS"] = "-50"
    assert _saml._clock_skew_seconds() == 0, "low clamp must be 0"
    os.environ["RMC_SAML_CLOCK_SKEW_SECONDS"] = "not-a-number"
    assert _saml._clock_skew_seconds() == 300, "malformed must fall back to 300"
    os.environ.pop("RMC_SAML_CLOCK_SKEW_SECONDS", None)

    _fixed_now = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)

    # --- H5-1: assertion within validity window allowed ---
    nb = (_fixed_now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    na = (_fixed_now + timedelta(minutes=8)).isoformat().replace("+00:00", "Z")
    ok, reason = _saml._is_within_validity_window(
        not_before_iso=nb, not_on_or_after_iso=na, now=_fixed_now,
    )
    assert ok is True and reason == "ok", f"H5-1 got ({ok!r}, {reason!r})"
    _ok("H5-1 assertion within window -> (True, ok)")

    # --- H5-2: assertion 4 min old (within 5min skew) allowed ---
    # NotOnOrAfter passed 4 minutes ago, but skew is 5 min, so still ok.
    nb = (_fixed_now - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    na = (_fixed_now - timedelta(minutes=4)).isoformat().replace("+00:00", "Z")
    ok, reason = _saml._is_within_validity_window(
        not_before_iso=nb, not_on_or_after_iso=na, now=_fixed_now,
    )
    assert ok is True and reason == "ok", f"H5-2 got ({ok!r}, {reason!r})"
    _ok("H5-2 expired 4 min ago (within 5 min skew) -> (True, ok)")

    # --- H5-3: assertion 10 min in future rejected (beyond skew) ---
    nb = (_fixed_now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    na = (_fixed_now + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    ok, reason = _saml._is_within_validity_window(
        not_before_iso=nb, not_on_or_after_iso=na, now=_fixed_now,
    )
    assert ok is False and reason == "not_yet_valid", f"H5-3 got ({ok!r}, {reason!r})"
    _ok("H5-3 NotBefore 10 min in future (beyond 5 min skew) -> (False, not_yet_valid)")

    # --- H5-3b: assertion 10 min past expiry rejected (beyond skew) ---
    nb = (_fixed_now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    na = (_fixed_now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    ok, reason = _saml._is_within_validity_window(
        not_before_iso=nb, not_on_or_after_iso=na, now=_fixed_now,
    )
    assert ok is False and reason == "expired", f"H5-3b got ({ok!r}, {reason!r})"
    _ok("H5-3b expired 10 min ago (beyond 5 min skew) -> (False, expired)")

    # --- H5-4: malformed ISO returns malformed_iso reason ---
    ok, reason = _saml._is_within_validity_window(
        not_before_iso="not-an-iso", not_on_or_after_iso=na, now=_fixed_now,
    )
    assert ok is False and reason == "malformed_iso", f"H5-4 got ({ok!r}, {reason!r})"
    _ok("H5-4 malformed NotBefore ISO -> (False, malformed_iso)")

    # --- H5-4b: empty + empty -> ok_no_constraint sentinel ---
    ok, reason = _saml._is_within_validity_window(
        not_before_iso="", not_on_or_after_iso="", now=_fixed_now,
    )
    assert ok is True and reason == "ok_no_constraint", f"H5-4b got ({ok!r}, {reason!r})"
    _ok("H5-4b empty-empty -> (True, ok_no_constraint)")

    # --- H5-4c: zero skew via env -> exactly-at-edge becomes expired ---
    os.environ["RMC_SAML_CLOCK_SKEW_SECONDS"] = "0"
    nb = (_fixed_now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    na = _fixed_now.isoformat().replace("+00:00", "Z")  # exactly now
    ok, reason = _saml._is_within_validity_window(
        not_before_iso=nb, not_on_or_after_iso=na, now=_fixed_now,
    )
    # exact-edge with zero skew: now >= NotOnOrAfter -> expired
    assert ok is False and reason == "expired", f"H5-4c got ({ok!r}, {reason!r})"
    _ok("H5-4c zero-skew env -> strict edge enforced (expired)")
    os.environ.pop("RMC_SAML_CLOCK_SKEW_SECONDS", None)

    # --- Back-compat: _within_validity_window still bool, delegates to new helper ---
    # Use REAL now() here (not the fixed _fixed_now used for the H5 cases
    # above) because the legacy wrapper doesn't accept a now= override.
    _real_now = datetime.now(timezone.utc)
    nb_r = (_real_now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    na_r = (_real_now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    assert _saml._within_validity_window(nb_r, na_r) is True, \
        "back-compat bool wrapper failed (expected True for in-window)"
    # Also verify legacy bool wrapper returns False for malformed.
    assert _saml._within_validity_window("not-iso", na_r) is False, \
        "back-compat bool wrapper expected False on malformed"
    _ok("H5-bc legacy _within_validity_window still bool -> True/False as expected")
finally:
    _restore("RMC_SAML_CLOCK_SKEW_SECONDS", _orig_h5)


# ---------------------------------------------------------------------------
# H6 — Assertion-ID one-time-use replay defense
# ---------------------------------------------------------------------------
print("=" * 70)
print("H6: assertion-ID one-time-use cache (replay defense)")
print("=" * 70)

_orig_h6 = os.environ.get("RMC_SAML_REPLAY_DEFENSE_ENABLED")
try:
    # --- H6-1: first-seen assertion ID registered ok ---
    _saml._clear_assertion_id_cache()
    os.environ.pop("RMC_SAML_REPLAY_DEFENSE_ENABLED", None)
    assert _saml._replay_defense_enabled() is True, "default must be enabled"
    ok, reason = _saml._register_assertion_id("_assert_smoke_h6_001")
    assert ok is True and reason == "first_seen", f"H6-1 got ({ok!r}, {reason!r})"
    _ok("H6-1 first-seen assertion ID -> (True, first_seen)")

    # --- H6-2: second-seen assertion ID detected as replay ---
    ok, reason = _saml._register_assertion_id("_assert_smoke_h6_001")
    assert ok is False and reason == "replay_detected", f"H6-2 got ({ok!r}, {reason!r})"
    _ok("H6-2 repeat of same ID -> (False, replay_detected)")

    # --- H6-2b: empty ID surfaces missing_id_skipped (defense in depth) ---
    ok, reason = _saml._register_assertion_id("")
    assert ok is True and reason == "missing_id_skipped", \
        f"H6-2b got ({ok!r}, {reason!r})"
    _ok("H6-2b empty ID -> (True, missing_id_skipped)")

    # --- H6-3: cache cap evicts old entries ---
    # Force the cap to a small value via monkeypatching constants for the
    # test only. Mutates the module's int attributes; restored after.
    _orig_max = _saml._ASSERTION_ID_CACHE_MAX
    _orig_evict = _saml._ASSERTION_ID_CACHE_EVICT_BATCH
    try:
        _saml._clear_assertion_id_cache()
        _saml._ASSERTION_ID_CACHE_MAX = 10
        _saml._ASSERTION_ID_CACHE_EVICT_BATCH = 5
        # Fill to cap.
        for i in range(10):
            ok, reason = _saml._register_assertion_id(f"_assert_evict_{i:03d}")
            assert ok is True and reason == "first_seen", f"fill {i} failed"
        # Cache now at cap (10). Next write evicts oldest 5 first.
        ok, reason = _saml._register_assertion_id("_assert_evict_NEW")
        assert ok is True and reason == "first_seen", \
            f"H6-3 new entry after cap failed ({ok!r}, {reason!r})"
        cache_size = len(_saml._ASSERTION_ID_CACHE)
        assert cache_size == 6, \
            f"H6-3 expected 6 entries post-evict (10 - 5 + 1), got {cache_size}"
        # Oldest entries should be gone; newest entries + the just-added
        # one should remain.
        assert "_assert_evict_000" not in _saml._ASSERTION_ID_CACHE, \
            "H6-3 oldest should be evicted"
        assert "_assert_evict_009" in _saml._ASSERTION_ID_CACHE, \
            "H6-3 newest pre-evict entry should remain"
        assert "_assert_evict_NEW" in _saml._ASSERTION_ID_CACHE, \
            "H6-3 just-added entry must be present"
        _ok(f"H6-3 cap-evict: 10 + 1 -> 6 entries (oldest 5 dropped, "
            f"newest + new survive)")
    finally:
        _saml._ASSERTION_ID_CACHE_MAX = _orig_max
        _saml._ASSERTION_ID_CACHE_EVICT_BATCH = _orig_evict
        _saml._clear_assertion_id_cache()

    # --- H6-3b: _clear_assertion_id_cache returns count cleared ---
    _saml._register_assertion_id("_clear_test_a")
    _saml._register_assertion_id("_clear_test_b")
    _saml._register_assertion_id("_clear_test_c")
    n = _saml._clear_assertion_id_cache()
    assert n == 3, f"H6-3b expected 3 cleared, got {n}"
    assert len(_saml._ASSERTION_ID_CACHE) == 0, "H6-3b cache must be empty"
    _ok("H6-3b _clear_assertion_id_cache returns count (3)")

    # --- H6-4: env=0 disables replay defense ---
    os.environ["RMC_SAML_REPLAY_DEFENSE_ENABLED"] = "0"
    assert _saml._replay_defense_enabled() is False, "env=0 must disable"

    # Register an ID -- even though direct call still works on the cache,
    # _replay_defense_enabled gates whether _parse_saml_response routes
    # through registration at all. The direct helper does NOT check the
    # env (it's the gate, not the action) — so we exercise the helper to
    # confirm it still functions, then assert _parse_saml_response leaves
    # replay_ok=True / replay_reason="disabled" when env=0.
    _saml._clear_assertion_id_cache()

    # Build a minimal SAMLResponse (the parser uses stdlib xml.etree, no
    # lxml dep needed). Issuer + Subject + Conditions + StatusCode are
    # the minimum the parser walks.
    import base64
    _minimal_resp_xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
        ' ID="_resp_001" Version="2.0" IssueInstant="2026-05-30T12:00:00Z"'
        ' InResponseTo="_authn_001">'
        '<samlp:Status>'
        '<samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>'
        '</samlp:Status>'
        '<saml:Assertion ID="_assert_smoke_disabled_001" Version="2.0"'
        ' IssueInstant="2026-05-30T12:00:00Z">'
        '<saml:Issuer>https://idp.example.com</saml:Issuer>'
        '<saml:Subject>'
        '<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        'user@example.com</saml:NameID>'
        '</saml:Subject>'
        '<saml:Conditions NotBefore="2026-05-30T11:55:00Z"'
        ' NotOnOrAfter="2026-05-30T12:05:00Z">'
        '<saml:AudienceRestriction>'
        '<saml:Audience>https://sp.example.com</saml:Audience>'
        '</saml:AudienceRestriction>'
        '</saml:Conditions>'
        '</saml:Assertion>'
        '</samlp:Response>'
    )
    _b64 = base64.b64encode(_minimal_resp_xml.encode("utf-8")).decode("ascii")
    parsed = _saml._parse_saml_response(_b64)
    assert parsed.get("replay_ok") is True, \
        f"H6-4 with env=0 parsed.replay_ok must be True, got {parsed.get('replay_ok')!r}"
    assert parsed.get("replay_reason") == "disabled", \
        f"H6-4 with env=0 parsed.replay_reason must be 'disabled', got {parsed.get('replay_reason')!r}"

    # Parse a SECOND time with the same Assertion ID -- still no replay
    # rejection because the env disables it.
    parsed2 = _saml._parse_saml_response(_b64)
    assert parsed2.get("replay_ok") is True, "H6-4 second parse must still allow"
    assert parsed2.get("replay_reason") == "disabled", \
        "H6-4 second parse must still be disabled"
    _ok("H6-4 env=0 disables replay defense (2x same assertion ID OK)")

    # --- H6-4b: env=1 re-enables; second parse trips replay_detected ---
    os.environ["RMC_SAML_REPLAY_DEFENSE_ENABLED"] = "1"
    assert _saml._replay_defense_enabled() is True, "env=1 must re-enable"
    _saml._clear_assertion_id_cache()
    parsed = _saml._parse_saml_response(_b64)
    assert parsed.get("replay_ok") is True and parsed.get("replay_reason") == "first_seen", \
        f"H6-4b first parse: {parsed.get('replay_ok')!r}, {parsed.get('replay_reason')!r}"
    parsed2 = _saml._parse_saml_response(_b64)
    assert parsed2.get("replay_ok") is False, \
        f"H6-4b second parse should fail replay_ok, got {parsed2.get('replay_ok')!r}"
    assert parsed2.get("replay_reason") == "replay_detected", \
        f"H6-4b second parse reason: {parsed2.get('replay_reason')!r}"
    _ok("H6-4b env=1 re-enables: 2nd parse of same assertion ID -> replay_detected")
finally:
    _restore("RMC_SAML_REPLAY_DEFENSE_ENABLED", _orig_h6)
    _saml._clear_assertion_id_cache()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("=" * 70)
print(f"v4.00.91 SAML security hardening smoke: {CASES} cases green")
print("=" * 70)
