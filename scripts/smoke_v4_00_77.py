"""v4.00.77 smoke."""
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
    keys = ["RU-SPE","RU-SVE","RU-NVS","UA-46","UA-32","BY-HM","KZ-ALA",
            "UZ-TK","AM-ER","AZ-BA","GE-TB","MD-CU","MK-85","AL-TR"]
    for k in keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-{k}", "missing")
        _ok(f"t1-{k} OK")
    if len(COUNTRY_LOCALIZATION) < 598:
        _fail("t1-sot-count", f"got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] OneRoster /staff/ endpoint")
    from apps.api import oneroster as mod
    rf = RequestFactory()
    os.environ["RMC_ONEROSTER_BEARER"] = "smoke-bearer"
    try:
        req = rf.get("/api/roster/v1p2/staff/")
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        resp = mod.staff(req)
        if resp.status_code != 200:
            _fail("t2-status", f"got {resp.status_code}")
        body = _json.loads(resp.content)
        if "staff" not in body:
            _fail("t2-envelope", str(body))
        # Verify role filter: every entry must be administrator OR staff.
        for it in body.get("staff", []):
            if it.get("role") not in ("administrator", "staff"):
                _fail(f"t2-role-{it.get('role')}", str(it))
        _ok(f"t2-/staff/ envelope; n={len(body.get('staff', []))} (all role in administrator|staff)")
    finally:
        os.environ.pop("RMC_ONEROSTER_BEARER", None)

    from django.urls import reverse, NoReverseMatch
    try:
        url = reverse("api:api-roster-v1p2-staff")
        if not url.endswith("/staff/"):
            _fail("t2-url", url)
        _ok(f"t2-URL: {url}")
    except NoReverseMatch as exc:
        _fail("t2-url", str(exc))


