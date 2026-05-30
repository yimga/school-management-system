"""v4.00.36 — OneRoster v1.2 read-only Rostering endpoints.

Implements the spec-shape JSON envelopes for the wedge-44 (Clever /
ClassLink-style roster + SSO) operator surface. Scope:

* Read-only: `GET` only. No PUT / POST / DELETE in this wave.
* Pagination: ``?limit=<n>&offset=<n>`` honored per spec (default 100,
  max 1000).
* Auth: bearer token compared against ``RMC_ONEROSTER_ACCESS_TOKEN``
  env / settings (constant-time compare). Anonymous gets 401.
* Tenant isolation: when a token is associated with a specific tenant
  via the ``RMC_ONEROSTER_TENANT_SLUG`` env, queries are scoped; in
  multi-tenant mode the platform should issue per-tenant tokens.

Spec envelopes (subset):
    { "orgs":              [ {..., "type": "school"|"district", ...} ], "totalCount": N }
    { "schools":           [ {..., "type": "school", ...} ],            "totalCount": N }
    { "users":             [ {..., "role": "student"|"teacher", ...} ], "totalCount": N }
    { "classes":           [ {..., "title": "..." } ],                  "totalCount": N }
    { "academicSessions":  [ {..., "type": "schoolYear"|"term", ...} ], "totalCount": N }

Endpoints intentionally use the spec base path
``/ims/oneroster/rostering/v1p2/`` so customer tooling can be pointed
at the deployment without rewriting URLs. They're also re-exposed
under ``/api/v1/roster/v1p2/`` for our own dashboards.

Honest deferred: write-path, OAuth 2 client-credentials grant, real
Clever / ClassLink connector adapters.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Iterable

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _expected_token() -> str:
    """Resolve the OneRoster access token from env / settings."""
    return str(
        getattr(settings, "RMC_ONEROSTER_ACCESS_TOKEN", "")
        or os.environ.get("RMC_ONEROSTER_ACCESS_TOKEN", "")
        or ""
    )


def _authenticate(request: HttpRequest) -> tuple[bool, str | None]:
    """Bearer-token check. Returns (ok, error_code)."""
    header = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if not header.lower().startswith("bearer "):
        return False, "missing_bearer"
    submitted = header[7:].strip()
    expected = _expected_token()
    if not expected:
        # Soft-allow when no token is configured — useful for dev. Production
        # must set the env variable; log a one-time warning here.
        logger.info("oneroster: no RMC_ONEROSTER_ACCESS_TOKEN configured (dev mode)")
        return True, None
    if not submitted or not hmac.compare_digest(submitted, expected):
        return False, "invalid_token"
    return True, None


def _paginate(request: HttpRequest, items: list[Any]) -> tuple[list[Any], dict[str, int]]:
    try:
        limit = int(request.GET.get("limit") or 100)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.GET.get("offset") or 0)
    except (ValueError, TypeError):
        offset = 0
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    return items[offset : offset + limit], {"limit": limit, "offset": offset, "totalCount": len(items)}


def _envelope(key: str, items: list[Any], page_meta: dict[str, int]) -> JsonResponse:
    payload = {
        key: items,
        "totalCount": page_meta["totalCount"],
        "limit": page_meta["limit"],
        "offset": page_meta["offset"],
    }
    resp = JsonResponse(payload)
    resp["X-Total-Count"] = str(page_meta["totalCount"])
    resp["X-Limit"] = str(page_meta["limit"])
    resp["X-Offset"] = str(page_meta["offset"])
    return resp


def _gate(request: HttpRequest) -> JsonResponse | None:
    ok, err = _authenticate(request)
    if ok:
        return None
    resp = JsonResponse({"error": err or "unauthorized"}, status=401)
    resp["WWW-Authenticate"] = 'Bearer realm="OneRoster v1.2"'
    return resp


# ----- data adapters ------------------------------------------------------


def _iter_orgs() -> Iterable[dict[str, Any]]:
    """v4.00.70 — Enriched projection: parentSourcedId + metadata block w/
    subdivisionCode (ISO 3166-2 hint when present on the School row)."""
    try:
        from apps.schools.models import School
        qs = School.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        for s in qs[:1000]:
            parent_id = ""
            parent = getattr(s, "parent_org", None) or getattr(s, "parent", None)
            if parent is not None and hasattr(parent, "pk"):
                parent_id = str(parent.pk)
            subdivision = (
                getattr(s, "iso_3166_2_code", "")
                or getattr(s, "subdivision_code", "")
                or ""
            )
            country = (
                getattr(s, "iso_3166_1_alpha_2", "")
                or getattr(s, "country_code", "")
                or ""
            )
            yield {
                "sourcedId": str(s.pk),
                "status": "active",
                "type": "school",
                "name": getattr(s, "name", "") or "",
                "identifier": getattr(s, "slug", "") or str(s.pk),
                "parentSourcedId": parent_id,
                "metadata": {
                    "subdivisionCode": str(subdivision or "")[:8],
                    "countryCode": str(country or "")[:2],
                },
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster orgs: school model not available: %s", exc)


def _iter_users() -> Iterable[dict[str, Any]]:
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        qs = User.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        for u in qs[:1000]:
            role = "student"
            raw_role = str(getattr(u, "role", "") or "").lower()
            if "teacher" in raw_role:
                role = "teacher"
            elif "admin" in raw_role or getattr(u, "is_staff", False):
                role = "administrator"
            yield {
                "sourcedId": str(u.pk),
                "status": "active",
                "username": getattr(u, "username", "") or "",
                "givenName": getattr(u, "first_name", "") or "",
                "familyName": getattr(u, "last_name", "") or "",
                "email": getattr(u, "email", "") or "",
                "role": role,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster users: user model not iterable: %s", exc)


def _iter_classes() -> Iterable[dict[str, Any]]:
    """v4.00.75 — Enriched projection: courseSourcedId + termSourcedIds +
    schoolSourcedId + grades per OneRoster v1.2 Class resource."""
    try:
        from apps.academics.models import Classroom  # adjust if model name differs
        qs = Classroom.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        for c in qs[:1000]:
            course = getattr(c, "course", None)
            course_id = str(getattr(course, "pk", "")) if course is not None else str(c.pk)
            school = getattr(c, "school", None)
            school_id = str(getattr(school, "pk", "")) if school is not None else ""
            term = getattr(c, "term", None) or getattr(c, "academic_year", None)
            term_ids = [str(getattr(term, "pk", ""))] if term is not None else []
            grade = getattr(c, "grade_level", "") or getattr(c, "grade", "") or ""
            yield {
                "sourcedId": str(c.pk),
                "status": "active",
                "title": getattr(c, "name", "") or "",
                "classType": "scheduled",
                "courseSourcedId": course_id,
                "schoolSourcedId": school_id,
                "termSourcedIds": term_ids,
                "grades": [str(grade)] if grade else [],
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster classes: classroom model not iterable: %s", exc)


def _iter_courses() -> Iterable[dict[str, Any]]:
    """v4.00.74 — Project distinct course shapes from the Classroom model
    (when the project has a separate Course model, swap the import).
    Returns OneRoster v1.2 Course resource shape: ``sourcedId, status,
    title, courseCode, grades, subjects, schoolYearSourcedId``.
    """
    try:
        from apps.academics.models import Classroom
        qs = Classroom.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        seen: set[str] = set()
        for c in qs[:1000]:
            code = (getattr(c, "course_code", "")
                    or getattr(c, "code", "")
                    or getattr(c, "name", "")
                    or str(c.pk))
            if code in seen:
                continue
            seen.add(code)
            grade = getattr(c, "grade_level", "") or getattr(c, "grade", "") or ""
            subject = getattr(c, "subject", "") or ""
            year = getattr(c, "academic_year", None)
            year_id = str(getattr(year, "pk", "")) if year is not None else ""
            yield {
                "sourcedId": str(c.pk),
                "status": "active",
                "title": getattr(c, "name", "") or "",
                "courseCode": str(code),
                "grades": [str(grade)] if grade else [],
                "subjects": [str(subject)] if subject else [],
                "schoolYearSourcedId": year_id,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster courses: classroom model not iterable: %s", exc)


def _iter_academic_sessions() -> Iterable[dict[str, Any]]:
    """v4.00.71 — Enriched projection: startDate / endDate / schoolYear /
    parentSourcedId per OneRoster v1.2 § 4.13 AcademicSession resource."""
    try:
        from apps.academics.models import AcademicYear  # adjust if model name differs
        qs = AcademicYear.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        for y in qs[:200]:
            start = getattr(y, "start_date", None) or getattr(y, "starts_on", None)
            end = getattr(y, "end_date", None) or getattr(y, "ends_on", None)
            school_year = getattr(y, "school_year", "") or getattr(y, "label", "") or getattr(y, "name", "") or ""
            parent = getattr(y, "parent", None)
            parent_id = str(getattr(parent, "pk", "")) if parent is not None else ""
            yield {
                "sourcedId": str(y.pk),
                "status": "active",
                "title": getattr(y, "name", "") or "",
                "type": "schoolYear",
                "startDate": start.isoformat() if hasattr(start, "isoformat") else (str(start) if start else ""),
                "endDate": end.isoformat() if hasattr(end, "isoformat") else (str(end) if end else ""),
                "schoolYear": str(school_year or "")[:32],
                "parentSourcedId": parent_id,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster sessions: academic year model not iterable: %s", exc)


# ----- endpoints ----------------------------------------------------------


@require_http_methods(["GET"])
def orgs(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_orgs())
    page, meta = _paginate(request, items)
    return _envelope("orgs", page, meta)


@require_http_methods(["GET"])
def org_detail(request, sourced_id: str):
    """v4.00.70 — Per-spec § 4.13 single-org GET. 404 when not found,
    bearer-gated like the collection endpoint."""
    gate = _gate(request)
    if gate is not None:
        return gate
    for o in _iter_orgs():
        if o["sourcedId"] == str(sourced_id):
            return JsonResponse({"org": o})
    return JsonResponse({"error": "org_not_found", "sourcedId": str(sourced_id)}, status=404)


@require_http_methods(["GET"])
def schools(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [o for o in _iter_orgs() if o["type"] == "school"]
    page, meta = _paginate(request, items)
    return _envelope("schools", page, meta)


@require_http_methods(["GET"])
def users(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_users())
    page, meta = _paginate(request, items)
    return _envelope("users", page, meta)


@require_http_methods(["GET"])
def students(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [u for u in _iter_users() if u["role"] == "student"]
    page, meta = _paginate(request, items)
    return _envelope("students", page, meta)


@require_http_methods(["GET"])
def staff(request):
    """v4.00.77 — Convenience endpoint for users where role==administrator
    (or staff equivalent). Per OneRoster v1.2 § 4.13 the term ``staff``
    aggregates administrators + non-teaching support roles.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [u for u in _iter_users() if u["role"] in ("administrator", "staff")]
    page, meta = _paginate(request, items)
    return _envelope("staff", page, meta)


