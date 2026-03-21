"""OneRoster 1.1: scoped Bearer, IP allowlist, per-token rate limit, audit, orgs/courses/users."""

from __future__ import annotations

import logging
import secrets as psecrets

from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.academics.models import Classroom, Department, Subject, Term
from apps.api.rate_limit import client_ip, throttle_ip_request
from apps.integrations_marketplace.models import ServiceIntegration
from apps.interop.oneroster.adapter import (
    classroom_to_oneroster,
    department_to_oneroster_org,
    enrollment_to_oneroster,
    school_to_oneroster_org,
    student_to_oneroster_user,
    subject_to_oneroster_course,
    synthetic_oneroster_rows,
    teacher_to_oneroster_user,
    term_to_academic_session,
)
from apps.interop.oneroster.auth_resolution import (
    export_profile,
    ip_allowed,
    match_integration_for_token,
    per_token_throttle,
    scope_allows,
    token_rate_limit_from_config,
)
from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School, TenantInteropAccessLog
from apps.siteconfig.integration_registry import resolve_service_integration

logger = logging.getLogger(__name__)

ONEROSTER_RATE_LIMIT_WINDOW = 60 * 15
ONEROSTER_RATE_LIMIT_MAX = 300

try:
    from prometheus_client import Counter

    ONEROSTER_REQ = Counter(
        "sms_oneroster_requests_total",
        "OneRoster API requests",
        ["endpoint", "status"],
    )
except Exception:  # pragma: no cover
    ONEROSTER_REQ = None


def _observe(endpoint: str, status: str) -> None:
    if ONEROSTER_REQ:
        try:
            ONEROSTER_REQ.labels(endpoint=endpoint, status=status).inc()
        except Exception:
            pass


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    slug = (request.GET.get("school_slug") or "").strip() or (
        request.headers.get("X-School-Slug") or ""
    ).strip()
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def _extract_token(request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _token_from_row(row: ServiceIntegration) -> str:
    return str(
        (row.config or {}).get("bearer_token") or row.client_secret or ""
    ).strip()


def _any_token_configured(school) -> bool:
    for row in ServiceIntegration.objects.filter(school=school, is_active=True).filter(
        Q(service_name__icontains="oneroster")
        | Q(service_name__icontains="1edtech")
        | Q(service_name__iexact=ONEROSTER_DISTRICT_API_SERVICE_NAME)
    ):
        if _token_from_row(row):
            return True
    alt = resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name="oneroster",
        name_hints=["oneroster", "1edtech"],
        allow_legacy_backfill=True,
    )
    return bool(alt and _token_from_row(alt))


def _collect_tokens(school) -> list[tuple[ServiceIntegration | None, str]]:
    out: list[tuple[ServiceIntegration | None, str]] = []
    seen = set()
    for row in (
        ServiceIntegration.objects.filter(school=school, is_active=True)
        .filter(
            Q(service_name__icontains="oneroster")
            | Q(service_name__icontains="1edtech")
            | Q(service_name__iexact=ONEROSTER_DISTRICT_API_SERVICE_NAME)
        )
        .order_by("-updated_at", "-id")
    ):
        t = _token_from_row(row)
        if t and t not in seen:
            seen.add(t)
            out.append((row, t))
    if not out:
        alt = resolve_service_integration(
            school,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            service_name="oneroster",
            name_hints=["oneroster", "1edtech"],
            allow_legacy_backfill=True,
        )
        if alt:
            t = _token_from_row(alt)
            if t:
                out.append((alt, t))
    return out


def _school_synthetic(school) -> bool:
    s = getattr(school, "settings", None) or {}
    if isinstance(s, dict) and s.get("interop_synthetic_roster"):
        return True
    sl = str(getattr(school, "slug", "") or "")
    return sl.endswith("-sandbox") or "sandbox" in sl.lower()


