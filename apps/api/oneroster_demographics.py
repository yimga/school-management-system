"""v4.00.59 — OneRoster v1.2 Demographics endpoints (read-only).
v4.00.60 — Demographics POST/PUT write coverage.

Surfaces the OneRoster ``Demographic`` resource as a projection over
``apps.people.models.StudentProfile`` data. Sparse projection — only the
fields we actually hold (sex / birthDate) are populated; the rest of the
v1.2 spec fields are emitted as empty strings per the optional-field
contract.

Endpoints (mounted under ``/api/roster/v1p2/``):

* ``GET  demographics/`` — paginated list
* ``GET  demographics/<sourcedId>/`` — single record
* ``GET  students/<sourcedId>/demographics/`` — projection for one student
* ``POST demographics/put/`` — create/upsert a Demographic (Idempotency-Key)
* ``PUT  demographics/<sourcedId>/`` — update an existing Demographic by demo-<pk>

Writes are persisted on StudentProfile for the fields we model
(``gender``, ``date_of_birth``, ``place_of_birth``). The optional v1.2
race/ethnicity/citizenship fields are accepted-and-stored in an in-process
override ring (cap 500) so subsequent reads echo what the caller wrote
(matches the optional-field contract — caller-supplied data round-trips).

All endpoints are bearer-gated via the existing ``apps.api.oneroster._gate``
contract. NEVER raises — model unavailability returns 503; missing rows
return 404.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any, Iterable

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _envelope, _gate, _paginate

logger = logging.getLogger(__name__)


_GENDER_TO_SEX = {
    "MALE": "male",
    "FEMALE": "female",
    "NON_BINARY": "other",
    "OTHER": "other",
    "PREFER_NOT_TO_SAY": "",
}

# Inverse map for write-path: OneRoster `sex` → StudentProfile.Gender choice.
_SEX_TO_GENDER = {
    "male": "MALE",
    "female": "FEMALE",
    "other": "OTHER",
}

# v4.00.60 — In-process override ring for optional v1.2 fields that have no
# backing column on StudentProfile (race / ethnicity / citizenship / etc).
# Keyed by ``demo-<pk>``. Cap 500; eviction is oldest-first.
_DEMOGRAPHIC_OVERRIDES: dict[str, dict[str, str]] = {}
_DEMOGRAPHIC_OVERRIDES_CAP = 500
_DEMOGRAPHIC_OVERRIDE_FIELDS = (
    "americanIndianOrAlaskaNative",
    "asian",
    "blackOrAfricanAmerican",
    "nativeHawaiianOrOtherPacificIslander",
    "white",
    "demographicRaceTwoOrMoreRaces",
    "hispanicOrLatinoEthnicity",
    "countryOfBirthCode",
    "stateOfBirthAbbreviation",
    "publicSchoolResidenceStatus",
)


def _set_demographic_overrides(sid: str, payload: dict[str, Any]) -> None:
    """Store optional v1.2 fields the caller supplied. NEVER raises."""
    try:
        kept: dict[str, str] = {}
        for k in _DEMOGRAPHIC_OVERRIDE_FIELDS:
            if k in payload:
                kept[k] = str(payload.get(k) or "")[:64]
        if kept:
            _DEMOGRAPHIC_OVERRIDES[sid] = kept
            if len(_DEMOGRAPHIC_OVERRIDES) > _DEMOGRAPHIC_OVERRIDES_CAP:
                # oldest-first eviction
                first = next(iter(_DEMOGRAPHIC_OVERRIDES))
                _DEMOGRAPHIC_OVERRIDES.pop(first, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("demographic overrides set failed: %s", exc)


def _idempotency_key(request: HttpRequest) -> str:
    return (
        request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
        or request.META.get("HTTP_X_IDEMPOTENCY_KEY", "").strip()
    )


_IDEMPOTENCY_TTL = 60 * 60 * 24


def _idem_cache_key(sourced_id: str, idem: str) -> str:
    return f"roster:demographics:idempo:{sourced_id}:{idem}"


def _hash_payload(method: str, path: str, body_bytes: bytes) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(method.encode("ascii"))
    h.update(b"|")
    h.update(path.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(body_bytes)
    return h.hexdigest()


def _demographic_from_student(s) -> dict[str, Any]:
    """Project a StudentProfile row into a OneRoster Demographic dict.

    Sparse fields per the v1.2 contract: missing data emits an empty
    string rather than null so JSON consumers don't need null-checks.
    """
    birth_date = ""
    if getattr(s, "date_of_birth", None) is not None:
        try:
            birth_date = s.date_of_birth.isoformat()
        except Exception:  # noqa: BLE001
            birth_date = ""
    sex = _GENDER_TO_SEX.get((getattr(s, "gender", "") or "").upper(), "")
    date_last_modified = ""
    upd = getattr(s, "updated_at", None) or getattr(s, "modified_at", None)
    if upd is not None:
        try:
            date_last_modified = upd.isoformat()
        except Exception:  # noqa: BLE001
            date_last_modified = ""
    sid = f"demo-{s.pk}"
    # v4.00.61 — OneRoster v1.2 spec Appendix link field. Each Demographic
    # records the User sourcedIds it applies to. Our projection is 1:1
    # (one Demographic ← one StudentProfile ← one User), so the array
    # carries a single User.pk string. Empty when the StudentProfile
    # has no linked user (rare — orphaned profile rows).
    user_sourced_ids: list[str] = []
    user_id = getattr(s, "user_id", None)
    if user_id:
        user_sourced_ids.append(str(user_id))
    rec = {
        "sourcedId": sid,
        "status": "active",
        "dateLastModified": date_last_modified,
        "birthDate": birth_date,
        "sex": sex,
        "americanIndianOrAlaskaNative": "",
        "asian": "",
        "blackOrAfricanAmerican": "",
        "nativeHawaiianOrOtherPacificIslander": "",
        "white": "",
        "demographicRaceTwoOrMoreRaces": "",
        "hispanicOrLatinoEthnicity": "",
        "countryOfBirthCode": "",
        "stateOfBirthAbbreviation": "",
        "cityOfBirth": (getattr(s, "place_of_birth", "") or ""),
        "publicSchoolResidenceStatus": "",
        # v4.00.61 spec link field — GUIDRef array per IMS OneRoster v1.2.
        "userSourcedIds": user_sourced_ids,
    }
    # v4.00.60 — fold in any caller-supplied optional fields stored in the
    # override ring so caller-supplied race/ethnicity/citizenship round-trips.
    overrides = _DEMOGRAPHIC_OVERRIDES.get(sid)
    if overrides:
        for k, v in overrides.items():
            rec[k] = v
    return rec


def _iter_demographics() -> Iterable[dict[str, Any]]:
    try:
        from apps.people.models import StudentProfile
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster demographics: StudentProfile unavailable: %s", exc)
        return
    qs = StudentProfile.objects.all()  # tenant-isolation-allow: oneroster-demographics-platform-scope-bearer-auth
    for s in qs[:1000]:
        yield _demographic_from_student(s)


@require_http_methods(["GET"])
def demographics_collection(request: HttpRequest):
    """v4.00.59 — Paginated list of Demographic records.

    v4.00.61 — supports ``?userSourcedId=<pk>`` filter per OneRoster v1.2
    spec convention: returns only Demographic records whose ``userSourcedIds``
    array contains the supplied User sourcedId.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_demographics())
    user_filter = (request.GET.get("userSourcedId") or "").strip()
    if user_filter:
        items = [r for r in items if user_filter in (r.get("userSourcedIds") or [])]
    page, meta = _paginate(request, items)
    return _envelope("demographics", page, meta)


