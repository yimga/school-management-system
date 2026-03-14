"""OneRoster 1.1 baseline roster endpoints (tenant scoped, token authenticated)."""

from __future__ import annotations

import secrets
from typing import Any

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.academics.models import Classroom
from apps.api.rate_limit import throttle_ip_request
from apps.interop.oneroster.adapter import (
    classroom_to_oneroster,
    enrollment_to_oneroster,
    student_to_oneroster,
    teacher_to_oneroster,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.siteconfig.integration_registry import resolve_service_integration
from apps.integrations_marketplace.models import ServiceIntegration

ONEROSTER_RATE_LIMIT_WINDOW = 60 * 15
ONEROSTER_RATE_LIMIT_MAX = 300


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    slug = (
        (request.GET.get("school_slug") or "").strip()
        or (request.headers.get("X-School-Slug") or "").strip()
    )
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def _resolve_integration(school):
    return resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name="oneroster",
        name_hints=["oneroster", "1edtech"],
        allow_legacy_backfill=True,
    )


def _extract_token(request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _auth_guard(request):
    school = _resolve_school(request)
    if not school:
        return None, JsonResponse({"error": "School context required"}, status=400)
    integration = _resolve_integration(school)
    if not integration:
        return None, JsonResponse({"error": "OneRoster integration not configured"}, status=503)
    expected = str((integration.config or {}).get("bearer_token") or integration.client_secret or "").strip()
    provided = _extract_token(request)
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        return None, JsonResponse({"error": "Unauthorized"}, status=403)
    return school, None


def _oneroster_rate_limited(request, scope: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"oneroster:{scope}",
        max_count=ONEROSTER_RATE_LIMIT_MAX,
        window_seconds=ONEROSTER_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    response = JsonResponse({"error": "Too many requests"}, status=429)
    response["Retry-After"] = str(retry_after)
    return response


def _pagination(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0) or 0))
    except ValueError:
        offset = 0
    try:
        limit = int(request.GET.get("limit", 100) or 100)
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 200))
    return offset, limit


def _oneroster_response(*, key: str, rows: list[dict[str, Any]], offset: int, limit: int):
    payload = {
        "imsx_codeMajor": "success",
        "imsx_severity": "status",
        "imsx_description": "OK",
        "oneroster_version": "1.1",
        key: rows,
        "pagination": {"offset": offset, "limit": limit, "count": len(rows)},
    }
    return JsonResponse(payload, status=200)


@require_GET
def manifest(request):
    rl = _oneroster_rate_limited(request, "manifest")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    base = "/api/oneroster/v1p1"
    payload = {
        "imsx_codeMajor": "success",
        "imsx_severity": "status",
        "imsx_description": "OK",
        "oneroster_version": "1.1",
        "school_slug": school.slug,
        "resources": {
            "classes": f"{base}/classes?school_slug={school.slug}",
            "students": f"{base}/students?school_slug={school.slug}",
            "teachers": f"{base}/teachers?school_slug={school.slug}",
            "enrollments": f"{base}/enrollments?school_slug={school.slug}",
        },
    }
    return JsonResponse(payload, status=200)


@require_GET
def classes(request):
    rl = _oneroster_rate_limited(request, "classes")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    for classroom in Classroom.objects.filter(school=school).order_by("pk")[offset:(offset + limit)]:
        rows.append(classroom_to_oneroster(classroom, school))
    return _oneroster_response(key="classes", rows=rows, offset=offset, limit=limit)


@require_GET
def students(request):
    rl = _oneroster_rate_limited(request, "students")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = StudentProfile.objects.filter(school=school).select_related("classroom").order_by("pk")[offset:(offset + limit)]
    for student in qs:
        rows.append(student_to_oneroster(student, school))
    return _oneroster_response(key="users", rows=rows, offset=offset, limit=limit)


@require_GET
def teachers(request):
    rl = _oneroster_rate_limited(request, "teachers")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = TeacherProfile.objects.filter(school=school).select_related("user").order_by("pk")[offset:(offset + limit)]
    for teacher in qs:
        if teacher.user_id:
            pass
        rows.append(teacher_to_oneroster(teacher, school))
    return _oneroster_response(key="users", rows=rows, offset=offset, limit=limit)


@require_GET
def enrollments(request):
    rl = _oneroster_rate_limited(request, "enrollments")
    if rl:
        return rl
    school, err = _auth_guard(request)
    if err:
        return err
    offset, limit = _pagination(request)
    rows = []
    qs = StudentProfile.objects.filter(school=school, classroom_id__isnull=False).order_by("pk")[offset:(offset + limit)]
    for student in qs:
        rows.append(enrollment_to_oneroster(student, school))
    return _oneroster_response(key="enrollments", rows=rows, offset=offset, limit=limit)