def _parse_scopes_cfg(cfg: dict) -> set[str]:
    raw = cfg.get("oneroster_scopes") or cfg.get("scopes")
    if raw is None:
        return {"*"}
    if isinstance(raw, str):
        parts = [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]
        return set(parts) if parts else {"*"}
    if isinstance(raw, list):
        return {str(x).strip().lower() for x in raw if str(x).strip()} or {"*"}
    return {"*"}


def _auth_and_context(request, endpoint_key: str):
    school = _resolve_school(request)
    if not school:
        _observe(endpoint_key, "400")
        return (
            None,
            None,
            None,
            JsonResponse({"error": "School context required"}, status=400),
        )
    if not _any_token_configured(school):
        _observe(endpoint_key, "503")
        return (
            None,
            None,
            None,
            JsonResponse({"error": "OneRoster integration not configured"}, status=503),
        )
    provided = _extract_token(request)
    if not provided:
        _observe(endpoint_key, "403")
        return None, None, None, JsonResponse({"error": "Unauthorized"}, status=403)

    integ = match_integration_for_token(school, provided)
    if not integ:
        pairs = _collect_tokens(school)
        ok = any(
            len(t) == len(provided) and psecrets.compare_digest(t, provided)
            for _r, t in pairs
        )
        if not ok:
            _observe(endpoint_key, "403")
            return None, None, None, JsonResponse({"error": "Unauthorized"}, status=403)
        integ = match_integration_for_token(school, provided)
        if not integ:
            for r, t in pairs:
                if len(t) == len(provided) and psecrets.compare_digest(t, provided):
                    integ = r
                    break

    cfg = dict((integ.config or {})) if integ else {}
    ip = client_ip(request)
    if not ip_allowed(cfg, ip):
        _observe(endpoint_key, "403")
        return (
            None,
            None,
            None,
            JsonResponse({"error": "Forbidden: IP not allowlisted"}, status=403),
        )
    scopes = _parse_scopes_cfg(cfg)
    if not scope_allows(endpoint_key, scopes):
        _observe(endpoint_key, "403")
        return (
            None,
            None,
            None,
            JsonResponse({"error": "Forbidden: insufficient scope"}, status=403),
        )

    lim = token_rate_limit_from_config(cfg, ONEROSTER_RATE_LIMIT_MAX)
    allowed, retry = per_token_throttle(
        request,
        endpoint_key=endpoint_key,
        token=provided,
        max_count=lim,
        window_seconds=ONEROSTER_RATE_LIMIT_WINDOW,
    )
    if not allowed:
        _observe(endpoint_key, "429")
        retry_i = int(retry)
        r = JsonResponse(
            {
                "error": "Too many requests (token quota)",
                "message": "OneRoster token rate limit exceeded. Retry after the indicated seconds.",
                "retry_after": retry_i,
            },
            status=429,
        )
        r["Retry-After"] = str(retry_i)
        return None, None, None, r
    ok_ip, ra = throttle_ip_request(
        request,
        scope=f"oneroster:{endpoint_key}",
        max_count=ONEROSTER_RATE_LIMIT_MAX,
        window_seconds=ONEROSTER_RATE_LIMIT_WINDOW,
    )
    if not ok_ip:
        _observe(endpoint_key, "429")
        ra_i = int(ra)
        r = JsonResponse(
            {
                "error": "Too many requests",
                "message": "OneRoster IP rate limit exceeded. Retry after the indicated seconds.",
                "retry_after": ra_i,
            },
            status=429,
        )
        r["Retry-After"] = str(ra_i)
        return None, None, None, r

    if cfg.get("oneroster_audit_disabled") not in (True, "1", "yes"):
        try:
            TenantInteropAccessLog.objects.create(
                school_id=school.pk,
                service="oneroster",
                endpoint=endpoint_key,
                integration_id=integ.pk if integ else None,
                client_ip=ip[:64],
                token_prefix=(provided[:8] + "…") if len(provided) > 8 else "",
            )
        except Exception as e:
            logger.debug("interop audit: %s", e)

    prof = export_profile(cfg)
    return school, integ, prof, None


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