@require_http_methods(["GET"])
def demographic_detail(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Single Demographic record by sourcedId (``demo-<pk>``)."""
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("demo-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    pk = sourced_id[5:]
    if not pk:
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(pk=pk).first()  # tenant-isolation-allow: oneroster-demographic-by-pk-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"demographic": _demographic_from_student(obj)})


@require_http_methods(["GET"])
def student_demographics(request: HttpRequest, sourced_id: str):
    """v4.00.59 — Demographic for a single student, identified by user pk.

    ``sourced_id`` here is the student's user pk (matches the OneRoster
    students endpoint sourcedId, which projects User.pk).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(user_id=sourced_id).first()  # tenant-isolation-allow: oneroster-demographic-by-user-id-bearer-auth
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"demographic": _demographic_from_student(obj)})


# ---------------------------------------------------------------------------
# v4.00.60 — Demographics POST/PUT writes.
#
# POST /api/roster/v1p2/demographics/put/        — create/upsert
# PUT  /api/roster/v1p2/demographics/<sid>/      — update existing demo-<pk>
#
# Both require ``Idempotency-Key`` header. Body shape:
#   {"demographic": {
#       "sourcedId": "demo-12",   # required on PUT; optional on POST
#       "sex": "male" | "female" | "other",
#       "birthDate": "2008-04-15",
#       "cityOfBirth": "Lagos",
#       "studentSourcedId": "<student_pk>",   # required on POST when no sourcedId
#       # optional, accepted and round-tripped via override ring:
#       "americanIndianOrAlaskaNative": "yes"/"no"/"",
#       ...
#   }}
#
# Replay contract:
#   * same Idempotency-Key + same payload bytes → 200/201 cached body w/
#     ``Idempotency-Replay: true``
#   * same Idempotency-Key + different payload  → 409 idempotency mismatch
# ---------------------------------------------------------------------------

