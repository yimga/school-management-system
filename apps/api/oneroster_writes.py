"""v4.00.38 — OneRoster v1.2 write endpoints.

PUT (single-row create-or-update) endpoints for the three primary
entities:

* ``PUT /api/roster/v1p2/orgs/<sourcedId>/``
* ``PUT /api/roster/v1p2/users/<sourcedId>/``
* ``PUT /api/roster/v1p2/classes/<sourcedId>/``

Spec contract
-------------
* PUT body is a single-entity JSON envelope ``{"org": {...}}`` /
  ``{"user": {...}}`` / ``{"class": {...}}``.
* Idempotency: the ``Idempotency-Key`` header is REQUIRED. Re-submitting
  the same key returns the cached response without re-applying the body
  (24h sliding window).
* PUT is upsert semantics: 201 on first create, 200 on subsequent
  update. Body returns the persisted shape.
* Auth: bearer token (same gate as read endpoints).

Class writes resolve tenant academic setup before creating a classroom.
Enrollment writes bind existing student profiles to tenant classrooms.
Academic-session writes remain read-only because changing calendars requires
the governed academic-year workflow rather than a generic roster upsert.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _gate, _require_write_scope

logger = logging.getLogger(__name__)


_IDEMPOTENCY_TTL = 60 * 60 * 24  # 24h
_PROCESS_LOCK = threading.Lock()


def _body_json(request: HttpRequest) -> dict[str, Any] | None:
    try:
        if not request.body:
            return None
        return json.loads(request.body)
    except (ValueError, TypeError):
        return None


def _idempotency_key(request: HttpRequest) -> str:
    return (
        request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
        or request.META.get("HTTP_X_IDEMPOTENCY_KEY", "").strip()
    )


def _hash_payload(method: str, path: str, body_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(method.encode("ascii"))
    h.update(b"|")
    h.update(path.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(body_bytes)
    return h.hexdigest()


def _cache_key(entity: str, sourced_id: str, idem: str) -> str:
    return f"roster:idempo:{entity}:{sourced_id}:{idem}"


def _idempotency_check(
    request: HttpRequest,
    entity: str,
    sourced_id: str,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Returns (idem_key, cached_response, error_code).

    * If no idempotency header → returns (None, None, "missing_idempotency_key").
    * If a cached response is found AND payload matches → returns it.
    * If a cached response is found AND payload differs → returns 409-equivalent.
    * Else returns (idem_key, None, None) — caller proceeds.
    """
    idem = _idempotency_key(request)
    if not idem:
        return None, None, "missing_idempotency_key"
    ck = _cache_key(entity, sourced_id, idem)
    payload_hash = _hash_payload(request.method, request.path, request.body or b"")
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            return idem, cached, None
        return idem, None, "idempotency_key_payload_mismatch"
    return idem, None, None


