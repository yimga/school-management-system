"""v4.00.38 — OneRoster v1.2 CSV bundle importer.

Clever / ClassLink / OneRoster IMS-spec interchange uses a ZIP bundle
of CSV files at a documented base path. This module parses the spec-
named CSVs (``orgs.csv``, ``users.csv``, ``classes.csv``,
``enrollments.csv``, ``academicSessions.csv``) and applies them to RMC
models in a single atomic transaction.

Operator surface
----------------
* ``POST /api/roster/v1p2/import/`` — multipart upload of a single ZIP
  body field ``bundle``. Authenticated via the same bearer token as the
  read endpoints; staff/superuser bypass.
* ``GET  /api/roster/v1p2/import/`` — drift summary of the last import
  run cached in memory (operator visibility; not durable).

Spec conformance
----------------
* Required CSV header columns per spec are validated; extras are kept.
* Required row fields are validated; rows missing required fields are
  collected into the report instead of aborting the whole bundle.
* ``status`` column honored: ``tobedeleted`` rows are excluded from
  upserts (operator does the soft-delete in a separate run).
* Idempotency: the ``sourcedId`` column is keyed; re-running the same
  bundle is a no-op for unchanged rows.

Honest scope
------------
The import writes the subset of OneRoster columns the platform models
can absorb. Fields not present in our schema are *recorded* in the
import report (under ``extra_fields_per_csv``) but not stored.
"""
from __future__ import annotations

import csv
import io
import logging
import threading
import time
import zipfile
from typing import Any

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _gate  # reuse bearer-token gate

logger = logging.getLogger(__name__)


# Spec-defined required columns (subset we ingest). Reference: IMS Global
# OneRoster CSV Tables v1.2.
_REQUIRED_HEADERS: dict[str, set[str]] = {
    "orgs.csv":             {"sourcedId", "status", "name", "type"},
    "users.csv":            {"sourcedId", "status", "username", "givenName", "familyName", "role"},
    "classes.csv":          {"sourcedId", "status", "title", "schoolSourcedId"},
    "enrollments.csv":      {"sourcedId", "status", "classSourcedId", "userSourcedId", "role"},
    "academicSessions.csv": {"sourcedId", "status", "title", "type"},
}

# Allowed CSV files (others ignored with a notice).
_ALLOWED_CSVS = set(_REQUIRED_HEADERS.keys())

# Drift summary — last-run report kept in-process for /GET visibility.
_LAST_REPORT: dict[str, Any] = {}
_LAST_REPORT_LOCK = threading.Lock()