def _parse_demographic_payload(body_bytes: bytes):
    """Return (inner_dict, error_response_or_None)."""
    if not body_bytes:
        return None, JsonResponse({"error": "empty_body"}, status=400)
    try:
        payload = _json.loads(body_bytes)
    except (ValueError, TypeError):
        return None, JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("demographic")
    if not isinstance(inner, dict):
        return None, JsonResponse({"error": "missing_demographic_envelope"}, status=400)
    return inner, None


def _apply_demographic_to_student(s, inner: dict[str, Any]) -> None:
    """Write the mappable demographic fields onto a StudentProfile instance."""
    changed = False
    if "sex" in inner:
        sex_val = str(inner.get("sex") or "").strip().lower()
        gender = _SEX_TO_GENDER.get(sex_val, "")
        if gender and getattr(s, "gender", "") != gender:
            s.gender = gender
            changed = True
        elif sex_val == "" and getattr(s, "gender", ""):
            s.gender = ""
            changed = True
    if "birthDate" in inner:
        bd = str(inner.get("birthDate") or "").strip()
        if bd:
            try:
                from datetime import date as _date
                y, m, d = bd.split("-")
                s.date_of_birth = _date(int(y), int(m), int(d))
                changed = True
            except (ValueError, TypeError):
                pass
        else:
            if getattr(s, "date_of_birth", None) is not None:
                s.date_of_birth = None
                changed = True
    if "cityOfBirth" in inner:
        city = str(inner.get("cityOfBirth") or "")[:120]
        if getattr(s, "place_of_birth", "") != city:
            s.place_of_birth = city
            changed = True
    if changed:
        s.save()


@csrf_exempt
@require_http_methods(["POST"])
def post_demographic(request: HttpRequest):
    """v4.00.60 — POST /api/roster/v1p2/demographics/put/

    Creates or upserts a Demographic record. ``sourcedId`` resolves the
    target StudentProfile (``demo-<pk>``); otherwise ``studentSourcedId``
    points to a User (User.pk) which must have an existing StudentProfile.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("post", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    inner, err = _parse_demographic_payload(body_bytes)
    if err is not None:
        return err

    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)

    obj = None
    sid_in = str(inner.get("sourcedId") or "").strip()
    if sid_in.startswith("demo-"):
        pk_str = sid_in[5:]
        try:
            obj = StudentProfile.objects.filter(pk=pk_str).first()  # tenant-isolation-allow: oneroster-demographic-post-by-pk
        except (ValueError, TypeError):
            return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        stu_sid = str(inner.get("studentSourcedId") or "").strip()
        if not stu_sid:
            return JsonResponse({"error": "missing_student_sourced_id"}, status=400)
        try:
            obj = StudentProfile.objects.filter(user_id=stu_sid).first()  # tenant-isolation-allow: oneroster-demographic-post-by-user-id
        except (ValueError, TypeError):
            return JsonResponse({"error": "bad_student_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "student_not_found"}, status=404)

    _apply_demographic_to_student(obj, inner)
    sid_out = f"demo-{obj.pk}"
    _set_demographic_overrides(sid_out, inner)
    body = {"demographic": _demographic_from_student(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "status": 200, "response_body": body}, _IDEMPOTENCY_TTL)
    return JsonResponse(body, status=200)


@csrf_exempt
@require_http_methods(["PUT"])
def put_demographic(request: HttpRequest, sourced_id: str):
    """v4.00.60 — PUT /api/roster/v1p2/demographics/<sourced_id>/

    Updates an existing Demographic. ``sourced_id`` is ``demo-<pk>``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    if not sourced_id.startswith("demo-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    pk_str = sourced_id[5:]
    if not pk_str:
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(sourced_id, idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    inner, err = _parse_demographic_payload(body_bytes)
    if err is not None:
        return err

    try:
        from apps.people.models import StudentProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=503)
    try:
        obj = StudentProfile.objects.filter(pk=pk_str).first()  # tenant-isolation-allow: oneroster-demographic-put-by-pk
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    if obj is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    _apply_demographic_to_student(obj, inner)
    _set_demographic_overrides(sourced_id, inner)
    body = {"demographic": _demographic_from_student(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "status": 200, "response_body": body}, _IDEMPOTENCY_TTL)
    return JsonResponse(body, status=200)
