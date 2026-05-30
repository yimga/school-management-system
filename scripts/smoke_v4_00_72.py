"""v4.00.72 smoke."""
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
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    keys = ["PE-LAL","PE-AQP","AR-N","AR-Z","EG-LX","ET-AA","MA-RBA","SN-DK",
            "ZW-HA","ZM-08","BW-GA","MZ-MPM","NA-WI","RW-01"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        for r in ("calendar_system","school_types","education_levels","terminology"):
            if r not in e: _fail(f"t1-{k}-{r}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 535:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster academic_sessions ?type= filter + terms convenience endpoint")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        # ?type=term filter (collection variant).
        req = rf.get("/api/roster/v1p2/academic-sessions/?type=term")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.academic_sessions(req)
        if resp.status_code != 200:
            _fail("t2-collection-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        for it in body.get("academicSessions", []):
            if it.get("type") != "term":
                _fail("t2-type-filter", f"got {it.get('type')}")
        _ok(f"t2-?type=term filter applied; n={len(body.get('academicSessions', []))} after filter")

        # terms convenience.
        req = rf.get("/api/roster/v1p2/terms/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.terms(req)
        if resp.status_code != 200:
            _fail("t2-terms-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if "terms" not in body:
            _fail("t2-terms-envelope", f"got {body}")
        for it in body.get("terms", []):
            if it.get("type") != "term":
                _fail("t2-terms-type", f"got {it.get('type')}")
        _ok(f"t2-/terms/ endpoint returns terms envelope; n={len(body.get('terms', []))}")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    # URL resolves.
    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-terms")
        if not url.endswith("/terms/"):
            _fail("t2-url", url)
        _ok(f"t2-URL route: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] hispanicOrLatinoEthnicity race flag")
    from apps.api import oneroster_demographics as odm
    if "hispanicOrLatinoEthnicity" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-registered", "missing")
    _ok(f"t3-RACE_ETHNICITY_BOOL_FIELDS expanded to {sorted(odm.RACE_ETHNICITY_BOOL_FIELDS)}")

    for v in (True, False, "true", "yes", "1", "0", "no", ""):
        err = odm._validate_race_ethnicity_bool_flags({"hispanicOrLatinoEthnicity": v})
        if err is not None:
            _fail(f"t3-{v!r}", f"got {err.content}")
    _ok("t3-hispanicOrLatinoEthnicity accepts bool literals + boolish strings + empty (clear)")

    err = odm._validate_race_ethnicity_bool_flags({"hispanicOrLatinoEthnicity": "maybe"})
    if err is None or err.status_code != 400:
        _fail("t3-bad", f"got {err}")
    body = _json.loads(err.content)
    if body.get("field") != "hispanicOrLatinoEthnicity":
        _fail("t3-field-echo", str(body))
    _ok("t3-'maybe' -> 400 not_boolish w/ field=hispanicOrLatinoEthnicity")

    # E2E covers all 4 flags now.
    body_bytes = _json.dumps({"demographic": {
        "americanIndianOrAlaskaNative": "false", "asian": "true",
        "blackOrAfricanAmerican": "false", "hispanicOrLatinoEthnicity": "true",
    }}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e-4-flags", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts all 4 race/ethnicity flags simultaneously")


def run_t4():
    _line("\n[T4] action_history_rollup_by_action analytics")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    # Also clear legacy LMSPushGradeAudit rows w/ _diag_action discriminator.
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(course_id="_diag_action").delete()  # tenant-isolation-allow: smoke-cleanup
    except Exception:
        pass
    vld._LAST_ACTION_RING.clear()

    rollup = vld.action_history_rollup_by_action()
    if rollup != {}:
        _fail("t4-empty", f"expected {{}}; got {rollup}")
    _ok("t4-empty ring + empty DB -> {} rollup")

    # Seed ring with a few synthetic action events.
    vld._LAST_ACTION_RING.extend([
        {"ts_iso": "2026-05-29T10:00:00Z", "action": "force_refresh",
         "provider": "canvas", "actor_hash": "aaa", "considered": 10, "ok": 8, "failed": 2},
        {"ts_iso": "2026-05-29T10:05:00Z", "action": "force_refresh",
         "provider": "moodle", "actor_hash": "aaa", "considered": 5, "ok": 5, "failed": 0},
        {"ts_iso": "2026-05-29T10:10:00Z", "action": "force_rotate",
         "provider": "canvas", "actor_hash": "bbb", "considered": 1, "ok": 1, "failed": 0},
        {"ts_iso": "2026-05-29T10:15:00Z", "action": "retention_purge",
         "provider": "lms_diag_action", "actor_hash": "ccc",
         "considered": 100, "ok": 75, "failed": 25},
    ])

    rollup = vld.action_history_rollup_by_action()
    if "force_refresh" not in rollup:
        _fail("t4-refresh-key", f"got {rollup}")
    if rollup["force_refresh"]["count"] != 2:
        _fail("t4-refresh-count", f"got {rollup['force_refresh']}")
    if rollup["force_refresh"]["ok_total"] != 13:
        _fail("t4-refresh-ok", f"got {rollup['force_refresh']}")
    if rollup["force_refresh"]["failed_total"] != 2:
        _fail("t4-refresh-failed", f"got {rollup['force_refresh']}")
    if rollup["force_refresh"]["considered_total"] != 15:
        _fail("t4-refresh-considered", f"got {rollup['force_refresh']}")
    _ok(f"t4-force_refresh rolled up: count=2 ok=13 failed=2 considered=15")

    if rollup["force_rotate"]["count"] != 1:
        _fail("t4-rotate-count", f"got {rollup}")
    if rollup["retention_purge"]["ok_total"] != 75:
        _fail("t4-purge-ok", f"got {rollup}")
    if rollup["retention_purge"]["failed_total"] != 25:
        _fail("t4-purge-failed", f"got {rollup}")
    _ok("t4-force_rotate + retention_purge rolled up correctly")

    # Bucket keys all match expected shape.
    for action, bucket in rollup.items():
        for k in ("count", "ok_total", "failed_total", "considered_total"):
            if k not in bucket:
                _fail(f"t4-bucket-key-{action}-{k}", "missing")
    _ok(f"t4-all {len(rollup)} action buckets carry count/ok_total/failed_total/considered_total")

    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] D2L OAuth state mint")
    from apps.integrations_marketplace import lms_connector_d2l as d2l

    for f in ("mint_oauth_state", "read_oauth_state"):
        if not hasattr(d2l, f):
            _fail(f"t5-func-{f}", "missing")
    _ok("t5-mint_oauth_state + read_oauth_state present")

    # Round-trip.
    token = d2l.mint_oauth_state(tenant_slug="acme", user_pk=42,
                                 redirect_path="/portal/dashboard/")
    parsed, reason = d2l.read_oauth_state(token)
    if reason != "ok":
        _fail("t5-rt-reason", f"got {reason}")
    if parsed["tenant_slug"] != "acme" or str(parsed["user_pk"]) != "42":
        _fail("t5-rt-payload", str(parsed))
    if parsed["redirect_path"] != "/portal/dashboard/":
        _fail("t5-rt-redirect", str(parsed))
    _ok("t5-D2L mint + read round-trip preserves tenant_slug/user_pk/redirect_path")

    # Bad token.
    _, reason = d2l.read_oauth_state("garbage")
    if reason != "bad_token":
        _fail("t5-bad", f"got {reason}")
    _ok("t5-bad token -> bad_token")

    # Empty.
    _, reason = d2l.read_oauth_state("")
    if reason != "missing_token":
        _fail("t5-missing", f"got {reason}")
    _ok("t5-empty -> missing_token")

    # Open-redirect defense.
    token = d2l.mint_oauth_state(tenant_slug="t", user_pk=1, redirect_path="//evil/")
    parsed, _ = d2l.read_oauth_state(token)
    if parsed["redirect_path"] != "/":
        _fail("t5-open-redirect", str(parsed))
    _ok("t5-//external redirect collapsed to / on mint")

    # Salt different from Schoology (cross-provider token reuse should fail).
    from apps.integrations_marketplace import lms_connector_schoology as sg
    sg_token = sg.mint_oauth_state(tenant_slug="t", user_pk=1)
    _, reason = d2l.read_oauth_state(sg_token)
    if reason != "bad_token":
        _fail("t5-cross-provider", f"expected bad_token (different salt); got {reason}")
    _ok("t5-Schoology token rejected by D2L reader (different salt - cross-provider isolation)")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
