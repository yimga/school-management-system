"""v4.00.73 smoke."""
from __future__ import annotations
import json as _json
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.test import RequestFactory  # noqa: E402


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def run_t1():
    _line("\n[T1] +14 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    keys = ["VN-CT","VN-DN","VN-HP","TH-13","TH-90","PH-MNL","ID-JB","ID-JT",
            "ID-BT","MY-10","SG-01","KH-12","LA-VT","NP-3"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 549:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster gradingPeriods convenience endpoint")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/grading-periods/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.grading_periods(req)
        if resp.status_code != 200:
            _fail("t2-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if "gradingPeriods" not in body:
            _fail("t2-envelope", str(body))
        for it in body.get("gradingPeriods", []):
            if it.get("type") != "gradingPeriod":
                _fail("t2-type", f"got {it.get('type')}")
        _ok(f"t2-/grading-periods/ envelope; n={len(body.get('gradingPeriods', []))}")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-grading-periods")
        if not url.endswith("/grading-periods/"):
            _fail("t2-url", url)
        _ok(f"t2-URL: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] nativeHawaiianOrOtherPacificIslander race flag")
    from apps.api import oneroster_demographics as odm
    if "nativeHawaiianOrOtherPacificIslander" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-registered", "missing")
    _ok(f"t3-{len(odm.RACE_ETHNICITY_BOOL_FIELDS)} flags now: {sorted(odm.RACE_ETHNICITY_BOOL_FIELDS)}")

    for v in (True, "true", "yes", "1", False, "false", "no", "0", ""):
        err = odm._validate_race_ethnicity_bool_flags({"nativeHawaiianOrOtherPacificIslander": v})
        if err is not None:
            _fail(f"t3-good-{v!r}", f"got {err.content}")
    _ok("t3-nativeHawaiian boolish + clear accepted")

    err = odm._validate_race_ethnicity_bool_flags({"nativeHawaiianOrOtherPacificIslander": "huh"})
    if err is None or err.status_code != 400:
        _fail("t3-bad", "expected 400")
    body = _json.loads(err.content)
    if body.get("field") != "nativeHawaiianOrOtherPacificIslander":
        _fail("t3-field-echo", str(body))
    _ok("t3-'huh' -> 400 not_boolish w/ field=nativeHawaiianOrOtherPacificIslander")


def run_t4():
    _line("\n[T4] build_diagnostics_forensic_export")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(course_id="_diag_action").delete()  # tenant-isolation-allow: smoke-cleanup
    except Exception:
        pass
    vld._LAST_ACTION_RING.clear()

    pkt = vld.build_diagnostics_forensic_export()
    for k in ("generated_at", "filters", "rollup_by_action", "entries", "entry_count"):
        if k not in pkt:
            _fail(f"t4-key-{k}", "missing")
    if pkt["entry_count"] != 0 or pkt["entries"] != []:
        _fail("t4-empty", str(pkt))
    _ok("t4-empty forensic export carries all 5 expected keys")

    # Seed.
    vld._LAST_ACTION_RING.extend([
        {"ts_iso": "2026-05-29T10:00:00Z", "action": "force_refresh",
         "provider": "canvas", "actor_hash": "aaa", "considered": 5, "ok": 5, "failed": 0},
        {"ts_iso": "2026-05-29T10:05:00Z", "action": "force_refresh",
         "provider": "moodle", "actor_hash": "aaa", "considered": 3, "ok": 2, "failed": 1},
        {"ts_iso": "2026-05-29T10:10:00Z", "action": "force_rotate",
         "provider": "canvas", "actor_hash": "bbb", "considered": 1, "ok": 1, "failed": 0},
    ])

    pkt = vld.build_diagnostics_forensic_export()
    if pkt["entry_count"] != 3:
        _fail("t4-count", str(pkt))
    if pkt["rollup_by_action"]["force_refresh"]["count"] != 2:
        _fail("t4-rollup-refresh", str(pkt["rollup_by_action"]))
    _ok(f"t4-unfiltered export entry_count={pkt['entry_count']} rollup_actions={list(pkt['rollup_by_action'].keys())}")

    # Filter by provider.
    pkt = vld.build_diagnostics_forensic_export(provider="canvas")
    if pkt["entry_count"] != 2:
        _fail("t4-provider-filter", f"got {pkt['entry_count']}")
    if pkt["filters"]["provider"] != "canvas":
        _fail("t4-filter-echo", str(pkt["filters"]))
    _ok(f"t4-provider=canvas filter -> {pkt['entry_count']} entries")

    # Filter by action.
    pkt = vld.build_diagnostics_forensic_export(action="force_rotate")
    if pkt["entry_count"] != 1:
        _fail("t4-action-filter", f"got {pkt['entry_count']}")
    _ok(f"t4-action=force_rotate filter -> {pkt['entry_count']} entries")

    # Both filters.
    pkt = vld.build_diagnostics_forensic_export(provider="canvas", action="force_refresh")
    if pkt["entry_count"] != 1:
        _fail("t4-both-filters", f"got {pkt['entry_count']}")
    _ok("t4-provider+action filters compose (AND)")

    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] 5-provider rollup card")
    from apps.integrations_marketplace import lms_supported_providers as lsp
    cards = lsp.lms_provider_rollup_card()
    if len(cards) != 5:
        _fail("t5-len", f"expected 5; got {len(cards)}")
    _ok(f"t5-rollup card has {len(cards)} providers")

    slugs = [c["slug"] for c in cards]
    if slugs != ["canvas", "moodle", "google_classroom", "schoology", "d2l_brightspace"]:
        _fail("t5-order", str(slugs))
    _ok("t5-slug order matches lms_provider_rollup_order()")

    for c in cards:
        for k in ("slug", "label", "maturity", "oauth_ready", "is_scaffold", "pill"):
            if k not in c:
                _fail(f"t5-key-{k}-{c['slug']}", str(c))
    _ok("t5-each card carries slug/label/maturity/oauth_ready/is_scaffold/pill")

    # Canvas is production; Schoology + D2L are scaffold.
    canvas = next(c for c in cards if c["slug"] == "canvas")
    if canvas["maturity"] != "production" or canvas["pill"] != "Production":
        _fail("t5-canvas-mat", str(canvas))
    _ok("t5-Canvas pill='Production' maturity='production'")

    sch = next(c for c in cards if c["slug"] == "schoology")
    if sch["maturity"] != "scaffold" or sch["pill"] != "Scaffold (coming soon)":
        _fail("t5-schoology-mat", str(sch))
    _ok("t5-Schoology pill='Scaffold (coming soon)' maturity='scaffold'")

    d2l = next(c for c in cards if c["slug"] == "d2l_brightspace")
    if d2l["label"] != "Brightspace (D2L)":
        _fail("t5-d2l-label", str(d2l))
    _ok("t5-D2L label='Brightspace (D2L)' (canonical_lms_provider_label propagated)")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
