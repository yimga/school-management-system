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

Honest scope
------------
classes writes accept the envelope, validate it, and apply the title
update only when the corresponding model is identifiable in the
codebase. enrollments / academicSessions writes are still deferred to
the next wave (they need DRF-style class/user relation handling).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any, Callable

from django.core.cache import cache
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
            defaults={"name": name or identifier, "subdomain": identifier},
        )
        changed = False
        if name and obj.name != name:
            obj.name = name
            changed = True
        if changed:
            obj.save(update_fields=["name"])
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


def _upsert_user(sourced_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    username = (body.get("username") or "").strip()[:150]  # magic-number-allow: string-truncation-cap
    if not username:
        return {"error": "missing_username"}, 400

    given = (body.get("givenName") or "")[:150]  # magic-number-allow: string-truncation-cap
    family = (body.get("familyName") or "")[:150]  # magic-number-allow: string-truncation-cap
    email = (body.get("email") or "")[:254]  # magic-number-allow: string-truncation-cap

    with _PROCESS_LOCK:
        obj, created = User.objects.get_or_create(  # tenant-isolation-allow: roster-write-platform-scope
            username=username,
            defaults={"first_name": given, "last_name": family, "email": email},
        )
        changed = False
        for field, raw in (("first_name", given), ("last_name", family), ("email", email)):
            if raw and hasattr(obj, field) and getattr(obj, field) != raw:
                setattr(obj, field, raw)
                changed = True
        if changed:
            obj.save(update_fields=[f for f in ("first_name", "last_name", "email") if hasattr(obj, f)])

    payload = {
        "user": {
            "sourcedId": str(obj.pk),
            "status": "active",
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
        from apps.academics.models import Classroom
        from apps.schools.models import School
    except Exception as exc:  # noqa: BLE001
        return {"error": f"models_unavailable: {exc}"}, 500

    title = (body.get("title") or "").strip()[:120]
    course_code = (body.get("classCode") or body.get("courseCode") or "").strip()[:40]
    school_id = (body.get("school") or body.get("schoolSourcedId") or "").strip().lower()
    if not title:
        return {"error": "missing_title"}, 400
    if not school_id:
        return {"error": "missing_school_sourced_id"}, 400
    school = School.objects.filter(slug=school_id).first()  # tenant-isolation-allow: roster-write-resolve-school-by-sourced-id
    if school is None:
        return {"error": "school_not_found"}, 404

    with _PROCESS_LOCK:
        if course_code:
            obj, created = Classroom.objects.get_or_create(  # tenant-isolation-allow: roster-write-classroom-keyed-by-school-and-code
                school=school,
                code=course_code,
                defaults={"name": title},
            )
        else:
            obj, created = Classroom.objects.get_or_create(  # tenant-isolation-allow: roster-write-classroom-keyed-by-school-and-name
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

    payload = {
        "class": {
            "sourcedId": str(obj.pk),
            "status": "active",
            "title": obj.name,
            "classCode": getattr(obj, "code", ""),
            "school": school.slug,
        }
    }
    return payload, 201 if created else 200


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
