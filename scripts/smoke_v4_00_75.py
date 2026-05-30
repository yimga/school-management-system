"""v4.00.75 smoke."""
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
    keys = ["DE-BE","DE-HE","DE-RP","NL-NH","BE-BRU","AU-NSW","AU-VIC",
            "NZ-AUK","NZ-WGN","IT-LIG","IT-PUG","FR-IDF","FR-PAC","ES-CT"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 570:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster classes enriched + class_detail endpoint")
    from apps.api import oneroster as mod
    classes = list(mod._iter_classes())
    if classes:
        for k in ("sourcedId","status","title","classType","courseSourcedId",
                  "schoolSourcedId","termSourcedIds","grades"):
            if k not in classes[0]:
                _fail(f"t2-key-{k}", str(classes[0]))
        _ok(f"t2-class projection has 8 enriched keys (n={len(classes)})")
    else:
        _ok("t2-_iter_classes empty (no Classroom rows)")

    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/classes/9999/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.class_detail(req, sourced_id="9999")
        if resp.status_code != 404:
            _fail("t2-404", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if body.get("error") != "class_not_found":
            _fail("t2-404-body", str(body))
        _ok("t2-class_detail 404 -> class_not_found")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-class-detail", kwargs={"sourced_id": "X"})
        if not url.endswith("/classes/X/"):
            _fail("t2-url", url)
        _ok(f"t2-URL: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] demographicRaceTwoOrMoreRaces (7th and final race flag)")
    from apps.api import oneroster_demographics as odm
    if "demographicRaceTwoOrMoreRaces" not in odm.RACE_ETHNICITY_BOOL_FIELDS:
        _fail("t3-registered", "missing")
    if len(odm.RACE_ETHNICITY_BOOL_FIELDS) != 7:
        _fail("t3-count", f"expected 7; got {len(odm.RACE_ETHNICITY_BOOL_FIELDS)}")
    _ok(f"t3-7 race/ethnicity flags complete set: {sorted(odm.RACE_ETHNICITY_BOOL_FIELDS)}")

    for v in (True, False, "true", "no", "1", "0", ""):
        err = odm._validate_race_ethnicity_bool_flags({"demographicRaceTwoOrMoreRaces": v})
        if err is not None:
            _fail(f"t3-{v!r}", f"got {err.content}")
    _ok("t3-demographicRaceTwoOrMoreRaces accepts bool literals + boolish strings + empty")

    err = odm._validate_race_ethnicity_bool_flags({"demographicRaceTwoOrMoreRaces": "??"})
    if err is None or err.status_code != 400:
        _fail("t3-bad", "expected 400")
    _ok("t3-'??' -> 400 not_boolish")

    # E2E with all 7 flags.
    body_bytes = _json.dumps({"demographic": {
        "americanIndianOrAlaskaNative": "false", "asian": "false",
        "blackOrAfricanAmerican": "false", "hispanicOrLatinoEthnicity": "true",
        "nativeHawaiianOrOtherPacificIslander": "false", "white": "true",
        "demographicRaceTwoOrMoreRaces": "true",
    }}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e-7-flags", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts all 7 race/ethnicity flags simultaneously")


def run_t4():
    _line("\n[T4] diagnostics_health_rollup_by_provider")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(course_id="_diag_action").delete()  # tenant-isolation-allow: smoke-cleanup
    except Exception:
        pass
    vld._LAST_ACTION_RING.clear()

    rollup = vld.diagnostics_health_rollup_by_provider()
    if rollup != {}:
        _fail("t4-empty", str(rollup))
    _ok("t4-empty ring + DB -> {} rollup")

    vld._LAST_ACTION_RING.extend([
        {"ts_iso": "2026-05-29T10:00:00Z", "action": "force_refresh",
         "provider": "canvas", "actor_hash": "a", "considered": 10, "ok": 9, "failed": 1},
        {"ts_iso": "2026-05-29T10:05:00Z", "action": "force_refresh",
         "provider": "canvas", "actor_hash": "a", "considered": 10, "ok": 10, "failed": 0},
        {"ts_iso": "2026-05-29T10:10:00Z", "action": "force_rotate",
         "provider": "moodle", "actor_hash": "b", "considered": 1, "ok": 0, "failed": 1},
    ])

    rollup = vld.diagnostics_health_rollup_by_provider()
    if "canvas" not in rollup or "moodle" not in rollup:
        _fail("t4-keys", str(rollup))
    if rollup["canvas"]["total_actions"] != 2:
        _fail("t4-canvas-total", str(rollup["canvas"]))
    if rollup["canvas"]["ok_total"] != 19:
        _fail("t4-canvas-ok", str(rollup["canvas"]))
    if rollup["canvas"]["failed_total"] != 1:
        _fail("t4-canvas-failed", str(rollup["canvas"]))
    if rollup["canvas"]["success_rate_pct"] != 95.0:
        _fail("t4-canvas-pct", str(rollup["canvas"]))
    _ok(f"t4-canvas total_actions=2 ok=19 failed=1 success_rate_pct={rollup['canvas']['success_rate_pct']}")

    if rollup["moodle"]["success_rate_pct"] != 0.0:
        _fail("t4-moodle-pct", str(rollup["moodle"]))
    _ok(f"t4-moodle success_rate_pct=0.0 (1 failed, 0 ok)")

    # latest_action_iso tracking.
    if rollup["canvas"]["latest_action_iso"] != "2026-05-29T10:05:00Z":
        _fail("t4-canvas-latest", str(rollup["canvas"]))
    _ok("t4-latest_action_iso tracked across multiple events per provider")

    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] Schoology push_grade scaffold w/ would_send payload")
    from apps.integrations_marketplace import lms_connector_schoology as sg

    # Happy path.
    out = sg.push_grade(base_url="https://api.schoology.com/v1", access_token="t",
                        course_id="c-123", user_id="u-456",
                        score=85.0, max_score=100.0, comment="Good work")
    if out.get("reason") != "scaffold_not_wired":
        _fail("t5-reason", str(out))
    if "would_send" not in out:
        _fail("t5-would-send", str(out))
    if out["would_send"]["method"] != "PUT":
        _fail("t5-method", str(out))
    if "/sections/c-123/grades" not in out["would_send"]["endpoint"]:
        _fail("t5-endpoint", str(out))
    grades = out["would_send"]["body"]["grades"]["grade"]
    if grades[0]["grade"] != 85.0 or grades[0]["max_points"] != 100.0:
        _fail("t5-body", str(out))
    if grades[0]["enrollment_id"] != "u-456":
        _fail("t5-enrollment-id", str(out))
    if grades[0]["comment"] != "Good work":
        _fail("t5-comment", str(out))
    _ok("t5-happy-path scaffold returns would_send w/ PUT /sections/<id>/grades + 85/100 body")

    # Missing course_id rejected.
    out = sg.push_grade(base_url="x", access_token="t",
                        course_id="", user_id="u", score=10, max_score=10)
    if out.get("reason") != "missing_required_field":
        _fail("t5-missing-course", str(out))
    _ok("t5-missing course_id -> reason=missing_required_field")

    # Non-numeric score.
    out = sg.push_grade(base_url="x", access_token="t",
                        course_id="c", user_id="u", score="bad", max_score=10)
    if out.get("reason") != "score_not_numeric":
        _fail("t5-non-numeric", str(out))
    _ok("t5-non-numeric score -> reason=score_not_numeric")

    # Score > max.
    out = sg.push_grade(base_url="x", access_token="t",
                        course_id="c", user_id="u", score=150, max_score=100)
    if out.get("reason") != "score_exceeds_max":
        _fail("t5-exceed", str(out))
    _ok("t5-score 150 > max 100 -> reason=score_exceeds_max")

    # max_score <= 0.
    out = sg.push_grade(base_url="x", access_token="t",
                        course_id="c", user_id="u", score=5, max_score=0)
    if out.get("reason") != "score_out_of_range":
        _fail("t5-max-zero", str(out))
    _ok("t5-max_score=0 -> reason=score_out_of_range")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