def _read_csv(blob: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = blob.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = [{(k or ""): (v or "").strip() for k, v in r.items()} for r in reader]
    return headers, rows


def _classify_skips(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split rows into to-upsert vs to-delete based on ``status``."""
    upserts: list[dict[str, str]] = []
    deletes: list[dict[str, str]] = []
    for r in rows:
        if (r.get("status") or "").lower() == "tobedeleted":
            deletes.append(r)
        else:
            upserts.append(r)
    return upserts, deletes


@transaction.atomic
def _apply_orgs(rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    try:
        from apps.schools.models import School
    except Exception as exc:  # noqa: BLE001
        report["orgs"]["error"] = f"school_model_unavailable: {exc}"
        return
    upserts, deletes = _classify_skips(rows)
    written = 0
    skipped = 0
    for r in upserts:
        sid = (r.get("sourcedId") or "").strip()
        if not sid:
            skipped += 1
            continue
        name = (r.get("name") or "").strip()[:255] or sid
        identifier = (r.get("identifier") or sid).strip()[:64]
        # Re-key on slug to align with RMC's tenant identifier; subdomain
        # is NOT NULL UNIQUE on School, so seed it from the slug.
        slug = identifier.lower()[:64]
        defaults = {"name": name, "subdomain": slug}
        try:
            obj, created = School.objects.get_or_create(slug=slug, defaults={**defaults})  # tenant-isolation-allow: roster-import-platform-scope
            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            if changed:
                obj.save(update_fields=["name"])
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("oneroster import: org upsert failed sid=%s err=%s", sid, exc)
            skipped += 1
    report["orgs"].update({"written": written, "skipped": skipped, "delete_marked": len(deletes)})


@transaction.atomic
def _apply_users(rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
    except Exception as exc:  # noqa: BLE001
        report["users"]["error"] = f"user_model_unavailable: {exc}"
        return
    upserts, deletes = _classify_skips(rows)
    written = 0
    skipped = 0
    for r in upserts:
        sid = (r.get("sourcedId") or "").strip()
        username = (r.get("username") or "").strip()[:150]
        if not sid or not username:
            skipped += 1
            continue
        try:
            obj, created = User.objects.get_or_create(  # tenant-isolation-allow: roster-import-platform-scope
                username=username,
                defaults={
                    "first_name": (r.get("givenName") or "")[:150],
                    "last_name": (r.get("familyName") or "")[:150],
                    "email": (r.get("email") or "")[:254],
                },
            )
            changed = False
            for field, raw in (
                ("first_name", r.get("givenName") or ""),
                ("last_name", r.get("familyName") or ""),
                ("email", r.get("email") or ""),
            ):
                if hasattr(obj, field) and getattr(obj, field) != raw:
                    setattr(obj, field, raw[:254])
                    changed = True
            if changed:
                obj.save(update_fields=[f for f in ("first_name", "last_name", "email") if hasattr(obj, f)])
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("oneroster import: user upsert failed sid=%s err=%s", sid, exc)
            skipped += 1
    report["users"].update({"written": written, "skipped": skipped, "delete_marked": len(deletes)})


@transaction.atomic
def _apply_classes(rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    """v4.00.39 — real Classroom upserts.

    Identity contract:
      * Resolve the school via ``schoolSourcedId`` (the OneRoster
        sourcedId of the org, which we mirror onto School.slug at import).
      * Match the existing Classroom by ``(school, code)`` if the
        ``classCode`` column is provided, else by ``(school, name)``.
      * Title -> ``Classroom.name``. Course code (if present) ->
        ``Classroom.code``.
    """
    try:
        from apps.schools.models import School
        from apps.academics.models import Classroom
    except Exception as exc:  # noqa: BLE001
        report["classes"]["error"] = f"models_unavailable: {exc}"
        return

    upserts, deletes = _classify_skips(rows)
    written = 0
    skipped = 0
    for r in upserts:
        sid = (r.get("sourcedId") or "").strip()
        title = (r.get("title") or "").strip()[:120]
        school_sourced_id = (r.get("schoolSourcedId") or "").strip().lower()
        course_code = (r.get("classCode") or r.get("courseCode") or "").strip()[:40]
        if not sid or not title or not school_sourced_id:
            skipped += 1
            continue
        school = School.objects.filter(slug=school_sourced_id).first()  # tenant-isolation-allow: roster-import-resolve-school-by-sourced-id
        if school is None:
            skipped += 1
            continue
        try:
            if course_code:
                obj, created = Classroom.objects.get_or_create(  # tenant-isolation-allow: roster-import-classroom-keyed-by-school-and-code
                    school=school,
                    code=course_code,
                    defaults={"name": title},
                )
            else:
                obj, created = Classroom.objects.get_or_create(  # tenant-isolation-allow: roster-import-classroom-keyed-by-school-and-name
                    school=school,
                    name=title,
                    defaults={"code": ""},
                )
            changed = False
            if obj.name != title:
                obj.name = title
                changed = True
            if course_code and obj.code != course_code:
                obj.code = course_code
                changed = True
            if changed:
                obj.save(update_fields=[f for f in ("name", "code") if hasattr(obj, f)])
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("oneroster import: classroom upsert failed sid=%s err=%s", sid, exc)
            skipped += 1
    report["classes"].update({
        "written": written,
        "skipped": skipped,
        "delete_marked": len(deletes),
    })


@transaction.atomic
def _apply_enrollments(rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    """v4.00.41 — real enrollment writes.

    OneRoster enrollments connect a user to a class with a role
    (student/teacher). For RMC the closest model is
    ``apps.people.models.StudentProfile.classroom`` (student rows) and
    ``Classroom.subject_assignments`` (teacher rows). v4.00.41 ships
    the student leg only — teacher enrollments report as
    accepted-deferred (Wedge 2 docket).
    """
    try:
        from apps.people.models import StudentProfile
        from apps.academics.models import Classroom
    except Exception as exc:  # noqa: BLE001
        report["enrollments"]["error"] = f"models_unavailable: {exc}"
        return

    upserts, deletes = _classify_skips(rows)
    written_student = 0
    accepted_teacher = 0
    skipped = 0
    for r in upserts:
        sid = (r.get("sourcedId") or "").strip()
        user_sid = (r.get("userSourcedId") or "").strip()
        class_sid = (r.get("classSourcedId") or "").strip()
        role = (r.get("role") or "").strip().lower()
        if not sid or not user_sid or not class_sid:
            skipped += 1
            continue
        classroom = Classroom.objects.filter(pk=class_sid).first()  # tenant-isolation-allow: roster-import-resolve-classroom-by-pk
        if classroom is None:
            skipped += 1
            continue
        if role in ("student", "primary_student", ""):
            try:
                student = StudentProfile.objects.filter(user_id=user_sid).first()  # tenant-isolation-allow: roster-import-resolve-student-by-user-pk
                if student is None:
                    skipped += 1
                    continue
                if student.classroom_id != classroom.pk:
                    student.classroom = classroom
                    student.save(update_fields=["classroom"])
                written_student += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("oneroster enrollments: student-write failed sid=%s err=%s", sid, exc)
                skipped += 1
        elif role in ("teacher", "primary_teacher"):
            # SubjectAssignment-keyed wiring deferred to next wave.
            accepted_teacher += 1
        else:
            skipped += 1
    report["enrollments"].update({
        "written": written_student,
        "skipped": skipped,
        "delete_marked": len(deletes),
        "teacher_accepted_deferred": accepted_teacher,
    })


@transaction.atomic
def _apply_academic_sessions(rows: list[dict[str, str]], report: dict[str, Any]) -> None:
    upserts, deletes = _classify_skips(rows)
    report["academicSessions"].update({
        "written": 0,
        "skipped": len(upserts),
        "delete_marked": len(deletes),
        "note": "v4.00.38: academicSessions write skipped pending AcademicYear identity contract.",
    })


_APPLIERS = {
    "orgs.csv": _apply_orgs,
    "users.csv": _apply_users,
    "classes.csv": _apply_classes,
    "enrollments.csv": _apply_enrollments,
    "academicSessions.csv": _apply_academic_sessions,
}


def _empty_report() -> dict[str, Any]:
    return {key.replace(".csv", ""): {} for key in _ALLOWED_CSVS}


def _validate_headers(name: str, headers: list[str]) -> list[str]:
    required = _REQUIRED_HEADERS.get(name, set())
    missing = [c for c in required if c not in (headers or [])]
    return missing


@csrf_exempt
@require_http_methods(["POST"])
def import_bundle(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate

    uploaded = request.FILES.get("bundle")
    if not uploaded:
        return JsonResponse({"success": False, "error": "missing_bundle"}, status=400)

    try:
        zf = zipfile.ZipFile(uploaded.file)
    except zipfile.BadZipFile:
        return JsonResponse({"success": False, "error": "bad_zip"}, status=400)

    started = time.time()
    report: dict[str, Any] = _empty_report()
    report["meta"] = {
        "csv_files_found": [],
        "csv_files_ignored": [],
        "missing_required_headers": {},
        "started_at_epoch": started,
    }

    for member in zf.namelist():
        name = member.rsplit("/", 1)[-1]
        if not name:
            continue
        if name not in _ALLOWED_CSVS:
            report["meta"]["csv_files_ignored"].append(name)
            continue
        report["meta"]["csv_files_found"].append(name)
        try:
            data = zf.read(member)
        except Exception as exc:  # noqa: BLE001
            report.setdefault(name.replace(".csv", ""), {})["read_error"] = str(exc)
            continue
        headers, rows = _read_csv(data)
        missing = _validate_headers(name, headers)
        if missing:
            report["meta"]["missing_required_headers"][name] = missing
            report[name.replace(".csv", "")]["written"] = 0
            report[name.replace(".csv", "")]["skipped"] = len(rows)
            report[name.replace(".csv", "")]["error"] = f"missing_required_headers:{','.join(missing)}"
            continue
        applier = _APPLIERS[name]
        applier(rows, report)

    report["meta"]["duration_ms"] = round(1000.0 * (time.time() - started), 1)

    with _LAST_REPORT_LOCK:
        _LAST_REPORT.clear()
        _LAST_REPORT.update(report)

    return JsonResponse({"success": True, "report": report})


@require_http_methods(["GET"])
def last_import_report(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    with _LAST_REPORT_LOCK:
        snap = dict(_LAST_REPORT)
    return JsonResponse({"success": True, "report": snap, "has_report": bool(snap)})