def _store_idempotency(
    entity: str,
    sourced_id: str,
    idem: str,
    request: HttpRequest,
    response_body: dict[str, Any],
    status: int,
) -> None:
    ck = _cache_key(entity, sourced_id, idem)
    payload_hash = _hash_payload(request.method, request.path, request.body or b"")
    try:
        cache.set(
            ck,
            {
                "payload_hash": payload_hash,
                "response_body": response_body,
                "status": status,
            },
            _IDEMPOTENCY_TTL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster writes: idempotency store failed: %s", exc)


def _spec_envelope_extract(body: dict[str, Any], entity_singular: str) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    inner = body.get(entity_singular)
    if not isinstance(inner, dict):
        return None
    return inner


# ----- per-entity handlers ------------------------------------------------


def _upsert_org(sourced_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    from apps.schools.models import School

    name = (body.get("name") or "").strip()[:255]
    identifier = (body.get("identifier") or sourced_id).strip()[:64].lower()
    if not identifier:
        return {"error": "missing_identifier"}, 400

    with _PROCESS_LOCK:
        obj, created = School.objects.get_or_create(  # tenant-isolation-allow: roster-write-platform-scope
            slug=identifier,
            # is_active=False so a newly-minted org is never a live husk (active
            # row, no schema/seed/owner). It is provisioned into usability below.
            # get_or_create ignores defaults on an existing row, so re-syncing a
            # live tenant never deactivates it.
            defaults={
                "name": name or identifier,
                "subdomain": identifier,
                "is_active": False,
            },
        )
        changed = False
        if name and obj.name != name:
            obj.name = name
            changed = True
        if changed:
            obj.save(update_fields=["name"])
    if created:
        # Reuse the importer's best-effort, on_commit-safe enqueue (local import
        # avoids import-time coupling between the two OneRoster modules).
        from apps.api.oneroster_csv_importer import _enqueue_provision_for_new_org

        _enqueue_provision_for_new_org(obj.pk)
    payload = {
        "org": {
            "sourcedId": str(obj.pk),
            "status": "active",
            "type": "school",
            "name": obj.name,
            "identifier": obj.slug,
        }
    }
    return payload, 201 if created else 200


def _user_role_value(role: str, User) -> str:
    normalized = str(role or "").strip().lower()
    role_map = {
        "student": User.Role.STUDENT,
        "teacher": User.Role.TEACHER,
        "administrator": User.Role.ADMIN,
        "staff": User.Role.ACADEMICS_STAFF,
        "aide": User.Role.ACADEMICS_STAFF,
        "proctor": User.Role.ACADEMICS_STAFF,
        "parent": User.Role.PARENT,
        "guardian": User.Role.PARENT,
        "relative": User.Role.PARENT,
    }
    return role_map.get(normalized, User.Role.PARENT)


def _schools_for_org_sourced_ids(org_sourced_ids: Any) -> list[Any]:
    if not isinstance(org_sourced_ids, list):
        return []
    raw_ids = [str(value or "").strip() for value in org_sourced_ids]
    raw_ids = [value for value in raw_ids if value][:20]
    if not raw_ids:
        return []

    from apps.schools.models import School

    found: dict[str, Any] = {}
    for school in School.objects.filter(slug__in=raw_ids):  # tenant-isolation-allow: roster-write-explicit-org-identifiers
        found[str(school.pk)] = school
    uuid_ids = []
    for value in raw_ids:
        try:
            uuid_ids.append(uuid.UUID(value))
        except (TypeError, ValueError, AttributeError):
            continue
    if uuid_ids:
        for school in School.objects.filter(pk__in=uuid_ids):  # tenant-isolation-allow: roster-write-explicit-org-identifiers
            found[str(school.pk)] = school
    return list(found.values())


@transaction.atomic
def _upsert_user(sourced_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    from django.contrib.auth import get_user_model
    from apps.schools.models import SchoolMembership

    User = get_user_model()
    username = (body.get("username") or sourced_id or "").strip()[:150]  # magic-number-allow: string-truncation-cap
    if not username:
        return {"error": "missing_username"}, 400

    given = (body.get("givenName") or "")[:150]  # magic-number-allow: string-truncation-cap
    family = (body.get("familyName") or "")[:150]  # magic-number-allow: string-truncation-cap
    email = (body.get("email") or "")[:254]  # magic-number-allow: string-truncation-cap
    role = _user_role_value(body.get("role") or "student", User)
    is_active = str(body.get("status") or "active").strip().lower() != "tobedeleted"

    with _PROCESS_LOCK:
        obj, created = User.objects.get_or_create(  # tenant-isolation-allow: roster-write-platform-scope
            username=username,
            defaults={
                "first_name": given,
                "last_name": family,
                "email": email,
                "role": role,
                "is_active": is_active,
            },
        )
        if created:
            obj.set_unusable_password()
        changed = False
        for field, raw in (
            ("first_name", given),
            ("last_name", family),
            ("email", email),
            ("role", role),
            ("is_active", is_active),
        ):
            if hasattr(obj, field) and getattr(obj, field) != raw:
                setattr(obj, field, raw)
                changed = True
        if created or changed:
            update_fields = [
                field
                for field in (
                    "first_name",
                    "last_name",
                    "email",
                    "role",
                    "is_active",
                    "password",
                )
                if hasattr(obj, field)
            ]
            obj.save(update_fields=update_fields)

        schools = _schools_for_org_sourced_ids(body.get("orgSourcedIds"))
        has_membership = obj.school_memberships.exists()
        for index, school in enumerate(schools):
            SchoolMembership.objects.update_or_create(
                user=obj,
                school=school,
                defaults={
                    "role": role,
                    "is_primary": not has_membership and index == 0,
                },
            )

    payload = {
        "user": {
            "sourcedId": str(obj.pk),
            "status": "active" if obj.is_active else "tobedeleted",
            "username": obj.username,
            "givenName": getattr(obj, "first_name", "") or "",
            "familyName": getattr(obj, "last_name", "") or "",
            "email": getattr(obj, "email", "") or "",
            "role": (body.get("role") or "student").strip() or "student",
        }
    }
    return payload, 201 if created else 200


def _upsert_class(sourced_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """v4.00.39 — real Classroom upserts.

    Resolves the school via ``school`` body field (the OneRoster
    ``schoolSourcedId``) which we mirror onto School.slug at import.
    Matches the existing Classroom by ``(school, code)`` if classCode
    is set; otherwise by ``(school, name)``.
    """
    try:
        from apps.academics.models import AcademicYear, Classroom, Department
        from apps.schools.models import School
    except Exception as exc:  # noqa: BLE001
        return {"error": f"models_unavailable: {exc}"}, 500

    title = (body.get("title") or "").strip()[:120]
    course_code = (
        body.get("classCode") or body.get("courseCode") or sourced_id or ""
    ).strip()[:30]
    school_id = (body.get("school") or body.get("schoolSourcedId") or "").strip().lower()
    if not title:
        return {"error": "missing_title"}, 400
    if not school_id:
        return {"error": "missing_school_sourced_id"}, 400
    school = School.objects.filter(slug=school_id).first()  # tenant-isolation-allow: roster-write-resolve-school-by-sourced-id
    if school is None:
        try:
            school = School.objects.filter(pk=uuid.UUID(school_id)).first()  # tenant-isolation-allow: roster-write-resolve-school-by-sourced-id
        except (TypeError, ValueError, AttributeError):
            school = None
    if school is None:
        return {"error": "school_not_found"}, 404

    with _PROCESS_LOCK:
        academic_year = (
            AcademicYear.objects.filter(school=school, is_active=True)
            .order_by("-start_date")
            .first()
            or AcademicYear.objects.filter(school=school)
            .order_by("-start_date")
            .first()
        )
        if academic_year is None:
            return {"error": "academic_year_not_found"}, 409
        department = Department.objects.filter(school=school).order_by("pk").first()
        if department is None:
            department, _ = Department.objects.get_or_create(
                school=school,
                code=f"{school.slug or str(school.pk)}-GEN"[:30],
                defaults={"name": "General"},
            )
        defaults = {
            "name": title,
            "academic_year": academic_year,
            "department": department,
        }
        if course_code:
            obj = Classroom.objects.filter(  # tenant-isolation-allow: roster-write-classroom-keyed-by-school-and-code
                school=school,
                code=course_code,
            ).first()
            created = obj is None
            if obj is None:
                # Store the code the roster system actually sent.
                #
                # ``Classroom.code`` is unique per ``(school, code)`` -- constraint
                # ``uniq_classroom_school_code``, academics migration 0085, which
                # mirrors 0076 for ``Department.code``. The column is NOT unique
                # platform-wide, so another tenant already holding this code is not
                # a collision the database would reject.
                #
                # This used to probe every tenant's rows and, on a hit, store
                # ``<slug>-<code>`` instead. That made an external integration's own
                # course code depend on an UNRELATED tenant's data: the same PUT
                # stored a different value depending on who else was on the
                # platform, the lookup directly above (keyed on the UNPREFIXED code,
                # which is this function's documented identity contract) then missed
                # its own row, and PUT reported the submitted code while a later GET
                # reported the rewritten one.
                #
                # The lookup above has already proved ``(school, course_code)`` is
                # free, so no further freshness probe is needed here.
                obj, created = Classroom.objects.get_or_create(
                    school=school,
                    code=course_code,
                    defaults=defaults,
                )
        else:
            obj, created = Classroom.objects.get_or_create(  # tenant-isolation-allow: roster-write-classroom-keyed-by-school-and-name
                school=school,
                name=title,
                defaults={
                    "code": sourced_id[:30],
                    "academic_year": academic_year,
                    "department": department,
                },
            )
        changed = False
        if obj.name != title:
            obj.name = title
            changed = True
        if changed:
            obj.save(update_fields=[f for f in ("name", "code") if hasattr(obj, f)])

    payload = {
        "class": {
            "sourcedId": str(obj.pk),
            "status": "active",
            "title": obj.name,
            "classCode": course_code or getattr(obj, "code", ""),
            "school": school.slug,
        }
    }
    return payload, 201 if created else 200


@transaction.atomic
def _upsert_enrollment(
    sourced_id: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    from django.contrib.auth import get_user_model

    from apps.academics.models import Classroom
    from apps.people.models import StudentProfile

    role = str(body.get("role") or "student").strip().lower()
    if role != "student":
        return {"error": "unsupported_enrollment_role"}, 422
    user_sourced_id = str(body.get("userSourcedId") or "").strip()
    class_sourced_id = str(body.get("classSourcedId") or "").strip()
    if not user_sourced_id or not class_sourced_id:
        return {"error": "missing_user_or_class_sourced_id"}, 400

    User = get_user_model()
    try:
        user = User.objects.filter(pk=user_sourced_id).first()  # tenant-isolation-allow: roster-write-explicit-user-sourced-id
    except (TypeError, ValueError, ValidationError):
        user = None
    try:
        classroom = Classroom.objects.filter(pk=class_sourced_id).select_related(  # tenant-isolation-allow: roster-write-explicit-class-sourced-id
            "school",
            "academic_year",
        ).first()
    except (TypeError, ValueError, ValidationError):
        classroom = None
    if user is None:
        return {"error": "user_not_found"}, 404
    if classroom is None:
        return {"error": "class_not_found"}, 404

    student = StudentProfile.objects.filter(user=user).first()  # tenant-isolation-allow: roster-write-explicit-user-profile
    if student is None:
        return {"error": "student_profile_not_found"}, 404
    if (
        student.school_id
        and classroom.school_id
        and student.school_id != classroom.school_id
    ):
        return {"error": "tenant_mismatch"}, 409

    previous_classroom_id = student.classroom_id
    is_delete = str(body.get("status") or "active").lower() == "tobedeleted"
    changed_fields: list[str] = []
    if is_delete and student.classroom_id == classroom.pk:
        student.classroom = None
        changed_fields.append("classroom")
    elif not is_delete and student.classroom_id != classroom.pk:
        student.classroom = classroom
        changed_fields.append("classroom")
    if not is_delete and student.school_id is None and classroom.school_id is not None:
        student.school_id = classroom.school_id
        changed_fields.append("school")
    if not is_delete and student.academic_year_id != classroom.academic_year_id:
        student.academic_year_id = classroom.academic_year_id
        changed_fields.append("academic_year")
    if changed_fields:
        student.save(update_fields=[*changed_fields, "updated_at"])
        # Keep the enrollment (the source of truth for a placement) in step with
        # the legacy fields this rail writes, or the two disagree (item 2.2).
        from apps.people.enrollment_services import set_placement

        set_placement(student)

    payload = {
        "enrollment": {
            "sourcedId": sourced_id or f"student-profile-{student.pk}",
            "status": "tobedeleted" if is_delete else "active",
            "role": "student",
            "userSourcedId": str(user.pk),
            "classSourcedId": str(classroom.pk),
            "schoolSourcedId": str(classroom.school_id or ""),
            "beginDate": str(body.get("beginDate") or ""),
            "endDate": str(body.get("endDate") or ""),
        }
    }
    return payload, 201 if previous_classroom_id is None else 200


# ----- generic dispatcher -------------------------------------------------


def _handle_put(
    request: HttpRequest,
    entity: str,
    sourced_id: str,
    upsert_fn: Callable[[str, dict[str, Any]], tuple[dict[str, Any], int]],
) -> JsonResponse:
    gate = _gate(request)
    if gate is not None:
        return gate
    scope_gate = _require_write_scope(request)
    if scope_gate is not None:
        return scope_gate

    body = _body_json(request)
    if body is None:
        return JsonResponse({"success": False, "error": "bad_json"}, status=400)
    inner = _spec_envelope_extract(body, entity)
    if inner is None:
        return JsonResponse({"success": False, "error": f"missing_{entity}_envelope"}, status=400)

    idem, cached, err = _idempotency_check(request, entity, sourced_id)
    if err == "missing_idempotency_key":
        return JsonResponse({"success": False, "error": err}, status=428)  # Precondition Required
    if err == "idempotency_key_payload_mismatch":
        return JsonResponse({"success": False, "error": err}, status=409)
    if cached is not None:
        resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
        resp["Idempotency-Replay"] = "true"
        return resp

    try:
        body_out, status = upsert_fn(sourced_id, inner)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oneroster writes: upsert %s/%s failed: %s", entity, sourced_id, exc)
        return JsonResponse({"success": False, "error": "upsert_failed"}, status=500)

    if idem:
        _store_idempotency(entity, sourced_id, idem, request, body_out, status)
    resp = JsonResponse(body_out, status=status)
    resp["X-OneRoster-Entity"] = entity
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_org(request, sourced_id: str):
    return _handle_put(request, "org", sourced_id, _upsert_org)


@csrf_exempt
@require_http_methods(["PUT"])
def put_user(request, sourced_id: str):
    return _handle_put(request, "user", sourced_id, _upsert_user)


@csrf_exempt
@require_http_methods(["PUT"])
def put_class(request, sourced_id: str):
    return _handle_put(request, "class", sourced_id, _upsert_class)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def org_resource(request, sourced_id: str):
    if request.method == "PUT":
        return put_org(request, sourced_id)
    from apps.api.oneroster import org_detail

    return org_detail(request, sourced_id)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def class_resource(request, sourced_id: str):
    if request.method == "PUT":
        return put_class(request, sourced_id)
    from apps.api.oneroster import class_detail

    return class_detail(request, sourced_id)