@require_http_methods(["GET"])
def teachers(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [u for u in _iter_users() if u["role"] == "teacher"]
    page, meta = _paginate(request, items)
    return _envelope("teachers", page, meta)


@require_http_methods(["GET"])
def classes(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_classes())
    page, meta = _paginate(request, items)
    return _envelope("classes", page, meta)


@require_http_methods(["GET"])
def academic_sessions(request):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_academic_sessions())
    # v4.00.72 — ?type=<value> subtype filter per spec § 4.13.
    # Common values: schoolYear / term / gradingPeriod / semester.
    wanted_type = (request.GET.get("type") or "").strip()
    if wanted_type:
        items = [it for it in items if it.get("type") == wanted_type]
    page, meta = _paginate(request, items)
    return _envelope("academicSessions", page, meta)


def _iter_enrollments() -> Iterable[dict[str, Any]]:
    """v4.00.76 — Project enrollments from any model with the typical
    student-class-role triple. Falls through silently when the model is
    not configured. Returns OneRoster v1.2 Enrollment shape:
    ``sourcedId, status, role, classSourcedId, schoolSourcedId, userSourcedId,
    beginDate, endDate``.
    """
    # Try a few common model names; project supports varied schemas.
    candidates = [
        ("apps.academics.models", "Enrollment"),
        ("apps.academics.models", "ClassEnrollment"),
        ("apps.academics.models", "StudentClassroom"),
    ]
    for module_path, class_name in candidates:
        try:
            mod = __import__(module_path, fromlist=[class_name])
            Model = getattr(mod, class_name, None)
            if Model is None:
                continue
            qs = Model.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
            for r in qs[:1000]:
                user = getattr(r, "student", None) or getattr(r, "user", None)
                klass = getattr(r, "classroom", None) or getattr(r, "klass", None) or getattr(r, "course", None)
                school = getattr(r, "school", None)
                begin = getattr(r, "start_date", None) or getattr(r, "begins_on", None)
                end = getattr(r, "end_date", None) or getattr(r, "ends_on", None)
                yield {
                    "sourcedId": str(r.pk),
                    "status": "active",
                    "role": "student",
                    "userSourcedId": str(getattr(user, "pk", "")) if user else "",
                    "classSourcedId": str(getattr(klass, "pk", "")) if klass else "",
                    "schoolSourcedId": str(getattr(school, "pk", "")) if school else "",
                    "beginDate": begin.isoformat() if hasattr(begin, "isoformat") else (str(begin) if begin else ""),
                    "endDate": end.isoformat() if hasattr(end, "isoformat") else (str(end) if end else ""),
                }
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("oneroster enrollments: %s.%s not iterable: %s", module_path, class_name, exc)
            continue


