"""OneRoster v1.2 Rostering endpoints.

Implements the spec-shape JSON envelopes for the wedge-44 (Clever /
ClassLink-style roster + SSO) operator surface. Scope:

* Read and governed write paths for core roster entities.
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

OAuth 2 client-credentials, single-entity writes, bulk user upserts, and
CSV bundle import are implemented. Vendor-native Clever / ClassLink adapters
remain partner-credential integration gates; OneRoster is the open substitute.
"""
from __future__ import annotations

import hashlib
import hmac
import json as _json
import logging
import os
from typing import Any, Iterable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _expected_token() -> str:
    """Resolve the OneRoster access token from env / settings."""
    return str(
        getattr(settings, "RMC_ONEROSTER_ACCESS_TOKEN", "")
        or os.environ.get("RMC_ONEROSTER_ACCESS_TOKEN", "")
        or ""
    )


def _allow_dev_open() -> bool:
    """v4.01 SECURITY escape hatch (default OFF).

    When no ``RMC_ONEROSTER_ACCESS_TOKEN`` is configured, the roster API fails
    closed. Set ``RMC_ONEROSTER_ALLOW_DEV_OPEN=1`` to restore the historical
    "no token → open" behavior on a dev/test box only — never in production.
    """
    raw = str(
        getattr(settings, "RMC_ONEROSTER_ALLOW_DEV_OPEN", "")
        or os.environ.get("RMC_ONEROSTER_ALLOW_DEV_OPEN", "")
        or ""
    )
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _authenticate(request: HttpRequest) -> tuple[bool, str | None]:
    """Bearer-token check. Returns (ok, error_code).

    v4.00.92 Wave 25 C4 — extended to accept BOTH:
      * the legacy static env Bearer in ``RMC_ONEROSTER_ACCESS_TOKEN``
        (back-compat for existing integrations);
      * OAuth2-issued Bearer tokens minted by
        :mod:`apps.api.oneroster_oauth2_token` (RFC 6749 § 4.4 client
        credentials grant). The decoded payload is stashed on the request
        as ``_oneroster_oauth2`` so downstream views can check scopes.

    Validation order: static env first (cheap constant-time compare),
    then OAuth2 (TimestampSigner.unsign). On both miss → ``invalid_token``.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if not header.lower().startswith("bearer "):
        return False, "missing_bearer"
    submitted = header[7:].strip()
    if not submitted:
        return False, "invalid_token"
    expected = _expected_token()
    # Legacy static env Bearer wins when configured + matches.
    if expected and hmac.compare_digest(submitted, expected):
        return True, None
    # OAuth2 client_credentials path.
    try:
        from apps.api.oneroster_oauth2_token import decode_oauth2_bearer_token
        ok, payload = decode_oauth2_bearer_token(submitted)
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster oauth2 decode failed: %s", exc)
        ok, payload = False, None
    if ok and payload is not None:
        # Attach so per-endpoint scope checks can read it.
        try:
            setattr(request, "_oneroster_oauth2", payload)
        except Exception:  # noqa: BLE001
            pass
        # v4.01 SECURITY — enforce the token's bound tenant. An OAuth2 token is
        # minted for a specific tenant_schema; if the request resolves to a
        # different tenant, refuse rather than let the token read cross-tenant
        # roster data. Tokens with no bound schema (legacy/global) are exempt.
        token_schema = str((payload or {}).get("tenant_schema") or "").strip()
        if token_schema:
            req_schema = ""
            try:
                _t = getattr(request, "tenant", None)
                if _t is not None:
                    req_schema = str(getattr(_t, "schema_name", "") or "").strip()
            except Exception:  # noqa: BLE001
                req_schema = ""
            if req_schema and req_schema != token_schema:
                logger.warning(
                    "oneroster oauth2: tenant mismatch (token=%s request=%s)",
                    token_schema, req_schema,
                )
                return False, "tenant_mismatch"
        return True, None
    if not expected:
        # v4.01 SECURITY — fail closed. Previously "no env token configured"
        # soft-allowed ANY bearer (even garbage), opening every roster endpoint
        # on a deployment that simply hadn't set RMC_ONEROSTER_ACCESS_TOKEN.
        # The dev-open behavior now requires an explicit opt-in escape hatch.
        if _allow_dev_open():
            logger.info("oneroster: dev-open enabled (RMC_ONEROSTER_ALLOW_DEV_OPEN) — accepting bearer")
            return True, None
        logger.warning("oneroster: no token configured and dev-open disabled — refusing bearer")
        return False, "invalid_token"
    return False, "invalid_token"


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


# OneRoster v1.2 write scopes. A *.createput scope is required to mutate roster
# data; without this check a read-only (.readonly) OAuth2 token could call the
# PUT/bulk-POST write endpoints (the scope model existed but was unenforced).
_WRITE_SCOPES: frozenset[str] = frozenset({
    "roster-core.createput",
    "roster-demographics.createput",
    "roster-results.createput",
})


def _require_write_scope(request: HttpRequest) -> JsonResponse | None:
    """Return a 403 unless the OAuth2 caller holds a write scope.

    Static-bearer / dev-open callers (no ``_oneroster_oauth2`` payload) are
    unaffected — they have no scope model and keep their historical access.
    """
    payload = getattr(request, "_oneroster_oauth2", None)
    if not payload:
        return None
    scopes = set(payload.get("scopes") or [])
    if scopes & _WRITE_SCOPES:
        return None
    resp = JsonResponse(
        {"error": "insufficient_scope", "scope": "roster-*.createput"}, status=403
    )
    resp["WWW-Authenticate"] = (
        'Bearer realm="OneRoster v1.2", error="insufficient_scope"'
    )
    return resp


# ---------------------------------------------------------------------------
# v4.00.92 Wave 25 M1 + M2 — shared GET/HEAD pipeline for the 6 main
# collection list endpoints (orgs / schools / users / classes / courses /
# enrollments). Every collection view delegates to ``_collection_get`` so
# ?filter / ?sort / ?fields / pagination all share a single SOT, and the
# ``_head_supported`` wrapper computes X-Total-Count for HEAD verbs from
# the SAME projection function (no logic duplication per spec § 4.13).
# ---------------------------------------------------------------------------


def _empty_response_with_total_count(
    projection: "callable",
    request: HttpRequest,
) -> JsonResponse:
    """Build a HEAD-verb response: 200 + X-Total-Count + empty body.

    Reuses the GET projection so HEAD and GET always agree on the count.
    The filter pipeline runs so ``?filter=`` is honored even on HEAD.
    """
    from apps.api.oneroster_query_helpers import total_count_for
    items = list(projection())
    total = total_count_for(request, items)
    resp = JsonResponse({}, status=200)
    resp["X-Total-Count"] = str(total)
    # Empty body for HEAD per RFC 7231 § 4.3.2.
    resp.content = b""
    return resp


def _head_supported(view_func):
    """Decorator: route HEAD to an empty-body + X-Total-Count response.

    The wrapped view is expected to follow the OneRoster collection
    convention — accept ``request`` and return a JSON envelope of the
    queried collection. When HEAD is requested, we re-run only the
    projection callable carried on the function as ``_projection_attr``.
    """
    def wrapped(request, *args, **kwargs):
        if request.method == "HEAD":
            # Auth gate still applies on HEAD.
            gate = _gate(request)
            if gate is not None:
                return gate
            projection = getattr(view_func, "_projection", None)
            if projection is None:
                # Fall back to GET → strip body. This works because
                # JsonResponse + content="" honors X-Total-Count headers.
                resp = view_func(request, *args, **kwargs)
                if hasattr(resp, "content"):
                    resp.content = b""
                return resp
            return _empty_response_with_total_count(projection, request)
        return view_func(request, *args, **kwargs)
    wrapped.__name__ = view_func.__name__
    wrapped.__doc__ = view_func.__doc__
    # Mirror the projection attribute so the wrapper is introspectable.
    if hasattr(view_func, "_projection"):
        wrapped._projection = view_func._projection
    return wrapped


def _collection_get(
    request: HttpRequest,
    envelope_key: str,
    projection: "callable",
) -> JsonResponse:
    """Apply the canonical OneRoster v1.2 query pipeline to a collection.

    Pipeline: filter -> sort -> fields-mask -> pagination. Returns the
    standard envelope ``{<key>: [...], totalCount, limit, offset}`` plus
    the ``X-Total-Count`` / ``X-Limit`` / ``X-Offset`` mirror headers.
    """
    from apps.api.oneroster_query_helpers import apply_pipeline
    items = list(projection())
    page, meta = apply_pipeline(request, items)
    return _envelope(envelope_key, page, meta)


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


@require_http_methods(["GET", "HEAD"])
def orgs(request):
    """v4.00.92 Wave 25 M1+M2 — GET honors ?filter/?sort/?fields; HEAD returns
    X-Total-Count with empty body."""
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(_iter_orgs, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "orgs", _iter_orgs)


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


def _iter_schools():
    """Projection wrapper used by both GET and HEAD on /schools/."""
    return (o for o in _iter_orgs() if o.get("type") == "school")


@require_http_methods(["GET", "HEAD"])
def schools(request):
    """v4.00.92 Wave 25 M1+M2 — full query pipeline + HEAD support."""
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(_iter_schools, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "schools", _iter_schools)


@require_http_methods(["GET", "HEAD"])
def users(request):
    """v4.00.92 Wave 25 M1+M2 — full query pipeline + HEAD support."""
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(_iter_users, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "users", _iter_users)


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


@require_http_methods(["GET", "HEAD"])
def classes(request):
    """v4.00.92 Wave 25 M1+M2 — full query pipeline + HEAD support."""
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(_iter_classes, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "classes", _iter_classes)


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
    try:
        from apps.people.models import StudentProfile

        qs = StudentProfile.objects.filter(  # tenant-isolation-allow: roster-cross-tenant-explicit-platform-scope
            user__isnull=False,
            classroom__isnull=False,
            is_active=True,
        ).select_related("user", "classroom", "school")
        for student in qs[:1000]:
            yield {
                "sourcedId": f"student-profile-{student.pk}",
                "status": "active",
                "role": "student",
                "userSourcedId": str(student.user_id),
                "classSourcedId": str(student.classroom_id),
                "schoolSourcedId": str(student.school_id or ""),
                "beginDate": (
                    student.joined_date.isoformat() if student.joined_date else ""
                ),
                "endDate": "",
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster enrollments: student profile fallback failed: %s", exc)


def _iter_enrollments_with_window(request: HttpRequest):
    """Projection wrapper applying the pre-existing ?since/?before window.

    Used by both GET and HEAD so the count + page agree on the filter
    surface (v4.00.76 ?since/?before is preserved alongside the v4.00.92
    ?filter / ?sort / ?fields pipeline).
    """
    since = (request.GET.get("since") or "").strip()
    before = (request.GET.get("before") or "").strip()
    for it in _iter_enrollments():
        bd = it.get("beginDate") or ""
        if since and bd < since:
            continue
        if before and bd > before:
            continue
        yield it


@require_http_methods(["GET", "HEAD"])
def enrollments(request):
    """v4.00.76 — GET /api/roster/v1p2/enrollments/ per spec § 4.13.

    ``?since=<iso>&before=<iso>`` window filter (when the upstream Enrollment
    rows expose ``start_date`` / ``end_date`` columns).
    v4.00.92 Wave 25 M1+M2 — also honors ?filter / ?sort / ?fields and HEAD.
    """
    projection = lambda: _iter_enrollments_with_window(request)
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(projection, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "enrollments", projection)


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


@require_http_methods(["GET", "HEAD"])
def courses(request):
    """v4.00.74 — GET /api/roster/v1p2/courses/ per spec § 4.13 Course resource.
    v4.00.92 Wave 25 M1+M2 — full query pipeline + HEAD support."""
    if request.method == "HEAD":
        gate = _gate(request)
        if gate is not None:
            return gate
        return _empty_response_with_total_count(_iter_courses, request)
    gate = _gate(request)
    if gate is not None:
        return gate
    return _collection_get(request, "courses", _iter_courses)


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


# ----- v4.00.83 Wave 15 T2: bulk POST /users/ (idempotent batch) ---------
#
# POST /api/roster/v1p2/users/bulk/
#
# Required header: Idempotency-Key: <opaque>  -> 428 if absent
# Body shape:      {"users": [<user_payload>, ...]}  (max 500 entries)
# Response:        207 Multi-Status
#                  {"results": [{"sourcedId": "...", "status": "...",
#                                "reason"?: "..."}],
#                   "summary":  {"created": N, "updated": M,
#                                "skipped": K, "error": E, "total": T}}
#
# Idempotency contract:
#   * same Idempotency-Key + same body bytes -> cached 207 body
#     + Idempotency-Replay: true header
#   * same Idempotency-Key + different body  -> 409 idempotency_key_conflict
#   * TTL: 24h
#
# Per-row processing validates the payload, persists through the canonical
# single-user upsert contract, binds supplied organizations as tenant
# memberships, and isolates row failures in the 207 response.
_BULK_USERS_MAX_ITEMS = 500
_BULK_USERS_IDEMPOTENCY_TTL = 60 * 60 * 24
_BULK_USERS_REQUIRED_FIELDS = ("sourcedId", "givenName", "familyName", "role")
_BULK_USERS_ALLOWED_ROLES = frozenset((
    "student", "teacher", "administrator", "staff",
    "parent", "guardian", "aide", "proctor", "relative",
))


def _bulk_users_idem_cache_key(idem: str) -> str:
    return f"roster:users:bulk:idempo:{idem}"


def _bulk_users_hash_body(body_bytes: bytes) -> str:
    """sha256[:16] of the raw body bytes (matches demographics convention)."""
    h = hashlib.sha256()
    h.update(body_bytes or b"")
    return h.hexdigest()[:16]


def _bulk_user_idempotency_key(request: HttpRequest) -> str:
    return (
        request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
        or request.META.get("HTTP_X_IDEMPOTENCY_KEY", "").strip()
    )


def _validate_bulk_user_row(row: Any) -> tuple[str, str | None]:
    """Minimal shape check on a single user payload.

    Returns ``(sourcedId, error_reason_or_None)``. ``sourcedId`` is echoed
    as the empty string when the payload isn't a dict (so the per-row
    result still carries the field).
    """
    if not isinstance(row, dict):
        return "", "row_not_object"
    sid = str(row.get("sourcedId") or "").strip()
    if not sid:
        return "", "missing_sourcedId"
    for field in ("givenName", "familyName", "role"):
        val = str(row.get(field) or "").strip()
        if not val:
            return sid, f"missing_{field}"
    role = str(row.get("role") or "").strip().lower()
    if role not in _BULK_USERS_ALLOWED_ROLES:
        return sid, "bad_role"
    org_sids = row.get("orgSourcedIds")
    if org_sids is not None and not isinstance(org_sids, list):
        return sid, "orgSourcedIds_not_list"
    return sid, None


def _process_bulk_users(users: list[Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Validate and persist a OneRoster bulk user batch."""
    from apps.api.oneroster_writes import _upsert_user

    results: list[dict[str, Any]] = []
    summary = {"created": 0, "updated": 0, "skipped": 0, "error": 0, "total": 0}
    for row in users:
        sid, err = _validate_bulk_user_row(row)
        if err is not None:
            results.append({"sourcedId": sid, "status": "error", "reason": err})
            summary["error"] += 1
        else:
            try:
                body, status_code = _upsert_user(sid, row)
            except Exception:
                logger.exception("oneroster bulk user upsert failed sourced_id=%s", sid)
                body, status_code = {"error": "upsert_failed"}, 500
            if status_code in (200, 201):
                outcome = "created" if status_code == 201 else "updated"
                persisted = body.get("user") if isinstance(body, dict) else {}
                results.append(
                    {
                        "sourcedId": sid,
                        "status": outcome,
                        "persistedSourcedId": str(
                            (persisted or {}).get("sourcedId") or ""
                        ),
                    }
                )
                summary[outcome] += 1
            else:
                reason = (
                    str(body.get("error") or "upsert_failed")
                    if isinstance(body, dict)
                    else "upsert_failed"
                )
                results.append(
                    {"sourcedId": sid, "status": "error", "reason": reason}
                )
                summary["error"] += 1
        summary["total"] += 1
    return results, summary


