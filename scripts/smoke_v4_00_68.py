"""v4.00.68 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (JP-43/45, KR-30/28/29, TW-TPE/KHH, AR-X/S,
    CL-VS, CO-ANT, TH-50, ID-JI, PH-CEB); SOT >= 482.
T2: SAML LoginInitiator UX surface — resolve_saml_login_initiator helper
    + login_initiator_context processor + login.html button block.
T3: OneRoster ?filter= NOT unary operator — NOT > AND > OR precedence,
    binds to single factor, double-negation works, NOT (a OR b)
    flips the whole group.
T4: Demographics cityOfBirth length + charset validation —
    _validate_city_of_birth chained after stateOfBirthAbbreviation;
    >120 chars / control chars rejected with 400.
T5: Retention sparkline embedded in CSV gzip export — ?format=csv on
    retention preview view returns gzipped CSV with #summary block +
    bucket rows + sparkline geometry.

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import gzip as _gzip
import io as _io
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
        username="smoke-v4-00-68-staff",
        defaults={"email": "smoke@v4-00-68.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "JP-43", "JP-45",
        "KR-30", "KR-28", "KR-29",
        "TW-TPE", "TW-KHH",
        "AR-X", "AR-S",
        "CL-VS", "CO-ANT",
        "TH-50", "ID-JI", "PH-CEB",
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
    if len(COUNTRY_LOCALIZATION) < 482:
        _fail("t1-sot-count", f"expected >= 482, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] SAML LoginInitiator UX surface")
    from apps.api import saml as saml_mod
    rf = RequestFactory()

    # No env -> available=False, button gated off.
    os.environ.pop("RMC_SAML_IDP_SSO_URL", None)
    req = rf.get("/auth/login/")
    shape = saml_mod.resolve_saml_login_initiator(req)
    if shape["available"] is not False:
        _fail("t2-available-off", f"got {shape}")
    if "start_url" not in shape or "label" not in shape:
        _fail("t2-shape-keys", f"got {shape}")
    _ok("t2-no env -> available=False (button gated off)")

    # Env set -> available=True.
    os.environ["RMC_SAML_IDP_SSO_URL"] = "https://idp.example/sso"
    try:
        shape = saml_mod.resolve_saml_login_initiator(req)
        if shape["available"] is not True:
            _fail("t2-available-on", f"got {shape}")
        if not shape["start_url"].startswith("/sso/saml/login/start/"):
            _fail("t2-start-url", shape["start_url"])
        if not shape["label"]:
            _fail("t2-label", "empty")
        _ok(f"t2-env set -> available=True, label={shape['label']!r}")

        # ?next= carried through into start_url.
        shape = saml_mod.resolve_saml_login_initiator(req, next_url="/portal/dashboard/")
        if "next=%2Fportal%2Fdashboard%2F" not in shape["start_url"]:
            _fail("t2-next-passthrough", shape["start_url"])
        _ok("t2-next= URL-encoded into start_url")

        # Open-redirect defense: //evil dropped from start_url.
        shape = saml_mod.resolve_saml_login_initiator(req, next_url="//evil.example/")
        if "next=" in shape["start_url"]:
            _fail("t2-next-open-redirect", shape["start_url"])
        shape = saml_mod.resolve_saml_login_initiator(req, next_url="https://evil.example/")
        if "next=" in shape["start_url"]:
            _fail("t2-next-absolute-url", shape["start_url"])
        _ok("t2-//external and absolute next= dropped (open-redirect defense)")

        # Custom label via env.
        os.environ["RMC_SAML_LOGIN_BUTTON_LABEL"] = "Sign in with Okta"
        try:
            shape = saml_mod.resolve_saml_login_initiator(req)
            if shape["label"] != "Sign in with Okta":
                _fail("t2-label-env", shape["label"])
            _ok("t2-RMC_SAML_LOGIN_BUTTON_LABEL env overrides default label")
        finally:
            os.environ.pop("RMC_SAML_LOGIN_BUTTON_LABEL", None)

        # Context processor.
        req2 = rf.get("/auth/login/?next=/portal/dashboard/")
        ctx = saml_mod.login_initiator_context(req2)
        if "saml_login_initiator" not in ctx:
            _fail("t2-ctx-key", f"got {ctx}")
        if ctx["saml_login_initiator"]["available"] is not True:
            _fail("t2-ctx-available", f"got {ctx}")
        if "next=%2Fportal%2Fdashboard%2F" not in ctx["saml_login_initiator"]["start_url"]:
            _fail("t2-ctx-next", ctx)
        _ok("t2-login_initiator_context yields saml_login_initiator w/ next= passthrough")

        # Context processor NEVER raises.
        class _BadReq:
            GET = {}
        ctx = saml_mod.login_initiator_context(_BadReq())
        if "saml_login_initiator" not in ctx:
            _fail("t2-ctx-defensive", f"got {ctx}")
        _ok("t2-login_initiator_context never raises (defensive)")
    finally:
        os.environ.pop("RMC_SAML_IDP_SSO_URL", None)

    # Template carries the SSO button block.
    tpl_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "auth", "login.html",
    )
    with open(tpl_path, "r", encoding="utf-8") as fh:
        tpl = fh.read()
    for needle in (
        "saml_login_initiator.available",
        "saml_login_initiator.start_url",
        "saml_login_initiator.label",
        "data-rmc-saml-sso-button",
    ):
        if needle not in tpl:
            _fail(f"t2-tpl-missing-{needle}", "absent")
    _ok("t2-templates/auth/login.html carries SAML LoginInitiator block + 4 hooks")


def run_t3():
    _line("\n[T3] OneRoster ?filter= NOT unary operator")
    from apps.api.oneroster_filter import apply_filter, parse_filter

    rows = [
        {"sid": "a", "status": "active",   "role": "student"},
        {"sid": "b", "status": "active",   "role": "teacher"},
        {"sid": "c", "status": "inactive", "role": "student"},
        {"sid": "d", "status": "inactive", "role": "teacher"},
    ]

    # NOT before predicate.
    out = apply_filter(rows, "NOT status='active'")
    if {r["sid"] for r in out} != {"c", "d"}:
        _fail("t3-not-pred", f"got {[r['sid'] for r in out]}")
    _ok("t3-NOT status='active' -> {c, d} (negates predicate)")

    # NOT before parenthesized group.
    out = apply_filter(rows, "NOT (status='active' OR role='teacher')")
    if {r["sid"] for r in out} != {"c"}:
        _fail("t3-not-group", f"got {[r['sid'] for r in out]}")
    _ok("t3-NOT (a OR b) -> single row (negates whole group)")

    # NOT > AND > OR precedence: `NOT a AND b` = `(NOT a) AND b`
    # NOT status='active' AND role='student' -> rows where status != active AND role=student -> c
    out = apply_filter(rows, "NOT status='active' AND role='student'")
    if {r["sid"] for r in out} != {"c"}:
        _fail("t3-not-precedence", f"got {[r['sid'] for r in out]}")
    _ok("t3-NOT a AND b -> (NOT a) AND b (precedence: NOT > AND)")

    # Double negation: NOT NOT x === x.
    out = apply_filter(rows, "NOT NOT status='active'")
    if {r["sid"] for r in out} != {"a", "b"}:
        _fail("t3-not-not", f"got {[r['sid'] for r in out]}")
    _ok("t3-NOT NOT status='active' -> identity ({a, b})")

    # NOT combined with OR.
    out = apply_filter(rows, "NOT role='student' OR status='inactive'")
    # NOT role=student -> {b, d}; status='inactive' -> {c, d}; OR -> {b, c, d}
    if {r["sid"] for r in out} != {"b", "c", "d"}:
        _fail("t3-not-or", f"got {[r['sid'] for r in out]}")
    _ok("t3-NOT a OR b composes correctly")

    # NOT at top of nested expr.
    out = apply_filter(rows, "(NOT status='active') AND (NOT role='student')")
    if {r["sid"] for r in out} != {"d"}:
        _fail("t3-not-double-paren", f"got {[r['sid'] for r in out]}")
    _ok("t3-(NOT a) AND (NOT b) -> single intersection row")

    # v4.00.66/.67 back-compat: flat AND/OR + parens still work.
    out = apply_filter(rows, "status='active' AND role='teacher'")
    if [r["sid"] for r in out] != ["b"]:
        _fail("t3-backcompat-AND", f"got {[r['sid'] for r in out]}")
    out = apply_filter(rows, "(status='active' OR status='inactive') AND role='student'")
    if [r["sid"] for r in out] != ["a", "c"]:
        _fail("t3-backcompat-parens", f"got {[r['sid'] for r in out]}")
    _ok("t3-backcompat v4.00.66 flat AND + v4.00.67 parens still work identically")

    # Truncated NOT (NOT with nothing after) -> fail-safe always-True.
    out = apply_filter(rows, "NOT")
    if len(out) != 4:
        _fail("t3-not-truncated", f"got {len(out)}")
    _ok("t3-NOT alone -> fail-safe (4 rows, parse_error swallowed)")


def run_t4():
    _line("\n[T4] Demographics cityOfBirth length + charset validation")
    from apps.api import oneroster_demographics as odm

    # Missing accepted.
    if odm._validate_city_of_birth({}) is not None:
        _fail("t4-missing", "expected None")
    # Empty allowed (explicit clear).
    if odm._validate_city_of_birth({"cityOfBirth": ""}) is not None:
        _fail("t4-empty", "expected None")
    _ok("t4-city missing + empty -> None (explicit clear)")

    # Normal city names accepted incl. unicode + punctuation.
    for city in (
        "Lagos",
        "São Paulo",
        "Washington, D.C.",
        "St. John's",
        "Stratford-upon-Avon",
        "New York (Manhattan)",
        "Saint-Étienne",
    ):
        err = odm._validate_city_of_birth({"cityOfBirth": city})
        if err is not None:
            _fail(f"t4-good-{city}", f"got {err.content}")
    _ok("t4-7 real-world city names (unicode + punctuation) all accepted")

    # 120-char boundary: exactly 120 OK, 121 rejected.
    boundary = "a" * 120
    if odm._validate_city_of_birth({"cityOfBirth": boundary}) is not None:
        _fail("t4-boundary-120", "120 chars should accept")
    overflow = "a" * 121
    err = odm._validate_city_of_birth({"cityOfBirth": overflow})
    if err is None or err.status_code != 400:
        _fail("t4-overflow-121", f"expected 400; got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "too_long":
        _fail("t4-overflow-reason", f"got {body}")
    if body.get("received_length") != 121:
        _fail("t4-overflow-len", f"got {body}")
    _ok("t4-boundary 120 OK, 121 -> 400 too_long (received_length echoed)")

    # Control character rejected.
    for bad in ("Lagos\x00null", "São\x09Paulo", "Bad\nLine", "Bad\rLine"):
        err = odm._validate_city_of_birth({"cityOfBirth": bad})
        if err is None or err.status_code != 400:
            _fail(f"t4-ctrl-{bad!r}", f"expected 400; got {err}")
        body = _json.loads(err.content)
        if body.get("reason") != "control_chars":
            _fail(f"t4-ctrl-reason-{bad!r}", f"got {body}")
    _ok("t4-control chars (NUL, TAB, LF, CR) all -> 400 control_chars")

    # C1 control char (U+0085) rejected.
    err = odm._validate_city_of_birth({"cityOfBirth": "LagosTrailer"})
    if err is None or err.status_code != 400:
        _fail("t4-c1-ctrl", f"got {err}")
    _ok("t4-C1 control char (U+0085) -> 400 control_chars")

    # End-to-end via _parse_demographic_payload — control char + 121 fail.
    body_bytes = _json.dumps({"demographic": {"cityOfBirth": "Bad\x00City"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is None or err.status_code != 400:
        _fail("t4-e2e-ctrl", f"expected 400; got {err}")
    _ok("t4-_parse_demographic_payload rejects control-char city w/ 400")

    body_bytes = _json.dumps({"demographic": {"cityOfBirth": "A" * 150}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is None or err.status_code != 400:
        _fail("t4-e2e-overflow", f"expected 400; got {err}")
    _ok("t4-_parse_demographic_payload rejects 150-char city w/ 400 too_long")

    # End-to-end happy path.
    body_bytes = _json.dumps({"demographic": {"cityOfBirth": "Lagos"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None or inner is None or inner.get("cityOfBirth") != "Lagos":
        _fail("t4-e2e-happy", f"got inner={inner} err={err}")
    _ok("t4-_parse_demographic_payload accepts valid city + returns inner dict")


def run_t5():
    _line("\n[T5] Retention sparkline embedded in CSV gzip export")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    from django.utils import timezone as _tz
    from datetime import timedelta

    rf = RequestFactory()
    user = _staff_user()

    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    # Helper to gzip-decompress the CSV body.
    def _csv_lines(resp):
        gz = _io.BytesIO(resp.content)
        with _gzip.GzipFile(fileobj=gz, mode="rb") as fh:
            text = fh.read().decode("utf-8")
        return text, text.splitlines()

    # Empty table at 7y window — CSV emits summary + header + 24 zero rows.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=csv&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-csv-status", f"got {resp.status_code}")
    if resp["Content-Type"] != "text/csv":
        _fail("t5-csv-content-type", resp["Content-Type"])
    if resp["Content-Encoding"] != "gzip":
        _fail("t5-csv-encoding", resp["Content-Encoding"])
    if "attachment" not in resp["Content-Disposition"]:
        _fail("t5-csv-disposition", resp["Content-Disposition"])
    if "lms_diag_retention_preview_" not in resp["Content-Disposition"]:
        _fail("t5-csv-filename", resp["Content-Disposition"])
    text, lines = _csv_lines(resp)
    if "#summary" not in text:
        _fail("t5-csv-summary-marker", "missing")
    if "week_start_iso,side,count,x,bar_h,bar_y" not in text:
        _fail("t5-csv-header-row", text[:300])
    # 9 summary rows + 1 blank + 1 header + 24 buckets = 35 lines.
    if len(lines) < 9:
        _fail("t5-csv-empty-lines", f"got {len(lines)} lines")
    _ok(f"t5-csv ?format=csv emits gzipped CSV w/ #summary + header + buckets ({len(lines)} lines)")

    # X-headers carry totals.
    if resp.get("X-Retention-Sparkline-Bucket-Count") is None:
        _fail("t5-csv-x-headers", "missing X-Retention-Sparkline-Bucket-Count")
    _ok(f"t5-csv X-headers: bucket-count={resp['X-Retention-Sparkline-Bucket-Count']}, "
        f"before-total={resp['X-Retention-Before-Total']}, after-total={resp['X-Retention-After-Total']}")

    # Seed real data and verify CSV reflects it.
    now = _tz.now()
    # Want cutoff that lands rows in the window. 7y retention -> cutoff is
    # 7y ago. Seed rows around that cutoff.
    cutoff = now - timedelta(weeks=52 * 7)
    for i in range(3):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_refresh", provider="canvas",
            actor_hash="aaa", actor_user_id="1",
            considered=1, ok_count=1, failed_count=0,
        )
        ts = cutoff - timedelta(weeks=2, days=i)
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke
    for i in range(2):
        r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
            action="force_rotate", provider="moodle",
            actor_hash="bbb", actor_user_id="2",
            considered=1, ok_count=1, failed_count=0,
        )
        ts = cutoff + timedelta(weeks=1, days=i)
        LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke

    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=csv&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    text, lines = _csv_lines(resp)
    if "#summary,before_total,3" not in text:
        _fail("t5-csv-before-total", f"missing 3 in summary; got text head: {text[:500]}")
    if "#summary,after_total,2" not in text:
        _fail("t5-csv-after-total", f"missing 2 in summary; got text head: {text[:500]}")
    # Verify at least one bucket row carries a non-zero count.
    bucket_rows = [ln for ln in lines if ln and not ln.startswith("#") and not ln.startswith("week_start_iso") and ln.count(",") == 5]
    nonzero = [ln for ln in bucket_rows if ln.split(",")[2] not in ("0", "")]
    if not nonzero:
        _fail("t5-csv-nonzero", f"no nonzero buckets in {len(bucket_rows)} rows")
    _ok(f"t5-csv reflects 3 before + 2 after totals; {len(nonzero)} non-zero bucket rows")

    # Verify the HTML preview surfaces the CSV link.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-html-status", f"got {resp.status_code}")
    html = resp.content.decode("utf-8")
    if "?format=csv" not in html:
        _fail("t5-html-csv-link", "missing CSV link")
    if "data-rmc-retention-sparkline-csv" not in html:
        _fail("t5-html-csv-marker", "missing marker attr")
    _ok("t5-HTML preview footer carries ?format=csv download link")

    # Confirm JSON shape is unaffected (back-compat).
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    body = _json.loads(resp.content)
    if "sparkline" not in body:
        _fail("t5-json-backcompat", "missing sparkline")
    if "buckets" not in body["sparkline"]:
        _fail("t5-json-buckets", "missing buckets in sparkline")
    _ok("t5-JSON ?format=json shape preserved (v4.00.67 back-compat)")

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