def _oneroster_response(
    *, key: str, rows: list, offset: int, limit: int, endpoint_metric: str = ""
):
    if ONEROSTER_REQ and endpoint_metric:
        try:
            ONEROSTER_REQ.labels(endpoint=endpoint_metric, status="200").inc()
        except Exception:
            pass
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
    school, _i, _p, err = _auth_and_context(request, "manifest")
    if err:
        return err
    base = "/api/oneroster/v1p1"
    slug = school.slug
    payload = {
        "imsx_codeMajor": "success",
        "imsx_severity": "status",
        "imsx_description": "OK",
        "oneroster_version": "1.1",
        "school_slug": slug,
        "resources": {
            "academicSessions": f"{base}/academicSessions?school_slug={slug}",
            "classes": f"{base}/classes?school_slug={slug}",
            "students": f"{base}/students?school_slug={slug}",
            "teachers": f"{base}/teachers?school_slug={slug}",
            "enrollments": f"{base}/enrollments?school_slug={slug}",
            "orgs": f"{base}/orgs?school_slug={slug}",
            "courses": f"{base}/courses?school_slug={slug}",
            "users": f"{base}/users?school_slug={slug}",
        },
    }
    return JsonResponse(payload, status=200)


@require_GET
def academic_sessions(request):
    school, _i, _p, err = _auth_and_context(request, "academicSessions")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["academicSessions"][offset : offset + limit]
        return _oneroster_response(
            key="academicSessions",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="academicSessions",
        )
    rows = []
    qs = (
        Term.objects.filter(Q(school=school) | Q(academic_year__school=school))
        .select_related("academic_year")
        .distinct()
        .order_by("academic_year_id", "start_date", "pk")[offset : offset + limit]
    )
    for term in qs:
        rows.append(term_to_academic_session(term, school))
    return _oneroster_response(
        key="academicSessions",
        rows=rows,
        offset=offset,
        limit=limit,
        endpoint_metric="academicSessions",
    )


@require_GET
def classes(request):
    school, _i, prof, err = _auth_and_context(request, "classes")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["classes"][offset : offset + limit]
        return _oneroster_response(
            key="classes",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="classes",
        )
    from django.utils.dateparse import parse_datetime

    rows = []
    qs_base = Classroom.objects.filter(school=school)
    since_raw = (
        request.GET.get("changesSince") or request.GET.get("since") or ""
    ).strip()
    if since_raw:
        try:
            dt = parse_datetime(since_raw.replace("Z", "+00:00"))
            if dt is not None:
                qs_base = qs_base.filter(updated_at__gte=dt)
        except (TypeError, ValueError):
            pass
    for c in qs_base.select_related("academic_year").order_by("pk")[
        offset : offset + limit
    ]:
        rows.append(classroom_to_oneroster(c, school))
    return _oneroster_response(
        key="classes", rows=rows, offset=offset, limit=limit, endpoint_metric="classes"
    )


@require_GET
def students(request):
    school, _i, prof, err = _auth_and_context(request, "students")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        users = [u for u in syn["users"] if u.get("role") == "student"]
        rows = users[offset : offset + limit]
        return _oneroster_response(
            key="users",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="students",
        )
    rows = []
    from django.utils.dateparse import parse_datetime

    qs_base = StudentProfile.objects.filter(school=school)
    since_raw = (
        request.GET.get("changesSince") or request.GET.get("since") or ""
    ).strip()
    if since_raw:
        try:
            dt = parse_datetime(since_raw.replace("Z", "+00:00"))
            if dt is not None:
                qs_base = qs_base.filter(updated_at__gte=dt)
        except (TypeError, ValueError):
            pass
    qs = qs_base.select_related("classroom").order_by("pk")[offset : offset + limit]
    for student in qs:
        rows.append(student_to_oneroster_user(student, school, prof))
    return _oneroster_response(
        key="users", rows=rows, offset=offset, limit=limit, endpoint_metric="students"
    )