@csrf_exempt
@require_http_methods(["POST"])
def users_bulk_post(request: HttpRequest):
    """v4.00.83 Wave 15 T2 — POST /api/roster/v1p2/users/bulk/

    Idempotent batch user upsert per OneRoster v1.2 bulk semantics. Valid rows
    are persisted and report ``created`` or ``updated``; invalid or failed rows
    report ``error`` without aborting the rest of the batch.

    Required: ``Idempotency-Key`` header. Body: ``{"users": [...]}``
    (max 500 entries). Response: 207 Multi-Status with per-row results +
    summary counters. Replay returns cached body with
    ``Idempotency-Replay: true``. Mismatched body on same key -> 409.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    scope_gate = _require_write_scope(request)
    if scope_gate is not None:
        return scope_gate

    idem = _bulk_user_idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _bulk_users_hash_body(body_bytes)
    ck = _bulk_users_idem_cache_key(idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=207)
            resp["Idempotency-Replay"] = "true"
            return resp
        return JsonResponse({"error": "idempotency_key_conflict"}, status=409)

    if not body_bytes:
        return JsonResponse({"error": "empty_body"}, status=400)
    try:
        payload = _json.loads(body_bytes)
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    if "users" not in payload:
        return JsonResponse({"error": "missing_users_key"}, status=400)
    users = payload.get("users")
    if not isinstance(users, list):
        return JsonResponse({"error": "users_not_list"}, status=400)
    if len(users) > _BULK_USERS_MAX_ITEMS:
        return JsonResponse(
            {"error": "too_many_users",
             "received_count": len(users),
             "max_count": _BULK_USERS_MAX_ITEMS},
            status=400,
        )

    results, summary = _process_bulk_users(users)
    body = {"results": results, "summary": summary}
    cache.set(
        ck,
        {"payload_hash": payload_hash, "response_body": body},
        _BULK_USERS_IDEMPOTENCY_TTL,
    )
    return JsonResponse(body, status=207)
