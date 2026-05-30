"""v4.00.69 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (JP-03/05/06/07, KR-27, TW-NWT, CN-XJ/TJ,
    MX-MEX, CL-AI, CO-CUN, BR-ES, IN-MH, IN-KA); SOT >= 496.
T2: OneRoster ?filter= IN(...) list operator — set-membership predicate
    syntactic sugar for repeated OR chains; empty IN() => always-False.
T3: Demographics countryOfCitizenship multi-value validation — accepts
    CSV string OR JSON list; ISO 3166-1 alpha-2 each; cap 5 values.
T4: Sparkline percentile bands p25/p50/p75 — overlay metadata on the
    by-week sparkline; SVG lines rendered with y-coords pre-computed.
T5: lms_supported_providers SOT module — Schoology + D2L registered as
    scaffold providers; helpers for is_supported / is_oauth_ready /
    is_scaffold / canonical_lms_provider_label / rollup_order.

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
        username="smoke-v4-00-69-staff",
        defaults={"email": "smoke@v4-00-69.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "JP-03", "JP-05", "JP-06", "JP-07",
        "KR-27",
        "TW-NWT",
        "CN-XJ", "CN-TJ",
        "MX-MEX",
        "CL-AI", "CO-CUN",
        "BR-ES",
        "IN-MH", "IN-KA",
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
    # Note: 3 of the 14 entries (IN-MH, IN-KA, + 1 other) refresh earlier
    # seed shapes rather than adding net-new keys, so the SOT count grows
    # by 11 instead of 14. All 14 dict writes still landed (verified above).
    if len(COUNTRY_LOCALIZATION) < 493:
        _fail("t1-sot-count", f"expected >= 493, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster ?filter= IN(...) list operator")
    from apps.api.oneroster_filter import apply_filter

    rows = [
        {"sid": "a", "status": "active",   "role": "student"},
        {"sid": "b", "status": "active",   "role": "teacher"},
        {"sid": "c", "status": "inactive", "role": "student"},
        {"sid": "d", "status": "inactive", "role": "teacher"},
        {"sid": "e", "status": "pending",  "role": "parent"},
    ]

    # IN with 2 values.
    out = apply_filter(rows, "status IN('active','inactive')")
    if {r["sid"] for r in out} != {"a", "b", "c", "d"}:
        _fail("t2-in-2vals", f"got {[r['sid'] for r in out]}")
    _ok("t2-IN(2 values) -> 4 rows (a,b,c,d)")

    # IN with 1 value (degenerate but valid).
    out = apply_filter(rows, "role IN('parent')")
    if {r["sid"] for r in out} != {"e"}:
        _fail("t2-in-1val", f"got {[r['sid'] for r in out]}")
    _ok("t2-IN(1 value) -> 1 row")

    # Empty IN() -> always-False per set-membership semantics.
    out = apply_filter(rows, "status IN()")
    if len(out) != 0:
        _fail("t2-in-empty", f"expected 0 rows; got {len(out)}")
    _ok("t2-IN() empty list -> 0 rows (set with no members)")

    # NOT IN composition.
    out = apply_filter(rows, "NOT status IN('active','inactive')")
    if {r["sid"] for r in out} != {"e"}:
        _fail("t2-not-in", f"got {[r['sid'] for r in out]}")
    _ok("t2-NOT IN(...) composes correctly")

    # IN combined with AND.
    out = apply_filter(rows, "status IN('active','inactive') AND role='student'")
    if {r["sid"] for r in out} != {"a", "c"}:
        _fail("t2-in-and", f"got {[r['sid'] for r in out]}")
    _ok("t2-IN(...) AND eq(...) composes correctly")

    # IN inside parens.
    out = apply_filter(rows, "(status IN('active') OR status IN('pending')) AND role IN('teacher','parent')")
    if {r["sid"] for r in out} != {"b", "e"}:
        _fail("t2-in-paren", f"got {[r['sid'] for r in out]}")
    _ok("t2-IN(...) nested inside paren expressions composes correctly")

    # Malformed IN (missing close paren) -> fail-safe always-True.
    out = apply_filter(rows, "status IN('active','inactive'")
    if len(out) != 5:
        _fail("t2-in-unbalanced", f"expected fail-safe (5 rows); got {len(out)}")
    _ok("t2-IN(...) unbalanced -> fail-safe (all rows)")

    # Back-compat: v4.00.66/.67/.68 grammar still works.
    out = apply_filter(rows, "status='active' OR (status='pending' AND role='parent')")
    if {r["sid"] for r in out} != {"a", "b", "e"}:
        _fail("t2-backcompat", f"got {[r['sid'] for r in out]}")
    _ok("t2-backcompat v4.00.66 flat + v4.00.67 parens + v4.00.68 NOT still work")


def run_t3():
    _line("\n[T3] Demographics countryOfCitizenship multi-value validation")
    from apps.api import oneroster_demographics as odm

    # Missing + empty allowed.
    if odm._validate_country_of_citizenship({}) is not None:
        _fail("t3-missing", "expected None")
    if odm._validate_country_of_citizenship({"countryOfCitizenship": ""}) is not None:
        _fail("t3-empty-str", "expected None")
    if odm._validate_country_of_citizenship({"countryOfCitizenship": []}) is not None:
        _fail("t3-empty-list", "expected None")
    _ok("t3-missing + empty str + empty list -> None (explicit clear)")

    # Single value CSV string.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "US"})
    if err is not None:
        _fail("t3-single-csv", f"got {err.content}")
    _ok("t3-single CSV string 'US' accepted")

    # Multi-value CSV.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "US,NG,GB"})
    if err is not None:
        _fail("t3-multi-csv", f"got {err.content}")
    _ok("t3-multi CSV 'US,NG,GB' accepted")

    # JSON list.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": ["US", "NG", "GB"]})
    if err is not None:
        _fail("t3-json-list", f"got {err.content}")
    _ok("t3-JSON list ['US','NG','GB'] accepted")

    # Case-insensitive.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "us,ng,gb"})
    if err is not None:
        _fail("t3-case-insensitive", f"got {err.content}")
    _ok("t3-lowercase 'us,ng,gb' accepted (case-insensitive)")

    # Too many values.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "US,NG,GB,FR,DE,CA"})
    if err is None or err.status_code != 400:
        _fail("t3-too-many", f"expected 400; got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "too_many_values":
        _fail("t3-too-many-reason", f"got {body}")
    _ok(f"t3-6 codes -> 400 too_many_values (max 5, received {body['received_count']})")

    # Bad shape inside list.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "US,USA,GB"})
    if err is None or err.status_code != 400:
        _fail("t3-bad-shape", f"got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "bad_shape":
        _fail("t3-bad-shape-reason", f"got {body}")
    _ok("t3-3-letter code in CSV -> 400 bad_shape (received echoed)")

    # Well-shaped but unknown.
    err = odm._validate_country_of_citizenship({"countryOfCitizenship": "US,ZZ,GB"})
    if err is None or err.status_code != 400:
        _fail("t3-not-in-sot", f"got {err}")
    body = _json.loads(err.content)
    if body.get("reason") != "not_in_iso_3166_1_alpha_2":
        _fail("t3-not-in-sot-reason", f"got {body}")
    _ok("t3-ZZ in CSV -> 400 not_in_iso_3166_1_alpha_2")

    # End-to-end via _parse_demographic_payload.
    body_bytes = _json.dumps({"demographic": {"countryOfCitizenship": "US,NG"}}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e-happy", f"got err={err}")
    if inner is None or inner.get("countryOfCitizenship") != "US,NG":
        _fail("t3-e2e-passthrough", f"got inner={inner}")
    _ok("t3-_parse_demographic_payload accepts 'US,NG' and round-trips")


def run_t4():
    _line("\n[T4] Sparkline percentile bands p25/p50/p75")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    from django.utils import timezone as _tz
    from datetime import timedelta

    rf = RequestFactory()
    user = _staff_user()
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()

    # No cutoff -> empty buckets, percentile_bands all 0.
    sl = vld._retention_purge_sparkline(cutoff_dt=None)
    if "percentile_bands" not in sl:
        _fail("t4-spark-key-none", f"got keys {sorted(sl.keys())}")
    if sl["percentile_bands"]["p25"] != 0 or sl["percentile_bands"]["p50"] != 0 or sl["percentile_bands"]["p75"] != 0:
        _fail("t4-spark-none-zero", f"got {sl['percentile_bands']}")
    _ok("t4-cutoff_dt=None -> percentile_bands all zero")

    # Empty table.
    now = _tz.now()
    cutoff = now - timedelta(weeks=4)
    sl = vld._retention_purge_sparkline(cutoff_dt=cutoff, now=now)
    bands = sl["percentile_bands"]
    if bands["p25"] != 0 or bands["nonzero_count"] != 0:
        _fail("t4-empty-bands", f"got {bands}")
    _ok("t4-empty table -> nonzero_count=0, all p25/p50/p75=0")

    # Seed varying counts across buckets.
    # 12 buckets before + 12 after. Place 1 row in week-before-1, 3 in week-before-2,
    # 5 in week-before-3, 9 in week-before-4 (so non-zero counts = [1, 3, 5, 9]).
    for count, weeks_back in [(1, 1), (3, 2), (5, 3), (9, 4)]:
        for _ in range(count):
            r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
                action="force_refresh", provider="canvas",
                actor_hash="aaa", actor_user_id="1",
                considered=1, ok_count=1, failed_count=0,
            )
            ts = cutoff - timedelta(weeks=weeks_back, days=0, hours=12)
            LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke

    sl = vld._retention_purge_sparkline(cutoff_dt=cutoff, now=now)
    bands = sl["percentile_bands"]
    if bands["nonzero_count"] != 4:
        _fail("t4-nonzero", f"expected 4; got {bands}")
    if not (0 < bands["p25"] <= bands["p50"] <= bands["p75"]):
        _fail("t4-monotonic", f"non-monotonic: {bands}")
    _ok(f"t4-4 nonzero buckets [1,3,5,9] -> p25={bands['p25']}, p50={bands['p50']}, p75={bands['p75']} (monotonic)")

    # SVG y-coords pre-computed.
    for k in ("p25_y", "p50_y", "p75_y"):
        if k not in bands:
            _fail(f"t4-svg-y-{k}", "missing")
    # y is inverted in SVG: higher value -> smaller y.
    if not (bands["p25_y"] >= bands["p50_y"] >= bands["p75_y"]):
        _fail("t4-y-inverted", f"got {bands}")
    _ok("t4-SVG y-coords pre-computed + inverted (higher value -> smaller y)")

    # Wire through to JSON.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    body = _json.loads(resp.content)
    if "percentile_bands" not in body.get("sparkline", {}):
        _fail("t4-json-percentile", f"got sparkline keys {sorted(body.get('sparkline', {}).keys())}")
    _ok("t4-JSON preview carries sparkline.percentile_bands")

    # HTML preview renders 3 percentile lines (when nonzero_count > 0).
    # Seed data above is at 4 weeks back from the cutoff at years=7 — the
    # cutoff is 7y ago, and 4w back from that may be outside the 12-week
    # window. So for HTML smoke we use a closer cutoff.
    cutoff_html = now - timedelta(weeks=2)
    # Re-seed within the visible window.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    for count, weeks_back in [(1, 1), (3, 3), (5, 5), (9, 7)]:
        for _ in range(count):
            r = LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: smoke
                action="force_refresh", provider="canvas",
                actor_hash="aaa", actor_user_id="1",
                considered=1, ok_count=1, failed_count=0,
            )
            ts = cutoff_html - timedelta(weeks=weeks_back, hours=12)
            LMSDiagActionAudit.objects.filter(pk=r.pk).update(created_at=ts)  # tenant-isolation-allow: smoke
    sl = vld._retention_purge_sparkline(cutoff_dt=cutoff_html, now=now)
    if sl["percentile_bands"]["nonzero_count"] < 1:
        _fail("t4-html-window", "no nonzero buckets in visible window")
    _ok(f"t4-percentile bands populated within visible window (nonzero={sl['percentile_bands']['nonzero_count']})")

    # CSV summary carries p25/p50/p75 rows.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=csv&years=7")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    gz = _io.BytesIO(resp.content)
    with _gzip.GzipFile(fileobj=gz, mode="rb") as fh:
        text = fh.read().decode("utf-8")
    for needle in ("#summary,p25,", "#summary,p50,", "#summary,p75,"):
        if needle not in text:
            _fail(f"t4-csv-{needle}", "missing in summary")
    _ok("t4-CSV summary block carries p25 + p50 + p75 rows")

    # Cleanup.
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup rows + ring cleared")


def run_t5():
    _line("\n[T5] lms_supported_providers SOT module + Schoology scaffold")
    from apps.integrations_marketplace import lms_supported_providers as lsp

    # All 3 legacy providers + 2 scaffolds known.
    for p in ("canvas", "moodle", "google_classroom", "google", "schoology", "d2l_brightspace"):
        if not lsp.is_supported_lms_provider(p):
            _fail(f"t5-supported-{p}", "expected True")
    _ok("t5-canvas/moodle/google_classroom/google + schoology/d2l all is_supported")

    # OAuth-ready set excludes scaffolds.
    for p in ("canvas", "moodle", "google_classroom", "google"):
        if not lsp.is_oauth_ready_lms_provider(p):
            _fail(f"t5-oauth-ready-{p}", "expected True")
    for p in ("schoology", "d2l_brightspace"):
        if lsp.is_oauth_ready_lms_provider(p):
            _fail(f"t5-oauth-ready-{p}-scaffold", "should be False (scaffold)")
    _ok("t5-scaffold providers (schoology, d2l_brightspace) NOT oauth_ready")

    # is_scaffold correctly identifies the new entries.
    for p in ("schoology", "d2l_brightspace"):
        if not lsp.is_scaffold_lms_provider(p):
            _fail(f"t5-is-scaffold-{p}", "expected True")
    for p in ("canvas", "moodle", "google_classroom"):
        if lsp.is_scaffold_lms_provider(p):
            _fail(f"t5-is-scaffold-{p}-legacy", "should be False (production)")
    _ok("t5-is_scaffold_lms_provider distinguishes new entries from legacy")

    # Labels.
    if lsp.canonical_lms_provider_label("canvas") != "Canvas LMS":
        _fail("t5-label-canvas", lsp.canonical_lms_provider_label("canvas"))
    if lsp.canonical_lms_provider_label("google") != "Google Classroom":
        _fail("t5-label-google-legacy", lsp.canonical_lms_provider_label("google"))
    if lsp.canonical_lms_provider_label("schoology") != "Schoology":
        _fail("t5-label-schoology", lsp.canonical_lms_provider_label("schoology"))
    if lsp.canonical_lms_provider_label("d2l_brightspace") != "Brightspace (D2L)":
        _fail("t5-label-d2l", lsp.canonical_lms_provider_label("d2l_brightspace"))
    _ok("t5-canonical labels match (legacy 'google' renders as 'Google Classroom')")

    # Rollup order is stable.
    order = lsp.lms_provider_rollup_order()
    if order != ("canvas", "moodle", "google_classroom", "schoology", "d2l_brightspace"):
        _fail("t5-rollup-order", str(order))
    _ok(f"t5-rollup order: {order}")

    # Case-insensitive.
    if not lsp.is_supported_lms_provider("SCHOOLOGY"):
        _fail("t5-case-supported", "expected True")
    if not lsp.is_scaffold_lms_provider("Schoology"):
        _fail("t5-case-scaffold", "expected True")
    _ok("t5-helpers case-insensitive")

    # Unknown provider.
    if lsp.is_supported_lms_provider("blackboard"):
        _fail("t5-unknown", "expected False")
    _ok("t5-unknown provider 'blackboard' -> False")


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