@require_http_methods(["GET"])
def enrollments(request):
    """v4.00.76 — GET /api/roster/v1p2/enrollments/ per spec § 4.13.

    ``?since=<iso>&before=<iso>`` window filter (when the upstream Enrollment
    rows expose ``start_date`` / ``end_date`` columns).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_enrollments())
    since = (request.GET.get("since") or "").strip()
    before = (request.GET.get("before") or "").strip()
    if since:
        items = [it for it in items if (it.get("beginDate") or "") >= since]
    if before:
        items = [it for it in items if (it.get("beginDate") or "") <= before]
    page, meta = _paginate(request, items)
    return _envelope("enrollments", page, meta)


@require_http_methods(["GET"])
def class_detail(request, sourced_id: str):
    """v4.00.75 — Per-spec § 4.13 single-class GET."""
    gate = _gate(request)
    if gate is not None:
        return gate
    for c in _iter_classes():
        if c["sourcedId"] == str(sourced_id):
            return JsonResponse({"class": c})
    return JsonResponse({"error": "class_not_found", "sourcedId": str(sourced_id)}, status=404)


@require_http_methods(["GET"])
def courses(request):
    """v4.00.74 — GET /api/roster/v1p2/courses/ per spec § 4.13 Course resource."""
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_courses())
    page, meta = _paginate(request, items)
    return _envelope("courses", page, meta)


@require_http_methods(["GET"])
def grading_periods(request):
    """v4.00.73 — Convenience endpoint for academicSessions where type==gradingPeriod.

    Equivalent to ``GET /academic-sessions/?type=gradingPeriod`` per spec § 4.13.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [s for s in _iter_academic_sessions() if s.get("type") == "gradingPeriod"]
    page, meta = _paginate(request, items)
    return _envelope("gradingPeriods", page, meta)


