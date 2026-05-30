"""v4.00.67 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (JP-29/30, CN-YN/GX/SX/SN, KR-49, PT-11/13,
    GR-A1/B, EG-C/ALX, IT-LAZ); SOT >= 468.
T2: SAML SP-initiated SSO — _build_saml_authn_request + login_start view
    w/ HTTP-Redirect (default) + HTTP-POST bindings, ForceAuthn /
    IsPassive / NameIDPolicy support, reuses v4.00.61 sign env.
T3: OneRoster ?filter= parenthesized nesting — recursive-descent parser
    via _Parser class; parens override AND > OR precedence; fail-safe
    on unbalanced parens (back-compat w/ v4.00.66 flat-grammar contract).
T4: Demographics stateOfBirthAbbreviation ISO 3166-2 validation scoped
    to countryOfBirthCode — accept known subdivisions only when country
    is supplied; shape-only check otherwise.
T5: Retention preview sparkline by-week — _retention_purge_sparkline
    returns 24 buckets (12 before + 12 after cutoff) w/ pre-computed
    SVG geometry for the template.

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}")
    sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-67-staff",
        defaults={"email": "smoke@v4-00-67.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "JP-29", "JP-30",
        "CN-YN", "CN-GX", "CN-SX", "CN-SN",
        "KR-49",
        "PT-11", "PT-13",
        "GR-A1", "GR-B",
        "EG-C", "EG-ALX",
        "IT-LAZ",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", f"missing {r}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 4:
            _fail(f"t1-school-types-{k}", "need >= 4")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3")
        _ok(f"t1-{k} OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 468:
        _fail("t1-sot-count", f"expected >= 468, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] SAML SP-initiated SSO (AuthnRequest builder)")
    from apps.api import saml as saml_mod
    rf = RequestFactory()

    # Builder shape.
    xml = saml_mod._build_saml_authn_request(
        sp_entity_id="https://rmc.test/sp",
        acs_url="https://rmc.test/sso/saml/acs/",
        idp_target="https://idp.example/sso",
    )
    for required in (
        b'<samlp:AuthnRequest',
        b'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"',
        b'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"',
        b'Version="2.0"',
        b'IssueInstant=',
        b'Destination="https://idp.example/sso"',
        b'AssertionConsumerServiceURL="https://rmc.test/sso/saml/acs/"',
        b'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"',
        b'<saml:Issuer>https://rmc.test/sp</saml:Issuer>',
    ):
        if required not in xml:
            _fail(f"t2-xml-missing-{required[:30]!r}", "absent")
    _ok(f"t2-builder XML carries all 9 required SAML 2.0 AuthnRequest substrings")

    # ForceAuthn / IsPassive / NameIDPolicy switches.
    xml = saml_mod._build_saml_authn_request(
        sp_entity_id="rmc-sp", acs_url="/acs", idp_target="",
        force_authn=True, is_passive=True,
        name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )
    if b'ForceAuthn="true"' not in xml:
        _fail("t2-force-authn", "missing")
    if b'IsPassive="true"' not in xml:
        _fail("t2-is-passive", "missing")
    if b'<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"' not in xml:
        _fail("t2-name-id-policy", "missing")
    _ok("t2-builder ForceAuthn + IsPassive + NameIDPolicy emitted when requested")

    # Defaults OFF.
    xml = saml_mod._build_saml_authn_request(
        sp_entity_id="rmc-sp", acs_url="/acs", idp_target="",
    )
    if b'ForceAuthn=' in xml:
        _fail("t2-force-default-off", "should not be emitted")
    if b'IsPassive=' in xml:
        _fail("t2-passive-default-off", "should not be emitted")
    if b'<samlp:NameIDPolicy' in xml:
        _fail("t2-name-id-default-off", "should not be emitted")
    _ok("t2-builder defaults: no ForceAuthn / IsPassive / NameIDPolicy attrs")

    # login_start view — IdP target missing -> 503.
    os.environ.pop("RMC_SAML_IDP_SSO_URL", None)
    req = rf.get("/sso/saml/login/start/")
    resp = saml_mod.login_start(req)
    if resp.status_code != 503:
        _fail("t2-login-503", f"got {resp.status_code}")
    body = _json.loads(resp.content)
    if body.get("stage") != "idp_sso_target_missing":
        _fail("t2-login-503-stage", f"got {body}")
    _ok("t2-login_start no env -> 503 idp_sso_target_missing")

    # login_start JSON format reports shape.
    os.environ["RMC_SAML_IDP_SSO_URL"] = "https://idp.example/sso"
    try:
        req = rf.get("/sso/saml/login/start/?format=json")
        resp = saml_mod.login_start(req)
        if resp.status_code != 200:
            _fail("t2-login-json", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        for k in ("authn_request_b64", "binding", "redirect_url", "saml_request_deflated_b64",
                  "sp_entity_id", "acs_url", "idp_target", "signed", "signature_reason"):
            if k not in body:
                _fail(f"t2-login-json-key-{k}", f"missing; got keys {sorted(body.keys())}")
        if body["binding"] != "HTTP-Redirect":
            _fail("t2-login-default-binding", f"got {body['binding']}")
        if "https://idp.example/sso?SAMLRequest=" not in body["redirect_url"]:
            _fail("t2-login-redirect-url", body["redirect_url"])
        _ok(f"t2-login_start ?format=json shape complete; binding={body['binding']}")

        # 302 redirect (no ?format=json).
        req = rf.get("/sso/saml/login/start/?next=/portal/dashboard/")
        resp = saml_mod.login_start(req)
        if resp.status_code != 302:
            _fail("t2-login-302", f"got {resp.status_code}")
        loc = resp["Location"]
        if not loc.startswith("https://idp.example/sso?SAMLRequest="):
            _fail("t2-login-302-loc", loc[:200])
        if "RelayState=%2Fportal%2Fdashboard%2F" not in loc:
            _fail("t2-login-relay", loc)
        _ok("t2-login_start 302 to IdP w/ deflated SAMLRequest + RelayState")

        # Open-redirect defense: relay starting with // is dropped.
        req = rf.get("/sso/saml/login/start/?next=//evil.example/&format=json")
        resp = saml_mod.login_start(req)
        body = _json.loads(resp.content)
        if body.get("relay_state") != "":
            _fail("t2-login-open-redirect", f"got {body.get('relay_state')!r}")
        _ok("t2-login_start //external relay dropped (open-redirect defense)")

        # POST binding returns auto-submit HTML form.
        req = rf.get("/sso/saml/login/start/?binding=post")
        resp = saml_mod.login_start(req)
        if resp.status_code != 200:
            _fail("t2-login-post-status", f"got {resp.status_code}")
        if b"<form" not in resp.content or b"SAMLRequest" not in resp.content:
            _fail("t2-login-post-form", resp.content[:200])
        if b"sso-start-form" not in resp.content:
            _fail("t2-login-post-formid", "missing form id")
        _ok("t2-login_start ?binding=post -> auto-submit HTML form w/ SAMLRequest hidden field")

        # ForceAuthn + IsPassive routed through to JSON shape.
        req = rf.get("/sso/saml/login/start/?force_authn=1&passive=1&format=json")
        resp = saml_mod.login_start(req)
        body = _json.loads(resp.content)
        if body.get("force_authn") is not True or body.get("is_passive") is not True:
            _fail("t2-login-flags", f"got {body}")
        _ok("t2-login_start ?force_authn=1 + ?passive=1 echoed in JSON shape")
    finally:
        os.environ.pop("RMC_SAML_IDP_SSO_URL", None)

    # URL route resolves.
    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("sso_saml_login_start")
        if url != "/sso/saml/login/start/":
            _fail("t2-url-shape", url)
        _ok(f"t2-URL route resolves: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] OneRoster ?filter= parenthesized nesting")
    from apps.api.oneroster_filter import apply_filter, parse_filter

    rows = [
        {"sid": "a", "status": "active",   "role": "student"},
        {"sid": "b", "status": "active",   "role": "teacher"},
        {"sid": "c", "status": "inactive", "role": "student"},
        {"sid": "d", "status": "inactive", "role": "teacher"},
    ]

    # Parens override precedence.
    # Without parens: status='active' OR status='inactive' AND role='student'
    #               = status='active' OR (status='inactive' AND role='student')
    #               -> a, b, c
    out = apply_filter(rows, "status='active' OR status='inactive' AND role='student'")
    if [r["sid"] for r in out] != ["a", "b", "c"]:
        _fail("t3-flat-precedence", f"got {[r['sid'] for r in out]}")
    _ok("t3-flat unparenthesized: a OR b AND c -> a, (b AND c) backward-compat preserved")

    # With parens: (status='active' OR status='inactive') AND role='student'
    #            -> a, c
    out = apply_filter(rows, "(status='active' OR status='inactive') AND role='student'")
    if [r["sid"] for r in out] != ["a", "c"]:
        _fail("t3-parens-override", f"got {[r['sid'] for r in out]}")
    _ok("t3-parens (a OR b) AND c -> a, c (overrides flat precedence)")

    # Nested parens.
    out = apply_filter(rows, "((status='active') AND (role='student' OR role='teacher'))")
    if {r["sid"] for r in out} != {"a", "b"}:
        _fail("t3-nested", f"got {[r['sid'] for r in out]}")
    _ok("t3-nested ((a) AND (b OR c)) -> a, b")

    # Single-paren wrap is identity.
    out = apply_filter(rows, "(role='student')")
    if {r["sid"] for r in out} != {"a", "c"}:
        _fail("t3-single-wrap", f"got {[r['sid'] for r in out]}")
    _ok("t3-single (role='student') === role='student'")

    # Unbalanced parens -> always-true (fail-safe).
    out = apply_filter(rows, "(status='active' AND role='student'")
    if len(out) != 4:
        _fail("t3-unbalanced", f"expected fail-safe (4 rows); got {len(out)}")
    _ok("t3-unbalanced fail-safe -> all rows pass")

    # Back-compat: v4.00.66 grammar still works unchanged.
    out = apply_filter(rows, "status='active' AND role='teacher'")
    if [r["sid"] for r in out] != ["b"]:
        _fail("t3-backcompat-AND", f"got {[r['sid'] for r in out]}")
    out = apply_filter(rows, "status='active' OR role='teacher'")
    if {r["sid"] for r in out} != {"a", "b", "d"}:
        _fail("t3-backcompat-OR", f"got {[r['sid'] for r in out]}")
    _ok("t3-backcompat flat AND / OR still produce v4.00.66-identical results")

    # Empty expr -> always-true.
    out = apply_filter(rows, "")
    if len(out) != 4:
        _fail("t3-empty", f"got {len(out)}")
    _ok("t3-empty filter -> all 4 rows pass")

    # Deeply nested 3-level.
    out = apply_filter(rows, "((status='active' OR status='inactive') AND (role='student' OR role='teacher'))")
    if len(out) != 4:
        _fail("t3-deep", f"got {len(out)}")
    _ok("t3-deep 3-level nested expression evaluates to all 4 rows")


def run_t4():
    _line("\n[T4] Demographics stateOfBirthAbbreviation ISO 3166-2 validation")
    from apps.api import oneroster_demographics as odm

    # Missing/empty accepted.
    if odm._validate_state_of_birth_abbreviation({}) is not None:
        _fail("t4-missing", "expected None")
    if odm._validate_state_of_birth_abbreviation({"stateOfBirthAbbreviation": ""}) is not None:
        _fail("t4-empty", "expected None")
    _ok("t4-state missing + empty -> None (explicit clear)")

    # Shape check fails for 4+ chars / special chars.
    for bad in ("CALIF", "X-Y", "@#$"):
        err = odm._validate_state_of_birth_abbreviation({"stateOfBirthAbbreviation": bad})
        if err is None or err.status_code != 400:
            _fail(f"t4-state-bad-shape-{bad}", f"expected 400; got {err}")
        body = _json.loads(err.content)
        if body.get("reason") != "bad_shape":
            _fail(f"t4-state-bad-shape-reason-{bad}", f"got {body}")
    _ok("t4-state bad shape -> 400 bad_shape (4+ chars, special chars rejected)")

    # Well-shaped, no country -> accept (permissive partial-update).
    err = odm._validate_state_of_birth_abbreviation({"stateOfBirthAbbreviation": "CA"})
    if err is not None:
        _fail("t4-state-no-country", f"got {err}")
    _ok("t4-state no countryOfBirthCode supplied -> shape-only accept")

    # Scoped: US-CA exists -> accept.
    err = odm._validate_state_of_birth_abbreviation({
        "countryOfBirthCode": "US",
        "stateOfBirthAbbreviation": "CA",
    })
    if err is not None:
        _fail("t4-state-us-ca", f"got {err}")
    _ok("t4-state US + CA -> accepted (US-CA in SOT)")

    # JP + 13 (Tokyo) exists -> accept.
    err = odm._validate_state_of_birth_abbreviation({
        "countryOfBirthCode": "JP",
        "stateOfBirthAbbreviation": "13",
    })
    if err is not None:
        _fail("t4-state-jp-13", f"got {err}")
    _ok("t4-state JP + 13 (Tokyo) -> accepted (numeric subdivision)")

    # US + ZZ -> not in SOT -> 400 not_in_iso_3166_2.
    err = odm._validate_state_of_birth_abbreviation({
        "countryOfBirthCode": "US",
        "stateOfBirthAbbreviation": "ZZ",
    })
    if err is None or err.status_code != 400:
        _fail("t4-state-us-zz", f"got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "not_in_iso_3166_2":
        _fail("t4-state-us-zz-reason", f"got {body}")
    _ok("t4-state US + ZZ -> 400 not_in_iso_3166_2 (well-shaped but not US-ZZ in SOT)")

    # Case-insensitive: us + ca -> accepted.
    err = odm._validate_state_of_birth_abbreviation({
        "countryOfBirthCode": "us",
        "stateOfBirthAbbreviation": "ca",
    })
    if err is not None:
        _fail("t4-state-case", f"got {err}")
    _ok("t4-state us + ca (lowercase) -> accepted (case-insensitive scope+match)")

    # Country w/ no subdivisions in SOT -> shape-only accept (defensive).
    err = odm._validate_state_of_birth_abbreviation({
        "countryOfBirthCode": "BB",  # Barbados — country-level only
        "stateOfBirthAbbreviation": "XX",
    })
    if err is not None:
        _fail("t4-state-bb-xx", f"got {err}")
    _ok("t4-state BB + XX (country w/o subdivisions in SOT) -> shape-only accept")


def run_t5():
    _line("\n[T5] Retention preview sparkline by-week")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    from django.utils import timezone as _tz
    from datetime import timedelta

    rf = RequestFactory()
    user = _staff_user()

    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    # No cutoff_dt -> empty buckets, all zero totals.
    sl = vld._retention_purge_sparkline(cutoff_dt=None)
    if sl["buckets"] != [] or sl["before_total"] != 0 or sl["after_total"] != 0:
        _fail("t5-spark-none", f"got {sl}")
    _ok("t5-sparkline cutoff_dt=None -> empty buckets shape")

    # Empty table, real cutoff -> 24 zero buckets.
    now = _tz.now()
    cutoff = now - timedelta(weeks=2)  # 2 weeks ago
    sl = vld._retention_purge_sparkline(cutoff_dt=cutoff, now=now)
    if len(sl["buckets"]) != 24:
        _fail("t5-spark-empty-len", f"got {len(sl['buckets'])}")
    if sl["max_count"] != 0:
        _fail("t5-spark-empty-max", f"got {sl['max_count']}")
    if any(b["count"] != 0 for b in sl["buckets"]):
        _fail("t5-spark-empty-counts", "expected all-zero")
    if sl["weeks_per_side"] != 12:
        _fail("t5-spark-weeks", f"got {sl['weeks_per_side']}")
    _ok("t5-sparkline empty table -> 24 zero buckets (12 before + 12 after)")

    # Seed rows: 5 in "before" range (older than cutoff) + 3 in "after" range.
    for i in range(5):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_refresh", provider="canvas",
            actor_hash="aaa", actor_user_id="1",
            considered=1, ok_count=1, failed_count=0,
        )
        # 4 weeks before cutoff so they land in week-index N (varies by i but
        # all are before cutoff -> "before" side).
        ts = cutoff - timedelta(weeks=4, days=i)
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke
    for i in range(3):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_rotate", provider="moodle",
            actor_hash="bbb", actor_user_id="2",
            considered=1, ok_count=1, failed_count=0,
        )
        ts = cutoff + timedelta(weeks=2, days=i)
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke

    sl = vld._retention_purge_sparkline(cutoff_dt=cutoff, now=now)
    if sl["before_total"] != 5:
        _fail("t5-spark-before", f"got {sl['before_total']}")
    if sl["after_total"] != 3:
        _fail("t5-spark-after", f"got {sl['after_total']}")
    if sl["max_count"] < 1:
        _fail("t5-spark-max", f"got {sl}")
    # Half the buckets are "before", half are "after".
    before_count = sum(1 for b in sl["buckets"] if b["side"] == "before")
    after_count = sum(1 for b in sl["buckets"] if b["side"] == "after")
    if before_count != 12 or after_count != 12:
        _fail("t5-spark-sides", f"got before={before_count} after={after_count}")
    _ok(f"t5-sparkline before_total=5, after_total=3, 12/12 bucket sides")

    # Pre-computed SVG geometry attached.
    for b in sl["buckets"]:
        for key in ("x", "bar_h", "bar_y"):
            if key not in b:
                _fail(f"t5-spark-svg-key-{key}", "missing")
    if sl["viewbox_width"] != 288 or sl["viewbox_height"] != 60:
        _fail("t5-spark-viewbox", f"got {sl}")
    if sl["divider_x"] != 144:
        _fail("t5-spark-divider", f"got {sl}")
    _ok("t5-sparkline buckets carry pre-computed SVG geometry (x, bar_h, bar_y) + viewbox metadata")

    # Wire through to JSON preview.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    body = _json.loads(resp.content)
    if "sparkline" not in body:
        _fail("t5-preview-json-key", "missing sparkline key")
    if "buckets" not in body["sparkline"]:
        _fail("t5-preview-json-buckets", f"got {body['sparkline']}")
    _ok("t5-preview JSON variant carries sparkline.buckets")

    # Wire through to HTML preview (SVG markers present).
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-preview-html-status", f"got {resp.status_code}")
    body_html = resp.content.decode("utf-8")
    for required in ("<svg", "Row distribution by week", "Before total", "After total", "cutoff"):
        if required not in body_html:
            _fail(f"t5-preview-html-missing-{required[:30]}", "absent")
    _ok(f"t5-preview HTML carries SVG + before/after totals + cutoff marker ({len(body_html)} bytes)")

    # Cleanup.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    _ok("t5-cleanup rows + ring cleared")


def main():
    run_t1()
    run_t2()
    run_t3()
    run_t4()
    run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(2)