def run_t3():
    _line("\n[T3] genderIdentity extended vocab")
    from apps.api import oneroster_demographics as odm

    # Empty / missing accepted.
    if odm._validate_gender_identity({}) is not None:
        _fail("t3-missing", "expected None")
    if odm._validate_gender_identity({"genderIdentity": ""}) is not None:
        _fail("t3-empty", "expected None")
    _ok("t3-missing/empty -> None")

    # All 7 vocab values accepted.
    for v in sorted(odm.GENDER_IDENTITY_VOCAB):
        err = odm._validate_gender_identity({"genderIdentity": v})
        if err is not None:
            _fail(f"t3-vocab-{v}", f"got {err.content}")
    _ok(f"t3-all {len(odm.GENDER_IDENTITY_VOCAB)} vocab values accepted: {sorted(odm.GENDER_IDENTITY_VOCAB)}")

    # Case-insensitive.
    err = odm._validate_gender_identity({"genderIdentity": "NON_BINARY"})
    if err is not None:
        _fail("t3-case", f"got {err.content}")
    _ok("t3-case-insensitive (NON_BINARY accepted)")

    # Bad value rejected.
    err = odm._validate_gender_identity({"genderIdentity": "alien"})
    if err is None or err.status_code != 400:
        _fail("t3-bad", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "value_not_in_vocab":
        _fail("t3-bad-reason", str(body))
    _ok("t3-'alien' -> 400 value_not_in_vocab w/ allowed list echoed")

    # Description w/o self_describe -> 400.
    err = odm._validate_gender_identity({
        "genderIdentity": "non_binary",
        "genderIdentityDescription": "agender",
    })
    if err is None or err.status_code != 400:
        _fail("t3-desc-no-self", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "description_requires_self_describe":
        _fail("t3-desc-reason", str(body))
    _ok("t3-description w/o prefer_to_self_describe -> 400 description_requires_self_describe")

    # Description WITH self_describe -> ok.
    err = odm._validate_gender_identity({
        "genderIdentity": "prefer_to_self_describe",
        "genderIdentityDescription": "Agender",
    })
    if err is not None:
        _fail("t3-desc-ok", f"got {err.content}")
    _ok("t3-prefer_to_self_describe + description accepted")

    # Description too long.
    err = odm._validate_gender_identity({
        "genderIdentity": "prefer_to_self_describe",
        "genderIdentityDescription": "x" * 81,
    })
    if err is None or err.status_code != 400:
        _fail("t3-desc-long", "expected 400")
    body = _json.loads(err.content)
    if body.get("reason") != "description_too_long":
        _fail("t3-desc-long-reason", str(body))
    _ok("t3-description 81 chars -> 400 description_too_long")

    # Description w/ control chars.
    err = odm._validate_gender_identity({
        "genderIdentity": "prefer_to_self_describe",
        "genderIdentityDescription": "Bad\x00Char",
    })
    if err is None or err.status_code != 400:
        _fail("t3-desc-ctrl", "expected 400")
    _ok("t3-description control char -> 400")

    # E2E via _parse_demographic_payload.
    body_bytes = _json.dumps({"demographic": {
        "genderIdentity": "non_binary",
    }}).encode("utf-8")
    inner, err = odm._parse_demographic_payload(body_bytes)
    if err is not None:
        _fail("t3-e2e", f"got {err}")
    _ok("t3-_parse_demographic_payload accepts genderIdentity=non_binary")


def run_t4():
    _line("\n[T4] compute_diagnostics_alarms")
    from apps.migration_cloud import views_lms_diagnostics as vld
    from apps.integrations_marketplace.models import LMSDiagActionAudit
    LMSDiagActionAudit.objects.all().delete()  # tenant-isolation-allow: smoke-cleanup
    try:
        from apps.integrations_marketplace.models import LMSPushGradeAudit
        LMSPushGradeAudit.objects.filter(course_id="_diag_action").delete()  # tenant-isolation-allow: smoke-cleanup
    except Exception:
        pass
    vld._LAST_ACTION_RING.clear()

    alarms = vld.compute_diagnostics_alarms()
    if alarms != []:
        _fail("t4-empty", str(alarms))
    _ok("t4-empty -> [] alarms")

    # Seed: canvas healthy (95%), moodle warning (75%), google_classroom critical (20%).
    seeds = []
    # canvas: 19 ok / 1 failed in 20 actions (success 95%, no alarm)
    seeds += [{"action": "force_refresh", "provider": "canvas", "actor_hash": "a",
               "considered": 1, "ok": 1, "failed": 0, "ts_iso": "2026-05-29T10:00:00Z"}] * 19
    seeds += [{"action": "force_refresh", "provider": "canvas", "actor_hash": "a",
               "considered": 1, "ok": 0, "failed": 1, "ts_iso": "2026-05-29T10:01:00Z"}]
    # moodle: 15 ok / 5 failed (75% success, "warning")
    seeds += [{"action": "force_refresh", "provider": "moodle", "actor_hash": "a",
               "considered": 1, "ok": 1, "failed": 0, "ts_iso": "2026-05-29T10:00:00Z"}] * 15
    seeds += [{"action": "force_refresh", "provider": "moodle", "actor_hash": "a",
               "considered": 1, "ok": 0, "failed": 1, "ts_iso": "2026-05-29T10:01:00Z"}] * 5
    # google_classroom: 2 ok / 8 failed (20% success, "critical")
    seeds += [{"action": "force_refresh", "provider": "google_classroom", "actor_hash": "a",
               "considered": 1, "ok": 1, "failed": 0, "ts_iso": "2026-05-29T10:00:00Z"}] * 2
    seeds += [{"action": "force_refresh", "provider": "google_classroom", "actor_hash": "a",
               "considered": 1, "ok": 0, "failed": 1, "ts_iso": "2026-05-29T10:01:00Z"}] * 8
    # schoology: only 2 actions (below min_actions) -> skipped
    seeds += [{"action": "force_refresh", "provider": "schoology", "actor_hash": "a",
               "considered": 1, "ok": 0, "failed": 1, "ts_iso": "2026-05-29T10:00:00Z"}] * 2
    vld._LAST_ACTION_RING.extend(seeds)

    alarms = vld.compute_diagnostics_alarms()
    providers = [a["provider"] for a in alarms]
    if "canvas" in providers:
        _fail("t4-canvas-healthy", str(alarms))
    if "schoology" in providers:
        _fail("t4-schoology-noise", str(alarms))
    if "moodle" not in providers or "google_classroom" not in providers:
        _fail("t4-missing-alarms", str(providers))
    _ok(f"t4-2 alarms triggered (moodle + google_classroom); canvas/schoology not (healthy/noise)")

    # Critical sorted first.
    if alarms[0]["provider"] != "google_classroom":
        _fail("t4-sort", f"expected google_classroom first; got {alarms[0]}")
    if alarms[0]["severity"] != "critical":
        _fail("t4-critical", str(alarms[0]))
    if alarms[1]["severity"] != "warning":
        _fail("t4-warning", str(alarms[1]))
    _ok("t4-google_classroom severity=critical sorted first; moodle severity=warning")

    # Threshold override.
    alarms = vld.compute_diagnostics_alarms(success_floor_pct=50.0)
    if len(alarms) != 1:
        _fail("t4-threshold", str(alarms))
    _ok(f"t4-threshold=50% -> 1 alarm (only google_classroom)")

    vld._LAST_ACTION_RING.clear()
    _ok("t4-cleanup")


def run_t5():
    _line("\n[T5] OAuth refresh metrics module")
    from apps.integrations_marketplace import lms_oauth_metrics as om

    om.reset_oauth_metrics()
    snap = om.get_oauth_metrics_snapshot()
    if snap != {}:
        _fail("t5-reset", str(snap))
    _ok("t5-reset -> {}")

    om.record_refresh_attempt("canvas", ok=True)
    om.record_refresh_attempt("canvas", ok=True)
    om.record_refresh_attempt("canvas", ok=False, reason="refresh_revoked")
    om.record_refresh_attempt("moodle", ok=True)

    snap = om.get_oauth_metrics_snapshot()
    if snap["canvas"]["attempts"] != 3:
        _fail("t5-canvas-attempts", str(snap["canvas"]))
    if snap["canvas"]["ok"] != 2:
        _fail("t5-canvas-ok", str(snap["canvas"]))
    if snap["canvas"]["failed"] != 1:
        _fail("t5-canvas-failed", str(snap["canvas"]))
    expected_rate = round(100.0 * 2 / 3, 2)
    if snap["canvas"]["ok_rate_pct"] != expected_rate:
        _fail("t5-canvas-rate", str(snap["canvas"]))
    if snap["canvas"]["last_reason"] != "refresh_revoked":
        _fail("t5-canvas-reason", str(snap["canvas"]))
    if snap["canvas"]["last_ok"] is not False:
        _fail("t5-canvas-last-ok", str(snap["canvas"]))
    _ok(f"t5-canvas: 3 attempts, 2 ok, 1 failed (rate={snap['canvas']['ok_rate_pct']}%), last_reason='refresh_revoked'")

    if snap["moodle"]["ok"] != 1 or snap["moodle"]["last_ok"] is not True:
        _fail("t5-moodle", str(snap["moodle"]))
    _ok("t5-moodle independent counters preserved")

    # Reason truncated to 120 chars.
    om.record_refresh_attempt("d2l_brightspace", ok=False, reason="x" * 200)
    snap = om.get_oauth_metrics_snapshot()
    if len(snap["d2l_brightspace"]["last_reason"]) != 120:
        _fail("t5-reason-trunc", str(snap["d2l_brightspace"]))
    _ok("t5-reason auto-truncated to 120 chars")

    om.reset_oauth_metrics()
    _ok("t5-cleanup")


def main():
    run_t1(); run_t2(); run_t3(); run_t4(); run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(2)