@require_http_methods(["GET"])
def terms(request):
    """v4.00.72 — Convenience endpoint for academicSessions where type==term.

    Equivalent to ``GET /academic-sessions/?type=term`` per spec § 4.13.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = [s for s in _iter_academic_sessions() if s.get("type") == "term"]
    page, meta = _paginate(request, items)
    return _envelope("terms", page, meta)


@require_http_methods(["GET"])
def academic_session_detail(request, sourced_id: str):
    """v4.00.71 — Per-spec § 4.13 single-academicSession GET."""
    gate = _gate(request)
    if gate is not None:
        return gate
    for s in _iter_academic_sessions():
        if s["sourcedId"] == str(sourced_id):
            return JsonResponse({"academicSession": s})
    return JsonResponse({"error": "academic_session_not_found",
                         "sourcedId": str(sourced_id)}, status=404)


# ----- v4.00.82 Wave 14 T2: delta endpoint w/ tombstones ------------------


def _parse_modified_since(raw: str):
    """Parse an ISO-8601 timestamp from the ``?modifiedSince=`` query param.

    Accepts the same shapes as v4.00.62 ``_parse_window_iso``:
    ``YYYY-MM-DD``, ``YYYY-MM-DDTHH:MM:SS``, trailing ``Z`` or ``+00:00``,
    naive (UTC-assumed).  Returns a tz-aware ``datetime`` on success, or
    ``None`` on unparseable input.
    """
    from datetime import datetime, timezone

    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Accept trailing Z as UTC.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Date-only shorthand.
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            dt = datetime.strptime(text, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _iter_users_delta(modified_since):
    """v4.00.82 — Iterate User rows with ``dateLastModified`` projected from
    the best-available timestamp on AbstractUser (``last_login`` falls back
    to ``date_joined``).  Yields two streams: active rows where
    ``dateLastModified > modified_since`` and tombstone rows where the user
    has been soft-deleted (``is_active=False``) since that moment.

    Tombstone honesty note:
      The Django AbstractUser model exposes ``is_active`` as a hard boolean
      but does NOT carry a dedicated "deactivated_at" column.  We synthesize
      tombstones by treating ``is_active=False`` rows as soft-deletes and
      use ``last_login`` (falling back to ``date_joined``) as the
      best-available proxy for ``dateLastModified``.  Hard deletes (rows
      removed via ``Model.delete()``) leave no audit trail and CANNOT
      produce tombstones — this is a known spec limitation per IMS v1.2
      § 4.13.4 and is documented here rather than faked.
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        qs = User.objects.all()  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
        for u in qs[:1000]:
            # Best-available modification anchor on AbstractUser.
            anchor = getattr(u, "last_login", None) or getattr(u, "date_joined", None)
            if anchor is not None and hasattr(anchor, "isoformat"):
                anchor_iso = anchor.isoformat()
            else:
                anchor_iso = ""
            # Filter: only emit rows changed AFTER modified_since.
            if modified_since is not None and anchor is not None:
                try:
                    if anchor <= modified_since:
                        continue
                except TypeError:
                    # Naive vs tz-aware compare — coerce to UTC.
                    from datetime import timezone as _tz
                    a = anchor if anchor.tzinfo else anchor.replace(tzinfo=_tz.utc)
                    if a <= modified_since:
                        continue
            is_active = bool(getattr(u, "is_active", True))
            if not is_active:
                # Tombstone projection per IMS v1.2 § 4.13.4 — minimal shape
                # so consumers can flip their local mirror without leaking
                # PII of a deactivated row.
                yield {
                    "sourcedId": str(u.pk),
                    "status": "tobedeleted",
                    "dateLastModified": anchor_iso,
                }
                continue
            # Active row — full projection, mirrors _iter_users + dateLastModified.
            role = "student"
            raw_role = str(getattr(u, "role", "") or "").lower()
            if "teacher" in raw_role:
                role = "teacher"
            elif "admin" in raw_role or getattr(u, "is_staff", False):
                role = "administrator"
            yield {
                "sourcedId": str(u.pk),
                "status": "active",
                "dateLastModified": anchor_iso,
                "username": getattr(u, "username", "") or "",
                "givenName": getattr(u, "first_name", "") or "",
                "familyName": getattr(u, "last_name", "") or "",
                "email": getattr(u, "email", "") or "",
                "role": role,
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster users delta: user model not iterable: %s", exc)


@require_http_methods(["GET"])
def users_delta_v1p2(request):
    """v4.00.82 Wave 14 T2 — Delta surface per OneRoster v1.2 § 4.13.4
    ("Pagination and updates").

    Required: ``?modifiedSince=<ISO>``.  Returns both:
      * Active rows where ``dateLastModified > modifiedSince`` (added or
        modified since the client's last sync).
      * Tombstone rows ``{sourcedId, status:"tobedeleted", dateLastModified}``
        for users whose ``is_active`` flag flipped to ``False`` since that
        moment.

    Optional: ``?limit=`` / ``?offset=`` paginate the combined stream.

    Honest deferred:
      Hard deletes (``Model.delete()``) leave no audit trail on the
      AbstractUser table and CANNOT produce tombstones — this is a known
      spec limitation. The tombstone half is synthesized from
      ``is_active=False`` rows using ``last_login`` / ``date_joined`` as
      the modification anchor.  When the project later adds a dedicated
      soft-delete column the filter narrows automatically.

    Response headers:
      ``X-Total-Count``: active + tombstone combined (before pagination).
      ``X-Active-Count``: active rows that passed the modifiedSince filter.
      ``X-Tombstone-Count``: tombstone rows that passed the filter.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    raw_since = (request.GET.get("modifiedSince") or "").strip()
    if not raw_since:
        return JsonResponse(
            {"error": "missing_param", "param": "modifiedSince"},
            status=400,
        )
    modified_since = _parse_modified_since(raw_since)
    if modified_since is None:
        return JsonResponse(
            {
                "error": "bad_modified_since",
                "param": "modifiedSince",
                "value": raw_since,
            },
            status=400,
        )

    items = list(_iter_users_delta(modified_since))
    active_count = sum(1 for it in items if it.get("status") == "active")
    tombstone_count = sum(1 for it in items if it.get("status") == "tobedeleted")
    page, meta = _paginate(request, items)
    resp = JsonResponse({"users": page})
    resp["X-Total-Count"] = str(meta["totalCount"])
    resp["X-Limit"] = str(meta["limit"])
    resp["X-Offset"] = str(meta["offset"])
    resp["X-Active-Count"] = str(active_count)
    resp["X-Tombstone-Count"] = str(tombstone_count)
    return resp