@require_GET
def teachers(request):
    school, _i, prof, err = _auth_and_context(request, "teachers")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        users = [u for u in syn["users"] if u.get("role") == "teacher"]
        rows = users[offset : offset + limit]
        return _oneroster_response(
            key="users",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="teachers",
        )
    rows = []
    qs = (
        TeacherProfile.objects.filter(school=school)
        .select_related("user")
        .order_by("pk")[offset : offset + limit]
    )
    for teacher in qs:
        rows.append(teacher_to_oneroster_user(teacher, school, prof))
    return _oneroster_response(
        key="users", rows=rows, offset=offset, limit=limit, endpoint_metric="teachers"
    )


@require_GET
def enrollments(request):
    school, _i, _p, err = _auth_and_context(request, "enrollments")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["enrollments"][offset : offset + limit]
        return _oneroster_response(
            key="enrollments",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="enrollments",
        )
    rows = []
    from django.utils.dateparse import parse_datetime as _pde

    qs_e = StudentProfile.objects.filter(school=school, classroom_id__isnull=False)
    since_e = (
        request.GET.get("changesSince") or request.GET.get("since") or ""
    ).strip()
    if since_e:
        try:
            dte = _pde(since_e.replace("Z", "+00:00"))
            if dte is not None:
                qs_e = qs_e.filter(updated_at__gte=dte)
        except (TypeError, ValueError):
            pass
    qs = qs_e.select_related("classroom").order_by("pk")[offset : offset + limit]
    for student in qs:
        rows.append(enrollment_to_oneroster(student, school))
    return _oneroster_response(
        key="enrollments",
        rows=rows,
        offset=offset,
        limit=limit,
        endpoint_metric="enrollments",
    )


@require_GET
def orgs(request):
    school, _i, _p, err = _auth_and_context(request, "orgs")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["orgs"][offset : offset + limit]
        return _oneroster_response(
            key="orgs", rows=rows, offset=offset, limit=limit, endpoint_metric="orgs"
        )
    rows = [school_to_oneroster_org(school)]
    rows.extend(
        department_to_oneroster_org(d, school)
        for d in Department.objects.filter(school=school).order_by("pk")
    )
    rows = rows[offset : offset + limit]
    return _oneroster_response(
        key="orgs", rows=rows, offset=offset, limit=limit, endpoint_metric="orgs"
    )


@require_GET
def courses(request):
    school, _i, _p, err = _auth_and_context(request, "courses")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["courses"][offset : offset + limit]
        return _oneroster_response(
            key="courses",
            rows=rows,
            offset=offset,
            limit=limit,
            endpoint_metric="courses",
        )
    rows = []
    for subj in Subject.objects.filter(school=school).order_by("pk")[
        offset : offset + limit
    ]:
        rows.append(subject_to_oneroster_course(subj, school))
    return _oneroster_response(
        key="courses", rows=rows, offset=offset, limit=limit, endpoint_metric="courses"
    )


@require_GET
def users(request):
    """Combined students + teachers (OneRoster-style users collection)."""
    school, _i, prof, err = _auth_and_context(request, "users")
    if err:
        return err
    offset, limit = _pagination(request)
    if _school_synthetic(school):
        syn = synthetic_oneroster_rows(school)
        rows = syn["users"][offset : offset + limit]
        return _oneroster_response(
            key="users", rows=rows, offset=offset, limit=limit, endpoint_metric="users"
        )
    rows = []
    for s in StudentProfile.objects.filter(school=school).order_by("pk"):
        rows.append(student_to_oneroster_user(s, school, prof))
    for t in (
        TeacherProfile.objects.filter(school=school)
        .select_related("user")
        .order_by("pk")
    ):
        rows.append(teacher_to_oneroster_user(t, school, prof))
    total = rows[offset : offset + limit]
    return _oneroster_response(
        key="users", rows=total, offset=offset, limit=limit, endpoint_metric="users"
    )
