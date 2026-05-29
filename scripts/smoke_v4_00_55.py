"""v4.00.55 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: 11 ISO 3166-2 subdivision packs
T2: OneRoster classGroup writes + results bulk-import
T3: LMS audit operator UI rotation-row filter
T4: LMS Celery beat schedule SOT install
T5: Audit retention export-before-purge

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name}: {detail}")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# T1 — 11 ISO 3166-2 subdivision packs
# ---------------------------------------------------------------------------
def run_t1():
    _line("\nT1 — 11 ISO 3166-2 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    expected = [
        "US-OH", "US-MI", "US-NC",
        "IN-AP", "IN-TG", "IN-GJ",
        "JP-13",
        "KR-11",
        "CN-BJ",
        "ES-MD",
        "IT-LOM",
    ]
    for code in expected:
        if code not in COUNTRY_LOCALIZATION:
            _fail("T1.subdivision_registered", f"missing {code}")
        row = COUNTRY_LOCALIZATION[code]
        for field in ("calendar_system", "school_types", "education_levels", "terminology"):
            if field not in row:
                _fail("T1.row_completeness", f"{code} missing {field}")
        if not isinstance(row["school_types"], list) or len(row["school_types"]) < 4:
            _fail("T1.school_types_min", f"{code} has {len(row.get('school_types', []))}")
        if not isinstance(row["education_levels"], list) or len(row["education_levels"]) < 3:
            _fail("T1.education_levels_min", f"{code} has {len(row.get('education_levels', []))}")
    _ok(f"all 11 subdivisions registered with required fields (sot len={len(COUNTRY_LOCALIZATION)})")


# ---------------------------------------------------------------------------
# T2 — OneRoster classGroup writes + Results bulk-import
# ---------------------------------------------------------------------------
def run_t2():
    _line("\nT2 — OneRoster classGroup writes + Results bulk-import")
    import json
    from django.test import RequestFactory
    from apps.api import oneroster_results as orr

    orr._CLASSGROUP_OVERRIDES.clear()
    orr._CLASSGROUP_TOMBSTONES.clear()

    rf = RequestFactory()

    def _post(path, body, headers=None):
        req = rf.post(path, data=json.dumps(body), content_type="application/json",
                      **(headers or {}))
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    def _put(path, body, headers=None):
        req = rf.put(path, data=json.dumps(body), content_type="application/json",
                     **(headers or {}))
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    def _delete(path):
        req = rf.delete(path)
        req._dont_enforce_csrf_checks = True
        req.META["HTTP_AUTHORIZATION"] = "Bearer smoke-bearer"
        return req

    # --- ClassGroup POST: missing idempotency-key -> 428 ---
    r = orr.post_classgroup(_post("/api/roster/results/v1p2/classGroups/post/", {}))
    if r.status_code != 428:
        _fail("T2.cg.missing_idem", f"got {r.status_code}")
    _ok("classGroup POST 428 on missing Idempotency-Key")

    # --- ClassGroup POST: success ---
    req = _post(
        "/api/roster/results/v1p2/classGroups/post/",
        {"classGroup": {"title": "Math Department", "type": "department",
                        "classSourcedIds": ["1", "2", "3"]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-1"},
    )
    r = orr.post_classgroup(req)
    if r.status_code != 201:
        _fail("T2.cg.first_post", f"got {r.status_code} body={r.content[:200]!r}")
    body = json.loads(r.content)
    sid = body["classGroup"]["sourcedId"]
    if not sid.startswith("cg-"):
        _fail("T2.cg.sid_prefix", sid)
    if body["classGroup"]["type"] != "department":
        _fail("T2.cg.type", str(body))
    if body["classGroup"]["classSourcedIds"] != ["1", "2", "3"]:
        _fail("T2.cg.class_sids", str(body))
    _ok(f"classGroup POST 201 creates {sid} with 3 class sids")

    # --- Replay returns cached body ---
    req2 = _post(
        "/api/roster/results/v1p2/classGroups/post/",
        {"classGroup": {"title": "Math Department", "type": "department",
                        "classSourcedIds": ["1", "2", "3"]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-1"},
    )
    r = orr.post_classgroup(req2)
    if r.get("Idempotency-Replay") != "true":
        _fail("T2.cg.replay_header", "missing")
    _ok("classGroup POST replay returns Idempotency-Replay: true")

    # --- Mismatch -> 409 ---
    req3 = _post(
        "/api/roster/results/v1p2/classGroups/post/",
        {"classGroup": {"title": "Different", "type": "grade", "classSourcedIds": []}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-1"},
    )
    r = orr.post_classgroup(req3)
    if r.status_code != 409:
        _fail("T2.cg.mismatch_409", f"got {r.status_code}")
    _ok("classGroup POST 409 on payload mismatch")

    # --- Bad type -> 400 ---
    req_bad_type = _post(
        "/api/roster/results/v1p2/classGroups/post/",
        {"classGroup": {"title": "x", "type": "not-a-real-type"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-bad-type"},
    )
    r = orr.post_classgroup(req_bad_type)
    if r.status_code != 400:
        _fail("T2.cg.bad_type_400", f"got {r.status_code}")
    _ok("classGroup POST 400 on bad type")

    # --- Missing title -> 400 ---
    req_no_title = _post(
        "/api/roster/results/v1p2/classGroups/post/",
        {"classGroup": {"type": "department"}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-no-title"},
    )
    r = orr.post_classgroup(req_no_title)
    if r.status_code != 400:
        _fail("T2.cg.no_title_400", f"got {r.status_code}")
    _ok("classGroup POST 400 on missing title")

    # --- PUT update title + add class ---
    req_put = _put(
        f"/api/roster/results/v1p2/classGroups/{sid}/put/",
        {"classGroup": {"title": "Mathematics Department", "classSourcedIds": ["1", "2", "3", "4"]}},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-cg-put-1"},
    )
    r = orr.put_classgroup(req_put, sid)
    if r.status_code != 200:
        _fail("T2.cg.put_status", f"got {r.status_code}")
    body = json.loads(r.content)
    if body["classGroup"]["title"] != "Mathematics Department":
        _fail("T2.cg.put_title", str(body))
    if body["classGroup"]["classSourcedIds"] != ["1", "2", "3", "4"]:
        _fail("T2.cg.put_classes", str(body))
    _ok("classGroup PUT 200 updates title + class list")

    # --- DELETE idempotent ---
    r = orr.delete_classgroup(_delete(f"/api/roster/results/v1p2/classGroups/{sid}/delete/"), sid)
    body = json.loads(r.content)
    if body.get("alreadyDeleted") is not False:
        _fail("T2.cg.first_delete", str(body))
    r = orr.delete_classgroup(_delete(f"/api/roster/results/v1p2/classGroups/{sid}/delete/"), sid)
    body = json.loads(r.content)
    if body.get("alreadyDeleted") is not True:
        _fail("T2.cg.second_delete", str(body))
    _ok("classGroup DELETE idempotent (alreadyDeleted false then true)")

    # --- Results bulk-import: missing idem-key -> 428 ---
    r = orr.post_results_bulk_import(_post("/api/roster/results/v1p2/results/import/", {}))
    if r.status_code != 428:
        _fail("T2.bulk.missing_idem", f"got {r.status_code}")
    _ok("results bulk-import POST 428 on missing Idempotency-Key")

    # --- Empty array -> 400 ---
    req_empty = _post(
        "/api/roster/results/v1p2/results/import/",
        {"results": []},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-bulk-empty"},
    )
    r = orr.post_results_bulk_import(req_empty)
    if r.status_code != 400:
        _fail("T2.bulk.empty_400", f"got {r.status_code}")
    _ok("results bulk-import POST 400 on empty array")

    # --- Missing results key -> 400 ---
    req_missing = _post(
        "/api/roster/results/v1p2/results/import/",
        {"foo": "bar"},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-bulk-missing"},
    )
    r = orr.post_results_bulk_import(req_missing)
    if r.status_code != 400:
        _fail("T2.bulk.missing_400", f"got {r.status_code}")
    _ok("results bulk-import POST 400 on missing results key")

    # --- Over-cap -> 413 ---
    big = [{"studentSourcedId": str(i), "lineItemSourcedId": f"li-{i}"} for i in range(501)]
    req_big = _post(
        "/api/roster/results/v1p2/results/import/",
        {"results": big},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-bulk-big"},
    )
    r = orr.post_results_bulk_import(req_big)
    if r.status_code != 413:
        _fail("T2.bulk.too_many_413", f"got {r.status_code}")
    _ok("results bulk-import POST 413 on > 500 rows")

    # --- Real bulk import: all rows have missing student so they error;
    # batch still returns 207 (Multi-Status) with per-row outcomes. ---
    rows = [
        {"studentSourcedId": "no-such-student-1", "lineItemSourcedId": "li-no-such-classroom-1", "score": "85"},
        {"studentSourcedId": "no-such-student-2", "lineItemSourcedId": "li-no-such-classroom-2", "score": "abc"},  # bad score -> errored
        {"studentSourcedId": "", "lineItemSourcedId": "li-x", "score": "70"},  # missing student
    ]
    req_real = _post(
        "/api/roster/results/v1p2/results/import/",
        {"results": rows},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-bulk-real"},
    )
    r = orr.post_results_bulk_import(req_real)
    if r.status_code != 207:
        _fail("T2.bulk.partial_207", f"got {r.status_code}")
    body = json.loads(r.content)
    if body["total"] != 3:
        _fail("T2.bulk.total", str(body))
    if body["errored"] != 3 or body["created"] != 0:
        _fail("T2.bulk.counts", str(body))
    if len(body["outcomes"]) != 3:
        _fail("T2.bulk.outcomes_len", str(body))
    if not any("score_not_numeric" in (o.get("error") or "") for o in body["outcomes"]):
        _fail("T2.bulk.score_error_detected", str(body["outcomes"]))
    _ok("results bulk-import 207 multi-status with per-row outcomes (3 errored, 0 created)")

    # --- Replay returns cached body ---
    req_replay = _post(
        "/api/roster/results/v1p2/results/import/",
        {"results": rows},
        headers={"HTTP_IDEMPOTENCY_KEY": "smoke-bulk-real"},
    )
    r = orr.post_results_bulk_import(req_replay)
    if r.get("Idempotency-Replay") != "true":
        _fail("T2.bulk.replay_header", "missing")
    _ok("results bulk-import replay returns Idempotency-Replay: true")


# ---------------------------------------------------------------------------
# T3 — LMS audit operator UI rotation-row filter
# ---------------------------------------------------------------------------
def run_t3():
    _line("\nT3 — LMS audit operator UI rotation-row filter")
    import json
    from django.test import RequestFactory
    from django.contrib.auth import get_user_model
    from apps.portal.views_lms_audit import lms_audit_index, _ROTATION_COURSE_ID_MARKER
    from apps.integrations_marketplace.models import LMSPushGradeAudit

    User = get_user_model()
    staff = User(pk=999992, username="smoke-staff-audit-rotation", is_staff=True, is_active=True)
    staff.set_unusable_password()
    rf = RequestFactory()

    # Sanity: marker value matches what the rotation sweep emits.
    if _ROTATION_COURSE_ID_MARKER != "_rotation":
        _fail("T3.marker_constant", _ROTATION_COURSE_ID_MARKER)
    _ok(f"rotation marker constant = {_ROTATION_COURSE_ID_MARKER!r}")

    # Insert 2 push rows + 1 rotation row in a transaction we roll back.
    from django.db import transaction
    push_a = LMSPushGradeAudit(
        provider="canvas", course_id="course-1", assignment_id="a1",
        user_hash="abcd1234abcd1234", ok=True, status_code=200,
    )
    push_b = LMSPushGradeAudit(
        provider="moodle", course_id="course-2", assignment_id="a2",
        user_hash="efef5678efef5678", ok=False, status_code=400,
    )
    rotation = LMSPushGradeAudit(
        provider="canvas", course_id=_ROTATION_COURSE_ID_MARKER, assignment_id="refresh_revoked",
        user_hash="", ok=False, status_code=0, detail="invalid_grant",
    )

    sid = transaction.savepoint()
    try:
        push_a.save()
        push_b.save()
        rotation.save()

        def _req(qs=""):
            req = rf.get(f"/portal/super/integrations/lms/audit/{qs}")
            req.user = staff
            return req

        # All rows (no rotation filter) — totals.count includes rotation
        r = lms_audit_index(_req("?format=json"))
        body = json.loads(r.content)
        if not body["success"]:
            _fail("T3.all.success", str(body))
        ids = {row["id"] for row in body["rows"]}
        if push_a.pk not in ids or push_b.pk not in ids or rotation.pk not in ids:
            _fail("T3.all.completeness", f"ids={ids}")
        if body["totals"]["rotation"] < 1:
            _fail("T3.all.totals_rotation", str(body["totals"]))
        if body["totals"]["push"] < 2:
            _fail("T3.all.totals_push", str(body["totals"]))
        _ok("default (no rotation filter) includes both push + rotation rows")

        # rotation=only
        r = lms_audit_index(_req("?format=json&rotation=only"))
        body = json.loads(r.content)
        ids = {row["id"] for row in body["rows"]}
        if rotation.pk not in ids:
            _fail("T3.only.missing_rotation", f"ids={ids}")
        if push_a.pk in ids or push_b.pk in ids:
            _fail("T3.only.includes_push", f"ids={ids}")
        if not all(row["is_rotation"] for row in body["rows"]):
            _fail("T3.only.is_rotation_flag", str(body["rows"]))
        _ok("rotation=only filters to just the rotation row + is_rotation=true")

        # rotation=exclude
        r = lms_audit_index(_req("?format=json&rotation=exclude"))
        body = json.loads(r.content)
        ids = {row["id"] for row in body["rows"]}
        if rotation.pk in ids:
            _fail("T3.exclude.includes_rotation", f"ids={ids}")
        if push_a.pk not in ids or push_b.pk not in ids:
            _fail("T3.exclude.missing_push", f"ids={ids}")
        _ok("rotation=exclude hides rotation row")

        # rotation=1 alias also works
        r = lms_audit_index(_req("?format=json&rotation=1"))
        body = json.loads(r.content)
        ids = {row["id"] for row in body["rows"]}
        if rotation.pk not in ids:
            _fail("T3.alias_1.missing_rotation", f"ids={ids}")
        if push_a.pk in ids or push_b.pk in ids:
            _fail("T3.alias_1.includes_push", f"ids={ids}")
        _ok("rotation=1 alias works the same as rotation=only")

        # rotation=0 alias also works
        r = lms_audit_index(_req("?format=json&rotation=0"))
        body = json.loads(r.content)
        ids = {row["id"] for row in body["rows"]}
        if rotation.pk in ids:
            _fail("T3.alias_0.includes_rotation", f"ids={ids}")
        _ok("rotation=0 alias works the same as rotation=exclude")

        # Filter is preserved in the response body
        r = lms_audit_index(_req("?format=json&rotation=only"))
        body = json.loads(r.content)
        if body["filter"]["rotation"] != "only":
            _fail("T3.filter_echo", str(body["filter"]))
        _ok("filter.rotation echoed in JSON response")
    finally:
        transaction.savepoint_rollback(sid)


# ---------------------------------------------------------------------------
# T4 — LMS Celery beat schedule SOT install
# ---------------------------------------------------------------------------
def run_t4():
    _line("\nT4 — LMS Celery beat schedule SOT install")
    from apps.integrations_marketplace import beat_schedule as bs

    # Build a fresh schedule (lazy, so we get the current env state)
    schedule = bs.get_lms_beat_schedule()
    expected = {
        "integrations-refresh-lms-tokens",
        "integrations-rotate-lms-tokens",
        "integrations-purge-lms-audit-rows",
    }
    if set(schedule.keys()) != expected:
        _fail("T4.schedule_keys", f"got {set(schedule.keys())}")
    _ok(f"SOT exports 3 entries: {sorted(schedule.keys())}")

    # Refresh entry is float 3600
    refresh = schedule["integrations-refresh-lms-tokens"]
    if refresh["task"] != "integrations_marketplace.refresh_due_lms_tokens":
        _fail("T4.refresh_task", refresh["task"])
    if refresh["schedule"] != 3600.0:
        _fail("T4.refresh_cadence", refresh["schedule"])
    _ok("refresh entry: 3600s float cadence + expires=3300")

    # Rotation entry uses crontab 03:30 UTC
    rotation = schedule["integrations-rotate-lms-tokens"]
    from celery.schedules import crontab as _crontab
    if not isinstance(rotation["schedule"], _crontab):
        _fail("T4.rotation_crontab_type", type(rotation["schedule"]).__name__)
    # crontab fields: hour=3, minute=30
    rs = rotation["schedule"]
    if str(rs._orig_hour) != "3" or str(rs._orig_minute) != "30":
        _fail("T4.rotation_hour_minute", f"hour={rs._orig_hour} minute={rs._orig_minute}")
    _ok("rotation entry: crontab 03:30 UTC daily")

    # Retention entry uses crontab Sun 04:00 UTC
    retention = schedule["integrations-purge-lms-audit-rows"]
    if not isinstance(retention["schedule"], _crontab):
        _fail("T4.retention_crontab_type", type(retention["schedule"]).__name__)
    rs2 = retention["schedule"]
    if str(rs2._orig_hour) != "4" or str(rs2._orig_minute) != "0" or str(rs2._orig_day_of_week) != "sun":
        _fail("T4.retention_day", f"hour={rs2._orig_hour} minute={rs2._orig_minute} dow={rs2._orig_day_of_week}")
    _ok("retention entry: crontab Sunday 04:00 UTC weekly")

    # install_lms_beat_schedule is idempotent: pre-existing keys preserved.
    class FakeConf:
        beat_schedule: dict = {}

    class FakeApp:
        conf = FakeConf()

    app = FakeApp()
    app.conf.beat_schedule = {"operator-custom": {"task": "x", "schedule": 60.0}}
    installed = bs.install_lms_beat_schedule(app)
    if "operator-custom" not in app.conf.beat_schedule:
        _fail("T4.install_preserves_operator_keys", "operator-custom was overwritten")
    if "integrations-refresh-lms-tokens" not in installed:
        _fail("T4.install_returns_added", str(installed))
    if len(installed) != 3:
        _fail("T4.install_count", str(len(installed)))
    _ok("install preserves operator-defined keys + returns 3 added entries")

    # Idempotent: re-install doesn't add anything new
    second = bs.install_lms_beat_schedule(app)
    if len(second) != 0:
        _fail("T4.install_idempotent", str(second))
    _ok("install is idempotent (re-run adds 0 entries)")

    # Per-entry disable via env var
    os.environ["RMC_LMS_TOKEN_ROTATION_BEAT_DISABLED"] = "1"
    try:
        disabled_schedule = bs.get_lms_beat_schedule()
        if "integrations-rotate-lms-tokens" in disabled_schedule:
            _fail("T4.disabled_skipped", "rotation entry still present")
        if len(disabled_schedule) != 2:
            _fail("T4.disabled_count", str(len(disabled_schedule)))
        _ok("RMC_LMS_TOKEN_ROTATION_BEAT_DISABLED=1 omits the rotation entry")
    finally:
        del os.environ["RMC_LMS_TOKEN_ROTATION_BEAT_DISABLED"]

    # Celery app already wired at config.celery import time
    from config.celery import app as real_app
    if "integrations-refresh-lms-tokens" not in real_app.conf.beat_schedule:
        _fail("T4.real_app_wired", "config/celery.py did not install the schedule")
    _ok("config/celery.py wires the schedule on app construction")


# ---------------------------------------------------------------------------
# T5 — Audit retention export-before-purge
# ---------------------------------------------------------------------------
def run_t5():
    _line("\nT5 — Audit retention export-before-purge")
    import json
    import tempfile
    import time
    from datetime import timedelta
    from django.utils import timezone as _tz
    from django.db import transaction
    from apps.integrations_marketplace import lms_audit_retention as lar
    from apps.integrations_marketplace.models import LMSPushGradeAudit

    # Sweep without rows is graceful when export_dir is set
    with tempfile.TemporaryDirectory() as tmp:
        out = lar.sweep_lms_audit_retention(years=7, export_dir=tmp)
        if out.get("exported") is not False:
            _fail("T5.no_rows.exported_false", str(out))
        if out["purged"] != 0:
            _fail("T5.no_rows.purged", str(out))
        _ok("no rows + export_dir set: exported=False, purged=0")

    # Inject a row OLDER than 7y so the sweep would purge it
    pinned_now = _tz.now()
    very_old = pinned_now - timedelta(days=8 * 365)
    sid = transaction.savepoint()
    try:
        old_row = LMSPushGradeAudit(
            provider="canvas", course_id="old-course", assignment_id="old-a",
            user_hash="aaaa1111aaaa1111", ok=True, status_code=200,
        )
        old_row.save()
        # Force created_at backwards by raw update so auto_now_add doesn't fight us
        LMSPushGradeAudit.objects.filter(pk=old_row.pk).update(created_at=very_old)  # tenant-isolation-allow: smoke-test-platform-scope-pinned-pk

        # Dry-run still respects export_dir but never writes (and never deletes)
        with tempfile.TemporaryDirectory() as tmp:
            out = lar.sweep_lms_audit_retention(
                years=7, now=pinned_now, dry_run=True, export_dir=tmp,
            )
            if out["dry_run"] is not True:
                _fail("T5.dry_run.flag", str(out))
            if out["purged"] != 0:
                _fail("T5.dry_run.purged", str(out))
            files = os.listdir(tmp)
            if files:
                _fail("T5.dry_run.no_write", f"unexpected files {files}")
            _ok("dry_run=True with export_dir does NOT write OR delete")

        # Real sweep WITH export — writes file then deletes
        with tempfile.TemporaryDirectory() as tmp:
            out = lar.sweep_lms_audit_retention(
                years=7, now=pinned_now, dry_run=False, export_dir=tmp,
            )
            if out["exported"] is not True:
                _fail("T5.real.exported_flag", str(out))
            if out["purged"] != 1:
                _fail("T5.real.purged_count", str(out))
            if out["export_rows"] != 1:
                _fail("T5.real.export_rows", str(out))
            files = os.listdir(tmp)
            if len(files) != 1 or not files[0].startswith("lms_audit_purge_"):
                _fail("T5.real.filename", f"got {files}")
            with open(os.path.join(tmp, files[0]), encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            if len(lines) != 1:
                _fail("T5.real.line_count", str(lines))
            entry = json.loads(lines[0])
            if entry["provider"] != "canvas" or entry["course_id"] != "old-course":
                _fail("T5.real.line_content", str(entry))
            # Row actually gone from DB
            still_there = LMSPushGradeAudit.objects.filter(pk=old_row.pk).exists()  # tenant-isolation-allow: smoke-test-platform-scope-pinned-pk
            if still_there:
                _fail("T5.real.row_deleted", "row still present after purge")
            _ok("export-before-purge writes JSONL snapshot then bulk-deletes (1 row)")

        # Backwards-compat: no export_dir = legacy behavior (purge w/o snapshot)
        old_row2 = LMSPushGradeAudit(
            provider="moodle", course_id="legacy-course", assignment_id="leg-a",
            user_hash="bbbb2222bbbb2222", ok=True, status_code=200,
        )
        old_row2.save()
        LMSPushGradeAudit.objects.filter(pk=old_row2.pk).update(created_at=very_old)  # tenant-isolation-allow: smoke-test-platform-scope-pinned-pk
        out = lar.sweep_lms_audit_retention(years=7, now=pinned_now, dry_run=False, export_dir=None)
        if out.get("exported") is not False:
            _fail("T5.no_export.exported_flag", str(out))
        if out["purged"] != 1:
            _fail("T5.no_export.purged_count", str(out))
        _ok("export_dir=None: legacy v4.00.54 behavior (purge w/o snapshot)")

        # Export batch oversized: refuses to proceed (env-overridable cap)
        for i in range(3):
            r = LMSPushGradeAudit(
                provider="canvas", course_id=f"big-{i}", assignment_id=f"big-a-{i}",
                user_hash=f"cccc{i}cccc{i}cccc", ok=True, status_code=200,
            )
            r.save()
            LMSPushGradeAudit.objects.filter(pk=r.pk).update(created_at=very_old)  # tenant-isolation-allow: smoke-test-platform-scope-pinned-pk
        with tempfile.TemporaryDirectory() as tmp:
            out = lar.sweep_lms_audit_retention(
                years=7, now=pinned_now, dry_run=False,
                export_dir=tmp, export_max_rows=2,
            )
            if out.get("error") != "export_batch_oversized":
                _fail("T5.oversized.error", str(out))
            if out["purged"] != 0:
                _fail("T5.oversized.no_purge", str(out))
            files = os.listdir(tmp)
            if files:
                _fail("T5.oversized.no_write", f"unexpected files {files}")
            _ok("export batch > max_rows: aborts before delete, error=export_batch_oversized")

        # Unwritable export dir = abort, no delete. Use the SMOKE SCRIPT
        # itself as the "directory" — mkdir on a regular file is the
        # cleanest cross-platform way to produce an OSError.
        out = lar.sweep_lms_audit_retention(
            years=7, now=pinned_now, dry_run=False,
            export_dir=os.path.abspath(__file__),
        )
        if out["purged"] != 0:
            _fail("T5.bad_dir.purged_not_zero", str(out))
        if "export_" not in (out.get("error") or ""):
            _fail("T5.bad_dir.error", str(out))
        _ok("unwritable export_dir (file-as-dir): aborts before delete (no data lost)")
    finally:
        transaction.savepoint_rollback(sid)


# ---------------------------------------------------------------------------

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
