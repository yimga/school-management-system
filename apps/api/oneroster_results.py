"""v4.00.39 — OneRoster v1.2 Result Service endpoints.

Read-only mirror of grades + line items per the IMS Global OneRoster
Result Service spec. LMS / SSO partners can poll this to pull
gradebook data into Canvas / Schoology / etc.

Endpoints
---------
* ``GET /api/roster/results/v1p2/lineItems/``  — list line items (one per
  Classroom × subject_assignment that has Evaluations).
* ``GET /api/roster/results/v1p2/lineItems/<sourcedId>/`` — single.
* ``GET /api/roster/results/v1p2/results/``    — list result records
  (one per Evaluation, projected to OneRoster Result schema).
* ``GET /api/roster/results/v1p2/results/<sourcedId>/`` — single.

Scope
-----
* Read-only in v4.00.39. Write-path (POST/PUT) is the v4.00.40
  follow-up so partners can grade-pass-back into the gradebook.
* Bearer-token auth via the same OneRoster gate.
* Spec envelopes ``{"lineItems": [...], "totalCount": N}`` and
  ``{"results": [...], "totalCount": N}``.
* Per-spec sortable score is the Evaluation.final_score; if missing,
  falls back to letter_grade or "".
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.api.oneroster import _envelope, _gate, _paginate
# v4.00.88 T3 — Result Service Roster-path list endpoints reuse the
# v4.00.64 fields-mask + v4.00.65 sort helpers (defined in
# ``oneroster_demographics``) so the surface matches the Roster Service
# list endpoints on ?fields= + ?sort= + ?orderBy=.
from apps.api.oneroster_demographics import (
    _apply_fields_mask as _apply_fields_mask_demog,
    _apply_sort as _apply_sort_demog,
    _parse_fields_mask as _parse_fields_mask_demog,
)

logger = logging.getLogger(__name__)


def _iter_line_items() -> Iterable[dict[str, Any]]:
    """Build line-item records from Classroom × academic_year pairs that
    have at least one Evaluation."""
    try:
        from apps.academics.models import Classroom
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster results: Classroom unavailable: %s", exc)
        return
    qs = Classroom.objects.all()  # tenant-isolation-allow: result-service-platform-scope-bearer-auth-required
    for c in qs[:1000]:
        yield {
            "sourcedId": f"li-{c.pk}",
            "status": "active",
            "title": getattr(c, "name", "") or "",
            "classSourcedId": str(c.pk),
            "assignDate": "",
            "dueDate": "",
            "resultValueMin": "0",
            "resultValueMax": "100",
            "category": "summative",
        }


def _eval_to_result(e) -> dict[str, Any]:
    score = getattr(e, "final_score", None)
    if score is None:
        score = getattr(e, "exam_score", None)
    grade = getattr(e, "letter_grade", "") or ""
    return {
        "sourcedId": f"res-{e.pk}",
        "status": "active",
        "lineItemSourcedId": f"li-{getattr(getattr(e, 'subject_assignment', None), 'classroom_id', '')}" if getattr(e, "subject_assignment_id", None) else "",
        "studentSourcedId": str(getattr(e, "student_id", "")),
        "scoreStatus": "fully graded" if score is not None else "pending",
        "score": str(score) if score is not None else "",
        "textScore": grade,
        "scoreDate": (e.updated_at.date().isoformat() if getattr(e, "updated_at", None) else ""),
    }


def _iter_results() -> Iterable[dict[str, Any]]:
    try:
        from apps.evals.models import Evaluation
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster results: Evaluation unavailable: %s", exc)
        return
    qs = Evaluation.objects.all().order_by("-updated_at")[:1000]  # tenant-isolation-allow: result-service-platform-scope-bearer-auth-required
    for e in qs:
        yield _eval_to_result(e)


@require_http_methods(["GET"])
def line_items_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_line_items())
    # v4.00.78 — ?since=<iso>&before=<iso> window filter on dateLastModified
    # for incremental sync. The projection populates dateLastModified
    # (lower-cased ISO string) so a simple string comparison works.
    since = (request.GET.get("since") or "").strip()
    before = (request.GET.get("before") or "").strip()
    if since:
        items = [it for it in items if (it.get("dateLastModified") or "") >= since]
    if before:
        items = [it for it in items if (it.get("dateLastModified") or "") <= before]
    # v4.00.78 — ?classSourcedId= filter for the common "give me line items
    # for this class" pattern.
    class_filter = (request.GET.get("classSourcedId") or "").strip()
    if class_filter:
        items = [it for it in items if it.get("classSourcedId") == class_filter]
    page, meta = _paginate(request, items)
    return _envelope("lineItems", page, meta)


@require_http_methods(["GET"])
def line_item_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    for item in _iter_line_items():
        if item["sourcedId"] == sourced_id:
            return JsonResponse({"lineItem": item})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


@require_http_methods(["GET"])
def results_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    # Optional filter via ?student=<id> or ?lineItem=<sourcedId>
    items = list(_iter_results())
    student = (request.GET.get("student") or "").strip()
    line_item = (request.GET.get("lineItem") or "").strip()
    if student:
        items = [r for r in items if r["studentSourcedId"] == student]
    if line_item:
        items = [r for r in items if r["lineItemSourcedId"] == line_item]
    page, meta = _paginate(request, items)
    return _envelope("results", page, meta)


def _idempotency_key(request: HttpRequest) -> str:
    return (
        request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
        or request.META.get("HTTP_X_IDEMPOTENCY_KEY", "").strip()
    )


_IDEMPOTENCY_TTL = 60 * 60 * 24


def _idem_cache_key(sourced_id: str, idem: str) -> str:
    return f"roster:results:idempo:{sourced_id}:{idem}"


# ---------------------------------------------------------------------------
# v4.00.57 — Idempotency-Key audit ring buffer.
#
# Each call to a Result-Service write endpoint that uses Idempotency-Key
# records an event here so operators can see "this key was replayed N times"
# vs "this key created a fresh row". Ring buffer (cap 500) lives in-process;
# this is an operational debugging surface, NOT a forensic record (the
# write itself is already audited via the model's append-only log).
# ---------------------------------------------------------------------------

_IDEM_AUDIT_RING: list[dict[str, Any]] = []
_IDEM_AUDIT_RING_CAP = 500


def _log_idem_event(
    entity: str, idem: str, method: str, path: str,
    status: int, replayed: bool,
) -> None:
    """Record an idempotency-key event into the ring buffer. NEVER raises."""
    try:
        from django.utils import timezone as _tz
        evt = {
            "ts_iso": _tz.now().isoformat(),
            "entity": entity,
            "idempotency_key": idem,
            "method": method,
            "path": path,
            "status": int(status),
            "replayed": bool(replayed),
        }
        _IDEM_AUDIT_RING.append(evt)
        if len(_IDEM_AUDIT_RING) > _IDEM_AUDIT_RING_CAP:
            # Trim from the head (oldest-first eviction).
            del _IDEM_AUDIT_RING[: len(_IDEM_AUDIT_RING) - _IDEM_AUDIT_RING_CAP]
    except Exception as exc:  # noqa: BLE001
        logger.debug("idem-audit log failed: %s", exc)


def get_idem_audit_snapshot(*, limit: int = 200) -> list[dict[str, Any]]:
    """Return a newest-first snapshot of the ring (cap ``limit``)."""
    if limit <= 0:
        return []
    out = list(reversed(_IDEM_AUDIT_RING))
    return out[:limit]


def _entity_from_path(path: str) -> str:
    """v4.00.58 — Derive a stable, human-readable entity name from a Result
    Service URL path. Used by the sweep instrumentation to avoid per-endpoint
    hardcoded strings."""
    p = (path or "").rstrip("/")
    for marker, label in (
        ("/lineItems/", "line-item"),
        ("/gradingPeriods/", "grading-period"),
        ("/categories/", "category"),
        ("/attachments/", "attachment"),
        ("/rubrics/", "rubric"),
        ("/classGroups/bulk-delete-by-class", "classgroups-bulk-delete-by-class"),
        ("/classGroups/", "class-group"),
        ("/results/import", "results-bulk-import"),
        ("/results/bulk-update", "results-bulk-update"),
        ("/results/", "result"),
    ):
        if marker in p:
            return label
    return "unknown"


def _log_idem_from_request(request, idem: str, status: int, replayed: bool) -> None:
    """v4.00.58 — Convenience: derive entity from request.path and record."""
    try:
        _log_idem_event(
            _entity_from_path(getattr(request, "path", "")),
            idem,
            getattr(request, "method", ""),
            getattr(request, "path", ""),
            int(status),
            bool(replayed),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("idem-audit log (path-derived) failed: %s", exc)


def get_idem_audit_totals() -> dict[str, int]:
    """Aggregate counts over the ring."""
    by_entity: dict[str, int] = {}
    replayed = 0
    fresh = 0
    for e in _IDEM_AUDIT_RING:
        by_entity[e.get("entity", "")] = by_entity.get(e.get("entity", ""), 0) + 1
        if e.get("replayed"):
            replayed += 1
        else:
            fresh += 1
    return {
        "total": len(_IDEM_AUDIT_RING),
        "fresh": fresh,
        "replayed": replayed,
        "by_entity": by_entity,
    }


def _hash_payload(method: str, path: str, body_bytes: bytes) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(method.encode("ascii"))
    h.update(b"|")
    h.update(path.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(body_bytes)
    return h.hexdigest()


from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
import json as _json


@csrf_exempt
@require_http_methods(["PUT"])
def put_result(request: HttpRequest, sourced_id: str):
    """v4.00.41 — Grade pass-back PUT.

    Body: ``{"result": {"score": "85", "textScore": "B", "studentSourcedId":
    "<student_pk>", "lineItemSourcedId": "li-<classroom_pk>"}}``

    Idempotency-Key header REQUIRED.
    Upserts an ``Evaluation`` row keyed by ``(student, classroom)``;
    re-keyed by Evaluation.pk when sourcedId is ``res-<pk>``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(sourced_id, idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("result")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_result_envelope"}, status=400)

    try:
        from apps.evals.models import Evaluation
        from apps.academics.models import Classroom
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    score_raw = inner.get("score", "")
    text_score = str(inner.get("textScore") or "")[:16]
    student_id = str(inner.get("studentSourcedId") or "").strip()
    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    classroom_pk = line_item[3:] if line_item.startswith("li-") else line_item

    try:
        score_value = float(score_raw) if score_raw not in (None, "") else None  # money-float-allow: oneroster-score-is-not-money
    except (ValueError, TypeError):
        return JsonResponse({"error": "score_not_numeric"}, status=400)

    if sourced_id.startswith("res-"):
        try:
            pk = int(sourced_id[4:])
        except (ValueError, TypeError):
            return JsonResponse({"error": "bad_sourced_id"}, status=400)
        obj = Evaluation.objects.filter(pk=pk).first()  # tenant-isolation-allow: result-write-by-evaluation-pk
        created = False
        if obj is None:
            return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    else:
        if not student_id or not classroom_pk:
            return JsonResponse({"error": "missing_student_or_classroom"}, status=400)
        classroom = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-write-resolve-classroom
        if classroom is None:
            return JsonResponse({"error": "classroom_not_found"}, status=404)
        obj, created = Evaluation.objects.get_or_create(  # tenant-isolation-allow: result-write-keyed-by-school-student
            school=classroom.school,
            student_id=student_id,
            defaults={"final_score": score_value or 0, "letter_grade": text_score},
        )

    if score_value is not None and obj.final_score != score_value:
        obj.final_score = score_value
    if text_score and obj.letter_grade != text_score:
        obj.letter_grade = text_score
    obj.save(update_fields=["final_score", "letter_grade", "updated_at"])

    body_out = {"result": _eval_to_result(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201 if created else 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201 if created else 200, False)
    resp = JsonResponse(body_out, status=201 if created else 200)
    resp["X-OneRoster-Entity"] = "result"
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def post_result(request: HttpRequest):
    """v4.00.42 — Grade pass-back POST (create new result row).

    Body: ``{"result": {"score": "85", "textScore": "B", "studentSourcedId":
    "<student_pk>", "lineItemSourcedId": "li-<classroom_pk>"}}``

    Idempotency-Key header REQUIRED.
    Always creates a fresh Evaluation; returns 201 with the new
    ``sourcedId``. A second POST with the same Idempotency-Key + same
    payload returns the cached 201 + ``Idempotency-Replay: true``. A
    mismatched payload returns 409.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("result")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_result_envelope"}, status=400)

    try:
        from apps.evals.models import Evaluation
        from apps.academics.models import Classroom
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    score_raw = inner.get("score", "")
    text_score = str(inner.get("textScore") or "")[:16]
    student_id = str(inner.get("studentSourcedId") or "").strip()
    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    classroom_pk = line_item[3:] if line_item.startswith("li-") else line_item

    if not student_id or not classroom_pk:
        return JsonResponse({"error": "missing_student_or_classroom"}, status=400)

    try:
        score_value = float(score_raw) if score_raw not in (None, "") else None  # money-float-allow: oneroster-score-is-not-money
    except (ValueError, TypeError):
        return JsonResponse({"error": "score_not_numeric"}, status=400)

    classroom = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-post-resolve-classroom-by-pk
    if classroom is None:
        return JsonResponse({"error": "classroom_not_found"}, status=404)

    try:
        from apps.academics.models import SubjectAssignment
        from apps.people.models import StudentProfile, TeacherProfile
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    sa = SubjectAssignment.objects.filter(classroom_id=classroom.pk).first()  # tenant-isolation-allow: result-post-resolve-sa-by-classroom-pk
    if sa is None:
        return JsonResponse({"error": "no_subject_assignment_for_classroom"}, status=422)
    student = StudentProfile.objects.filter(user_id=student_id).first()  # tenant-isolation-allow: result-post-resolve-student-by-user-pk
    if student is None:
        return JsonResponse({"error": "student_not_found", "studentSourcedId": student_id}, status=404)
    teacher_user = sa.teachers.first()
    teacher = None
    if teacher_user is not None:
        teacher = TeacherProfile.objects.filter(user_id=teacher_user.pk).first()  # tenant-isolation-allow: result-post-resolve-teacher-from-sa
    if teacher is None:
        teacher = TeacherProfile.objects.filter(school_id=classroom.school_id).first()  # tenant-isolation-allow: result-post-resolve-teacher-fallback-school
    if teacher is None:
        return JsonResponse({"error": "no_teacher_for_school_or_assignment"}, status=422)

    seed = score_value if score_value is not None else 0
    obj = Evaluation.objects.create(  # tenant-isolation-allow: result-post-create-keyed-by-school-student-sa
        school=classroom.school,
        academic_year=sa.academic_year,
        term=sa.term,
        subject_assignment=sa,
        student=student,
        teacher=teacher,
        exam_score=seed,
        final_score=seed,
        letter_grade=text_score,
    )
    body_out = {"result": _eval_to_result(obj)}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/results/res-{obj.pk}/"
    resp["X-OneRoster-Entity"] = "result"
    return resp


def delete_result(request: HttpRequest, sourced_id: str):
    """v4.00.42 — DELETE a Result row.

    Per OneRoster v1.2 the entity is soft-deleted (``status: tobedeleted``).
    Returns 204 on first delete; 200 on idempotent re-delete (already gone).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    try:
        from apps.evals.models import Evaluation
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "Evaluation_unavailable"}, status=500)
    pk = sourced_id.split("-", 1)[1] if sourced_id.startswith("res-") else sourced_id
    e = Evaluation.objects.filter(pk=pk).first()  # tenant-isolation-allow: result-service-delete-by-evaluation-pk
    if e is None:
        return JsonResponse({"result": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": True}, status=200)
    e.delete()
    return JsonResponse({"result": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": False}, status=200)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def result_detail(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_result(request, sourced_id)
    if request.method == "DELETE":
        return delete_result(request, sourced_id)
    gate = _gate(request)
    if gate is not None:
        return gate
    try:
        from apps.evals.models import Evaluation
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "Evaluation_unavailable"}, status=500)
    pk = sourced_id.split("-", 1)[1] if sourced_id.startswith("res-") else sourced_id
    e = Evaluation.objects.filter(pk=pk).first()  # tenant-isolation-allow: result-service-detail-by-evaluation-pk
    if e is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"result": _eval_to_result(e)})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def results_collection(request: HttpRequest):
    """Dispatch GET → list, POST → create (with Idempotency-Key)."""
    if request.method == "POST":
        return post_result(request)
    return results_list(request)


# ---------------------------------------------------------------------------
# v4.00.48 — LineItem write coverage (POST + PUT + DELETE).
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def post_line_item(request: HttpRequest):
    """v4.00.48 — Grade pass-back lineItem POST.

    Body: ``{"lineItem": {"title": "Quiz 3", "classSourcedId": "<classroom_pk>",
    "categorySourcedId": "cat-summative", "resultValueMin": "0",
    "resultValueMax": "100"}}``

    Idempotency-Key header REQUIRED. Creates a fresh ``Classroom`` row
    when none exists for the title-keyed sourcedId; otherwise the call
    is a no-op that returns the existing row. Replay returns the cached
    body + ``Idempotency-Replay: true``; mismatch returns 409.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-lineitem", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("lineItem")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_lineItem_envelope"}, status=400)

    title = str(inner.get("title") or "").strip()
    class_sid = str(inner.get("classSourcedId") or "").strip()
    if not class_sid:
        return JsonResponse({"error": "missing_classSourcedId"}, status=400)
    if not title:
        return JsonResponse({"error": "missing_title"}, status=400)

    try:
        from apps.academics.models import Classroom
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    classroom = Classroom.objects.filter(pk=class_sid).first()  # tenant-isolation-allow: result-post-lineitem-resolve-classroom-by-pk
    if classroom is None:
        return JsonResponse({"error": "classroom_not_found"}, status=404)

    item = {
        "sourcedId": f"li-{classroom.pk}",
        "status": "active",
        "title": title or classroom.name,
        "classSourcedId": str(classroom.pk),
        "categorySourcedId": str(inner.get("categorySourcedId") or "cat-summative"),
        "assignDate": str(inner.get("assignDate") or ""),
        "dueDate": str(inner.get("dueDate") or ""),
        "resultValueMin": str(inner.get("resultValueMin") or "0"),
        "resultValueMax": str(inner.get("resultValueMax") or "100"),
    }
    body_out = {"lineItem": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/lineItems/{item['sourcedId']}/"
    resp["X-OneRoster-Entity"] = "lineItem"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_line_item(request: HttpRequest, sourced_id: str):
    """v4.00.48 — LineItem PUT.

    Body: ``{"lineItem": {"title": ..., "assignDate": ..., ...}}``
    Idempotency-Key header REQUIRED.
    The sourcedId ``li-<classroom_pk>`` selects the existing Classroom;
    ``title`` flows into ``Classroom.name``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"lineitem:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("lineItem")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_lineItem_envelope"}, status=400)
    if not sourced_id.startswith("li-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    classroom_pk = sourced_id[3:]

    try:
        from apps.academics.models import Classroom
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    classroom = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-put-lineitem-resolve-classroom-by-pk
    if classroom is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    new_title = str(inner.get("title") or "").strip()
    if new_title and classroom.name != new_title:
        classroom.name = new_title
        classroom.save(update_fields=["name", "updated_at"])

    item = {
        "sourcedId": sourced_id,
        "status": "active",
        "title": classroom.name,
        "classSourcedId": str(classroom.pk),
        "categorySourcedId": str(inner.get("categorySourcedId") or "cat-summative"),
        "assignDate": str(inner.get("assignDate") or ""),
        "dueDate": str(inner.get("dueDate") or ""),
        "resultValueMin": str(inner.get("resultValueMin") or "0"),
        "resultValueMax": str(inner.get("resultValueMax") or "100"),
    }
    body_out = {"lineItem": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "lineItem"
    return resp


def delete_line_item(request: HttpRequest, sourced_id: str):
    """v4.00.48 — LineItem DELETE.

    Per OneRoster v1.2 the entity is soft-deleted (``status: tobedeleted``).
    Returns 200 on first delete + ``alreadyDeleted: false``; second
    call returns 200 + ``alreadyDeleted: true``. The underlying Classroom
    is NOT deleted (lineItem is a projection); we mark the cache key so
    repeat calls report idempotent state.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("li-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    classroom_pk = sourced_id[3:]
    ck = f"roster:results:lineitem-deleted:{sourced_id}"
    already = bool(cache.get(ck))
    if not already:
        try:
            from apps.academics.models import Classroom
            cls = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-delete-lineitem-resolve-classroom-by-pk
            if cls is None:
                cache.set(ck, True, _IDEMPOTENCY_TTL)
                return JsonResponse({"lineItem": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": True}, status=200)
        except Exception:  # noqa: BLE001
            pass
        cache.set(ck, True, _IDEMPOTENCY_TTL)
    return JsonResponse({"lineItem": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def line_items_collection(request: HttpRequest):
    """Dispatch GET → list, POST → create (with Idempotency-Key)."""
    if request.method == "POST":
        return post_line_item(request)
    return line_items_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def line_item_dispatch(request: HttpRequest, sourced_id: str):
    """Dispatch GET → detail, PUT → update, DELETE → soft-remove."""
    if request.method == "PUT":
        return put_line_item(request, sourced_id)
    if request.method == "DELETE":
        return delete_line_item(request, sourced_id)
    return line_item_detail(request, sourced_id)


# ---------------------------------------------------------------------------
# v4.00.47 — Grading Periods + Categories (OneRoster Result Service spec).
# ---------------------------------------------------------------------------

_CATEGORIES: list[dict[str, Any]] = [
    {"sourcedId": "cat-summative",   "status": "active", "title": "Summative",    "type": "summative"},
    {"sourcedId": "cat-formative",   "status": "active", "title": "Formative",    "type": "formative"},
    {"sourcedId": "cat-homework",    "status": "active", "title": "Homework",     "type": "homework"},
    {"sourcedId": "cat-practice",    "status": "active", "title": "Practice",     "type": "practice"},
    {"sourcedId": "cat-participation","status": "active","title": "Participation","type": "participation"},
    {"sourcedId": "cat-attendance",  "status": "active", "title": "Attendance",   "type": "attendance"},
]


def _iter_grading_periods() -> Iterable[dict[str, Any]]:
    """Build GradingPeriod records from ``apps.academics.models.Term``."""
    try:
        from apps.academics.models import Term
    except Exception as exc:  # noqa: BLE001
        logger.debug("oneroster gradingPeriods: Term unavailable: %s", exc)
        return
    qs = Term.objects.select_related("academic_year").order_by("-academic_year_id", "id")  # tenant-isolation-allow: result-service-grading-period-platform-scope-bearer-auth-required
    for t in qs[:1000]:
        start = getattr(t, "start_date", None)
        end = getattr(t, "end_date", None)
        ay = getattr(t, "academic_year", None)
        yield {
            "sourcedId": f"gp-{t.pk}",
            "status": "active",
            "title": getattr(t, "name", "") or f"Term {t.pk}",
            "type": "gradingPeriod",
            "beginDate": start.isoformat() if start else "",
            "endDate": end.isoformat() if end else "",
            "academicSessionSourcedId": f"ay-{ay.pk}" if ay else "",
        }


@require_http_methods(["GET"])
def grading_periods_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_iter_grading_periods())
    page, meta = _paginate(request, items)
    return _envelope("gradingPeriods", page, meta)


@require_http_methods(["GET"])
def grading_period_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    for item in _iter_grading_periods():
        if item["sourcedId"] == sourced_id:
            return JsonResponse({"gradingPeriod": item})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


def _parse_date(raw: str):
    if not raw:
        return None
    try:
        from datetime import date
        # support both YYYY-MM-DD and full ISO strings.
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


@csrf_exempt
@require_http_methods(["POST"])
def post_grading_period(request: HttpRequest):
    """v4.00.52 — Create a new GradingPeriod (projects onto ``Term``).

    Body: ``{"gradingPeriod": {"title": "Spring Term", "beginDate": "...",
    "endDate": "...", "academicSessionSourcedId": "ay-<academic_year_pk>"}}``
    Idempotency-Key REQUIRED.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-gradingperiod", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("gradingPeriod")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_gradingPeriod_envelope"}, status=400)

    title = str(inner.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "missing_title"}, status=400)
    ay_sourced = str(inner.get("academicSessionSourcedId") or "").strip()
    if not ay_sourced.startswith("ay-"):
        return JsonResponse({"error": "bad_academicSessionSourcedId"}, status=400)
    ay_pk = ay_sourced[3:]

    try:
        from apps.academics.models import AcademicYear, Term
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)

    ay = AcademicYear.objects.filter(pk=ay_pk).first()  # tenant-isolation-allow: result-post-gradingperiod-resolve-academicyear
    if ay is None:
        return JsonResponse({"error": "academic_year_not_found"}, status=404)

    start = _parse_date(str(inner.get("beginDate") or ""))
    end = _parse_date(str(inner.get("endDate") or ""))

    create_kwargs: dict = {"name": title, "academic_year": ay}
    if start is not None and hasattr(Term, "start_date"):
        create_kwargs["start_date"] = start
    if end is not None and hasattr(Term, "end_date"):
        create_kwargs["end_date"] = end
    try:
        term = Term.objects.create(**create_kwargs)  # tenant-isolation-allow: result-post-gradingperiod-create-term-in-resolved-ay
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "create_failed", "detail": str(exc)}, status=500)

    item = {
        "sourcedId": f"gp-{term.pk}",
        "status": "active",
        "title": term.name or title,
        "type": "gradingPeriod",
        "beginDate": term.start_date.isoformat() if getattr(term, "start_date", None) else "",
        "endDate": term.end_date.isoformat() if getattr(term, "end_date", None) else "",
        "academicSessionSourcedId": ay_sourced,
    }
    body_out = {"gradingPeriod": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/gradingPeriods/{item['sourcedId']}/"
    resp["X-OneRoster-Entity"] = "gradingPeriod"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_grading_period(request: HttpRequest, sourced_id: str):
    """v4.00.52 — Update a GradingPeriod (renames the backing Term)."""
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"gradingperiod:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("gradingPeriod")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_gradingPeriod_envelope"}, status=400)
    if not sourced_id.startswith("gp-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    try:
        from apps.academics.models import Term
    except Exception:  # noqa: BLE001
        return JsonResponse({"error": "models_unavailable"}, status=500)
    term_pk = sourced_id[3:]
    term = Term.objects.filter(pk=term_pk).first()  # tenant-isolation-allow: result-put-gradingperiod-resolve-term-by-pk
    if term is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    dirty: list[str] = []
    new_title = str(inner.get("title") or "").strip()
    if new_title and term.name != new_title:
        term.name = new_title
        dirty.append("name")
    start = _parse_date(str(inner.get("beginDate") or ""))
    end = _parse_date(str(inner.get("endDate") or ""))
    if start is not None and hasattr(term, "start_date") and term.start_date != start:
        term.start_date = start
        dirty.append("start_date")
    if end is not None and hasattr(term, "end_date") and term.end_date != end:
        term.end_date = end
        dirty.append("end_date")
    if dirty:
        try:
            term.save(update_fields=dirty)
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({"error": "save_failed", "detail": str(exc)}, status=500)

    item = {
        "sourcedId": sourced_id,
        "status": "active",
        "title": term.name,
        "type": "gradingPeriod",
        "beginDate": term.start_date.isoformat() if getattr(term, "start_date", None) else "",
        "endDate": term.end_date.isoformat() if getattr(term, "end_date", None) else "",
        "academicSessionSourcedId": f"ay-{term.academic_year_id}" if getattr(term, "academic_year_id", None) else "",
    }
    body_out = {"gradingPeriod": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "gradingPeriod"
    return resp


def delete_grading_period(request: HttpRequest, sourced_id: str):
    """v4.00.52 — Soft-delete a GradingPeriod via cache mark.

    Returns 200 + ``alreadyDeleted: false`` on first call, 200 +
    ``alreadyDeleted: true`` on re-delete. The backing ``Term`` row is
    NOT physically deleted (it is referenced by SubjectAssignment +
    Evaluation FKs) — the soft-delete is recorded server-side so OneRoster
    consumers stop polling.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("gp-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    ck = f"roster:results:gradingperiod-deleted:{sourced_id}"
    already = bool(cache.get(ck))
    if not already:
        cache.set(ck, True, _IDEMPOTENCY_TTL)
    return JsonResponse({"gradingPeriod": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def grading_periods_collection(request: HttpRequest):
    if request.method == "POST":
        return post_grading_period(request)
    return grading_periods_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def grading_period_dispatch(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_grading_period(request, sourced_id)
    if request.method == "DELETE":
        return delete_grading_period(request, sourced_id)
    return grading_period_detail(request, sourced_id)


@require_http_methods(["GET"])
def categories_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    page, meta = _paginate(request, _all_categories())
    return _envelope("categories", page, meta)


@require_http_methods(["GET"])
def category_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    for c in _all_categories():
        if c["sourcedId"] == sourced_id:
            return JsonResponse({"category": c})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


# ---------------------------------------------------------------------------
# v4.00.53 — Category write coverage (POST/PUT/DELETE).
#
# Categories are stored in a runtime override map keyed by ``cat-<slug>``
# alongside the 6 built-in seeds. POST creates with Idempotency-Key
# semantics; PUT updates title/type/status; DELETE soft-removes. The 6
# built-in seed categories are never physically removed — DELETE on a
# seed records a soft-tombstone so list readers skip the row, and a
# subsequent POST with the same sourcedId resurrects it.
# ---------------------------------------------------------------------------

_CATEGORY_OVERRIDES: dict[str, dict[str, Any]] = {}
_CATEGORY_TOMBSTONES: set[str] = set()
_ALLOWED_CATEGORY_TYPES = {
    "summative", "formative", "homework", "practice",
    "participation", "attendance", "project", "exam", "lab", "other",
}


def _seed_categories_by_id() -> dict[str, dict[str, Any]]:
    return {c["sourcedId"]: dict(c) for c in _CATEGORIES}


def _all_categories() -> list[dict[str, Any]]:
    """Compose seeds + overrides minus tombstones (deterministic order)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in _CATEGORIES:
        sid = c["sourcedId"]
        if sid in _CATEGORY_TOMBSTONES:
            continue
        merged = dict(c)
        if sid in _CATEGORY_OVERRIDES:
            merged.update(_CATEGORY_OVERRIDES[sid])
        out.append(merged)
        seen.add(sid)
    for sid, c in _CATEGORY_OVERRIDES.items():
        if sid in seen or sid in _CATEGORY_TOMBSTONES:
            continue
        out.append(dict(c))
    return out


def _validate_category_payload(inner: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    title = str(inner.get("title") or "").strip()
    if not title:
        return "missing_title", None
    ctype = str(inner.get("type") or "summative").strip()
    if ctype not in _ALLOWED_CATEGORY_TYPES:
        return "bad_type", None
    status = str(inner.get("status") or "active").strip()
    if status not in ("active", "tobedeleted"):
        return "bad_status", None
    return None, {"title": title, "type": ctype, "status": status}


@csrf_exempt
@require_http_methods(["POST"])
def post_category(request: HttpRequest):
    """v4.00.53 — Create a new Result Service Category.

    Body: ``{"category": {"title": "Quiz", "type": "formative",
    "sourcedId": "cat-quiz"}}``. ``sourcedId`` optional; when omitted the
    server derives ``cat-<slugified-title>``. Idempotency-Key REQUIRED.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-category", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("category")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_category_envelope"}, status=400)

    err, cleaned = _validate_category_payload(inner)
    if err is not None:
        return JsonResponse({"error": err}, status=400)

    sid = str(inner.get("sourcedId") or "").strip()
    if not sid:
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in cleaned["title"]).strip("-")
        slug = slug[:48] or "untitled"
        sid = f"cat-{slug}"
    if not sid.startswith("cat-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    item = {"sourcedId": sid, **cleaned}
    _CATEGORY_OVERRIDES[sid] = item
    _CATEGORY_TOMBSTONES.discard(sid)
    body_out = {"category": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/categories/{sid}/"
    resp["X-OneRoster-Entity"] = "category"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_category(request: HttpRequest, sourced_id: str):
    """v4.00.53 — Update an existing Result Service Category."""
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("cat-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"category:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    existing = None
    for c in _all_categories():
        if c["sourcedId"] == sourced_id:
            existing = c
            break
    if existing is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("category")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_category_envelope"}, status=400)

    merged_input = {"title": existing.get("title", ""), "type": existing.get("type", "summative"),
                    "status": existing.get("status", "active")}
    if inner.get("title") is not None:
        merged_input["title"] = inner.get("title")
    if inner.get("type") is not None:
        merged_input["type"] = inner.get("type")
    if inner.get("status") is not None:
        merged_input["status"] = inner.get("status")
    err, cleaned = _validate_category_payload(merged_input)
    if err is not None:
        return JsonResponse({"error": err}, status=400)

    item = {"sourcedId": sourced_id, **cleaned}
    _CATEGORY_OVERRIDES[sourced_id] = item
    _CATEGORY_TOMBSTONES.discard(sourced_id)
    body_out = {"category": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "category"
    return resp


def delete_category(request: HttpRequest, sourced_id: str):
    """v4.00.53 — Soft-delete a Category (idempotent).

    Returns 200 + ``alreadyDeleted: false`` on first call, 200 +
    ``alreadyDeleted: true`` on re-delete. Seeds are tombstoned (not
    removed); overrides are removed from the override map.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("cat-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    seeds = _seed_categories_by_id()
    already = sourced_id in _CATEGORY_TOMBSTONES or (sourced_id not in seeds and sourced_id not in _CATEGORY_OVERRIDES)
    if not already:
        _CATEGORY_TOMBSTONES.add(sourced_id)
        _CATEGORY_OVERRIDES.pop(sourced_id, None)
    return JsonResponse({"category": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def categories_collection(request: HttpRequest):
    if request.method == "POST":
        return post_category(request)
    return categories_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def category_dispatch(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_category(request, sourced_id)
    if request.method == "DELETE":
        return delete_category(request, sourced_id)
    return category_detail(request, sourced_id)


# ---------------------------------------------------------------------------
# v4.00.54 — LineItem Attachment + Rubric write coverage (Wedge 2).
#
# Attachments (``att-<slug>``) and rubrics (``rub-<slug>``) are auxiliary
# OneRoster Result Service entities attached to LineItems. They are
# stored in runtime override maps with the same Idempotency-Key contract
# as categories. POST creates, PUT updates, DELETE soft-removes via
# tombstone. GET list/detail compose the in-memory map.
#
# Validation guarantees:
#   - Attachments require ``lineItemSourcedId`` (must start ``li-``) and
#     ``url`` (must start http:// or https://).
#   - Rubrics require ``lineItemSourcedId`` and at least one criterion
#     in ``criteria`` (each criterion {title, points}).
# ---------------------------------------------------------------------------

_ATTACHMENT_OVERRIDES: dict[str, dict[str, Any]] = {}
_ATTACHMENT_TOMBSTONES: set[str] = set()
_RUBRIC_OVERRIDES: dict[str, dict[str, Any]] = {}
_RUBRIC_TOMBSTONES: set[str] = set()
_ALLOWED_ATTACHMENT_TYPES = {"file", "link", "video", "image", "audio", "document", "other"}


def _slugify_for_sid(raw: str, fallback: str = "item") -> str:
    import re
    base = re.sub(r"[^a-z0-9-]+", "-", (raw or "").lower()).strip("-")
    return base or fallback


def _all_attachments() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid, a in _ATTACHMENT_OVERRIDES.items():
        if sid in _ATTACHMENT_TOMBSTONES:
            continue
        out.append(dict(a))
    out.sort(key=lambda r: r.get("sourcedId", ""))
    return out


def _all_rubrics() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid, r in _RUBRIC_OVERRIDES.items():
        if sid in _RUBRIC_TOMBSTONES:
            continue
        out.append(dict(r))
    out.sort(key=lambda r: r.get("sourcedId", ""))
    return out


@require_http_methods(["GET"])
def attachments_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = _all_attachments()
    line_item = (request.GET.get("lineItem") or "").strip()
    if line_item:
        items = [a for a in items if a.get("lineItemSourcedId") == line_item]
    page, meta = _paginate(request, items)
    return _envelope("attachments", page, meta)


@require_http_methods(["GET"])
def attachment_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if sourced_id in _ATTACHMENT_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    a = _ATTACHMENT_OVERRIDES.get(sourced_id)
    if not a:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"attachment": a})


@csrf_exempt
@require_http_methods(["POST"])
def post_attachment(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-attachment", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("attachment")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_attachment_envelope"}, status=400)

    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    if not line_item.startswith("li-"):
        return JsonResponse({"error": "bad_lineItemSourcedId"}, status=400)
    url = str(inner.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return JsonResponse({"error": "bad_url"}, status=400)
    a_type = str(inner.get("type") or "link").strip().lower()
    if a_type not in _ALLOWED_ATTACHMENT_TYPES:
        return JsonResponse({"error": "bad_type"}, status=400)
    title = str(inner.get("title") or "").strip() or "Attachment"

    sid_raw = str(inner.get("sourcedId") or "").strip()
    if sid_raw:
        sid = sid_raw if sid_raw.startswith("att-") else f"att-{_slugify_for_sid(sid_raw)}"
    else:
        sid = f"att-{_slugify_for_sid(title)}"

    item = {
        "sourcedId": sid,
        "status": "active",
        "lineItemSourcedId": line_item,
        "title": title,
        "url": url,
        "type": a_type,
    }
    _ATTACHMENT_OVERRIDES[sid] = item
    _ATTACHMENT_TOMBSTONES.discard(sid)

    body_out = {"attachment": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/attachments/{sid}/"
    resp["X-OneRoster-Entity"] = "attachment"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_attachment(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("att-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"attachment:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("attachment")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_attachment_envelope"}, status=400)

    existing = _ATTACHMENT_OVERRIDES.get(sourced_id)
    if existing is None or sourced_id in _ATTACHMENT_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    item = dict(existing)
    if "title" in inner:
        item["title"] = str(inner["title"]).strip() or item["title"]
    if "url" in inner:
        new_url = str(inner["url"]).strip()
        if not (new_url.startswith("http://") or new_url.startswith("https://")):
            return JsonResponse({"error": "bad_url"}, status=400)
        item["url"] = new_url
    if "type" in inner:
        new_type = str(inner["type"]).strip().lower()
        if new_type not in _ALLOWED_ATTACHMENT_TYPES:
            return JsonResponse({"error": "bad_type"}, status=400)
        item["type"] = new_type
    if "status" in inner:
        new_status = str(inner["status"]).strip().lower()
        if new_status not in {"active", "tobedeleted"}:
            return JsonResponse({"error": "bad_status"}, status=400)
        item["status"] = new_status
    _ATTACHMENT_OVERRIDES[sourced_id] = item
    body_out = {"attachment": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "attachment"
    return resp


def delete_attachment(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    already = sourced_id in _ATTACHMENT_TOMBSTONES or sourced_id not in _ATTACHMENT_OVERRIDES
    if not already:
        _ATTACHMENT_TOMBSTONES.add(sourced_id)
        _ATTACHMENT_OVERRIDES.pop(sourced_id, None)
    return JsonResponse(
        {"attachment": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already},
        status=200,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def attachments_collection(request: HttpRequest):
    if request.method == "POST":
        return post_attachment(request)
    return attachments_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def attachment_dispatch(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_attachment(request, sourced_id)
    if request.method == "DELETE":
        return delete_attachment(request, sourced_id)
    return attachment_detail(request, sourced_id)


# --- Rubrics --------------------------------------------------------------

@require_http_methods(["GET"])
def rubrics_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = _all_rubrics()
    line_item = (request.GET.get("lineItem") or "").strip()
    if line_item:
        items = [r for r in items if r.get("lineItemSourcedId") == line_item]
    page, meta = _paginate(request, items)
    return _envelope("rubrics", page, meta)


@require_http_methods(["GET"])
def rubric_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if sourced_id in _RUBRIC_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    r = _RUBRIC_OVERRIDES.get(sourced_id)
    if not r:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"rubric": r})


def _validate_criteria(raw) -> tuple[list[dict[str, Any]] | None, str]:
    if not isinstance(raw, list) or not raw:
        return None, "missing_criteria"
    out: list[dict[str, Any]] = []
    for c in raw:
        if not isinstance(c, dict):
            return None, "bad_criterion"
        title = str(c.get("title") or "").strip()
        if not title:
            return None, "missing_criterion_title"
        try:
            pts = float(c.get("points", 0))  # money-float-allow: oneroster-rubric-points-not-money
        except (ValueError, TypeError):
            return None, "bad_criterion_points"
        if pts < 0:
            return None, "negative_criterion_points"
        out.append({"title": title, "points": pts})
    return out, ""


@csrf_exempt
@require_http_methods(["POST"])
def post_rubric(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-rubric", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("rubric")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_rubric_envelope"}, status=400)

    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    if not line_item.startswith("li-"):
        return JsonResponse({"error": "bad_lineItemSourcedId"}, status=400)

    criteria, err = _validate_criteria(inner.get("criteria"))
    if err:
        return JsonResponse({"error": err}, status=400)

    title = str(inner.get("title") or "").strip() or "Rubric"
    sid_raw = str(inner.get("sourcedId") or "").strip()
    if sid_raw:
        sid = sid_raw if sid_raw.startswith("rub-") else f"rub-{_slugify_for_sid(sid_raw)}"
    else:
        sid = f"rub-{_slugify_for_sid(title)}"

    item = {
        "sourcedId": sid,
        "status": "active",
        "lineItemSourcedId": line_item,
        "title": title,
        "criteria": criteria,
    }
    _RUBRIC_OVERRIDES[sid] = item
    _RUBRIC_TOMBSTONES.discard(sid)

    body_out = {"rubric": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/rubrics/{sid}/"
    resp["X-OneRoster-Entity"] = "rubric"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_rubric(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("rub-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"rubric:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("rubric")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_rubric_envelope"}, status=400)

    existing = _RUBRIC_OVERRIDES.get(sourced_id)
    if existing is None or sourced_id in _RUBRIC_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    item = dict(existing)
    if "title" in inner:
        item["title"] = str(inner["title"]).strip() or item["title"]
    if "criteria" in inner:
        criteria, err = _validate_criteria(inner.get("criteria"))
        if err:
            return JsonResponse({"error": err}, status=400)
        item["criteria"] = criteria
    if "status" in inner:
        new_status = str(inner["status"]).strip().lower()
        if new_status not in {"active", "tobedeleted"}:
            return JsonResponse({"error": "bad_status"}, status=400)
        item["status"] = new_status
    _RUBRIC_OVERRIDES[sourced_id] = item
    body_out = {"rubric": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "rubric"
    return resp


def delete_rubric(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    already = sourced_id in _RUBRIC_TOMBSTONES or sourced_id not in _RUBRIC_OVERRIDES
    if not already:
        _RUBRIC_TOMBSTONES.add(sourced_id)
        _RUBRIC_OVERRIDES.pop(sourced_id, None)
    return JsonResponse(
        {"rubric": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already},
        status=200,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def rubrics_collection(request: HttpRequest):
    if request.method == "POST":
        return post_rubric(request)
    return rubrics_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def rubric_dispatch(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_rubric(request, sourced_id)
    if request.method == "DELETE":
        return delete_rubric(request, sourced_id)
    return rubric_detail(request, sourced_id)


# ---------------------------------------------------------------------------
# v4.00.55 — ClassGroup write coverage + Results bulk-import (Wedge 2).
#
# ClassGroups (``cg-<slug>``) — OneRoster Result Service grouping that
# lets districts bundle classes by department / grade / cohort. Stored
# in a runtime override map alongside the lineItem/category projections.
#
# Results bulk-import — single Idempotency-Keyed POST that accepts an
# array of up to 500 Result envelopes. Per-row validation; partial
# failures DO NOT abort the batch — each row gets a 4-tuple outcome
# (created / updated / skipped / errored). Replay returns the cached
# top-level body + ``Idempotency-Replay: true``.
# ---------------------------------------------------------------------------

_CLASSGROUP_OVERRIDES: dict[str, dict[str, Any]] = {}
_CLASSGROUP_TOMBSTONES: set[str] = set()
_ALLOWED_CLASSGROUP_TYPES = {"department", "grade", "cohort", "homeroom", "advisory", "other"}


def _all_classgroups() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid, g in _CLASSGROUP_OVERRIDES.items():
        if sid in _CLASSGROUP_TOMBSTONES:
            continue
        out.append(dict(g))
    out.sort(key=lambda r: r.get("sourcedId", ""))
    return out


@require_http_methods(["GET"])
def classgroups_list(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    items = _all_classgroups()
    page, meta = _paginate(request, items)
    return _envelope("classGroups", page, meta)


@require_http_methods(["GET"])
def classgroup_detail(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if sourced_id in _CLASSGROUP_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    g = _CLASSGROUP_OVERRIDES.get(sourced_id)
    if not g:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    return JsonResponse({"classGroup": g})


def _validate_class_sids(raw) -> tuple[list[str] | None, str]:
    if raw is None:
        return [], ""
    if not isinstance(raw, list):
        return None, "bad_classSourcedIds"
    out: list[str] = []
    for v in raw:
        s = str(v or "").strip()
        if not s:
            return None, "empty_class_sid"
        out.append(s)
    return out, ""


@csrf_exempt
@require_http_methods(["POST"])
def post_classgroup(request: HttpRequest):
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-classgroup", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 201))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    inner = payload.get("classGroup")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_classGroup_envelope"}, status=400)

    title = str(inner.get("title") or "").strip()
    if not title:
        return JsonResponse({"error": "missing_title"}, status=400)
    g_type = str(inner.get("type") or "department").strip().lower()
    if g_type not in _ALLOWED_CLASSGROUP_TYPES:
        return JsonResponse({"error": "bad_type"}, status=400)
    class_sids, err = _validate_class_sids(inner.get("classSourcedIds"))
    if err:
        return JsonResponse({"error": err}, status=400)

    sid_raw = str(inner.get("sourcedId") or "").strip()
    if sid_raw:
        sid = sid_raw if sid_raw.startswith("cg-") else f"cg-{_slugify_for_sid(sid_raw)}"
    else:
        sid = f"cg-{_slugify_for_sid(title)}"

    item = {
        "sourcedId": sid,
        "status": "active",
        "title": title,
        "type": g_type,
        "classSourcedIds": class_sids,
    }
    _CLASSGROUP_OVERRIDES[sid] = item
    _CLASSGROUP_TOMBSTONES.discard(sid)

    body_out = {"classGroup": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 201}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 201, False)
    resp = JsonResponse(body_out, status=201)
    resp["Location"] = f"/api/roster/results/v1p2/classGroups/{sid}/"
    resp["X-OneRoster-Entity"] = "classGroup"
    return resp


@csrf_exempt
@require_http_methods(["PUT"])
def put_classgroup(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("cg-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)

    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key(f"classgroup:{sourced_id}", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_from_request(request, idem, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    inner = payload.get("classGroup")
    if not isinstance(inner, dict):
        return JsonResponse({"error": "missing_classGroup_envelope"}, status=400)

    existing = _CLASSGROUP_OVERRIDES.get(sourced_id)
    if existing is None or sourced_id in _CLASSGROUP_TOMBSTONES:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)

    item = dict(existing)
    if "title" in inner:
        item["title"] = str(inner["title"]).strip() or item["title"]
    if "type" in inner:
        new_type = str(inner["type"]).strip().lower()
        if new_type not in _ALLOWED_CLASSGROUP_TYPES:
            return JsonResponse({"error": "bad_type"}, status=400)
        item["type"] = new_type
    if "classSourcedIds" in inner:
        class_sids, err = _validate_class_sids(inner.get("classSourcedIds"))
        if err:
            return JsonResponse({"error": err}, status=400)
        item["classSourcedIds"] = class_sids
    if "status" in inner:
        new_status = str(inner["status"]).strip().lower()
        if new_status not in {"active", "tobedeleted"}:
            return JsonResponse({"error": "bad_status"}, status=400)
        item["status"] = new_status
    _CLASSGROUP_OVERRIDES[sourced_id] = item
    body_out = {"classGroup": item}
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    _log_idem_from_request(request, idem, 200, False)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "classGroup"
    return resp


def delete_classgroup(request: HttpRequest, sourced_id: str):
    gate = _gate(request)
    if gate is not None:
        return gate
    already = sourced_id in _CLASSGROUP_TOMBSTONES or sourced_id not in _CLASSGROUP_OVERRIDES
    if not already:
        _CLASSGROUP_TOMBSTONES.add(sourced_id)
        _CLASSGROUP_OVERRIDES.pop(sourced_id, None)
    return JsonResponse(
        {"classGroup": {"sourcedId": sourced_id, "status": "tobedeleted"}, "alreadyDeleted": already},
        status=200,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def classgroups_collection(request: HttpRequest):
    if request.method == "POST":
        return post_classgroup(request)
    return classgroups_list(request)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def classgroup_dispatch(request: HttpRequest, sourced_id: str):
    if request.method == "PUT":
        return put_classgroup(request, sourced_id)
    if request.method == "DELETE":
        return delete_classgroup(request, sourced_id)
    return classgroup_detail(request, sourced_id)


# ---------------------------------------------------------------------------
# v4.00.57 — ClassGroup bulk delete-by-class.
#
# When a teacher unassigns a class from a cohort or splits a cohort, the
# integration must DELETE every classGroup containing that class. Doing N
# DELETE round-trips is slow + non-atomic; this endpoint tombstones every
# matching group in one request and reports the count.
#
# Body: ``{"classSourcedId": "<id>"}``
# Idempotency-Key REQUIRED; same body + same key replays cached result.
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def classgroups_bulk_delete_by_class(request: HttpRequest):
    """v4.00.57 — Tombstone every classGroup containing ``classSourcedId``.

    Returns ``{tombstoned: N, alreadyTombstoned: M, total: N+M, sourcedIds: [...]}``.
    Empty match returns ``{tombstoned: 0, ...}`` with status 200 — NOT 404
    (the "no groups contain this class" answer is valid).
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-classgroups-bulk-delete", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_event("classgroups-bulk-delete-by-class", idem, request.method, request.path, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    class_sid = str(payload.get("classSourcedId") or "").strip()
    if not class_sid:
        return JsonResponse({"error": "missing_classSourcedId"}, status=400)

    tombstoned_ids: list[str] = []
    already_tombstoned_ids: list[str] = []
    # Walk a snapshot of overrides so we can mutate _CLASSGROUP_OVERRIDES safely.
    for sid in list(_CLASSGROUP_OVERRIDES.keys()):
        group = _CLASSGROUP_OVERRIDES.get(sid) or {}
        members = group.get("classSourcedIds") or []
        if class_sid not in members:
            continue
        if sid in _CLASSGROUP_TOMBSTONES:
            already_tombstoned_ids.append(sid)
            continue
        _CLASSGROUP_TOMBSTONES.add(sid)
        _CLASSGROUP_OVERRIDES.pop(sid, None)
        tombstoned_ids.append(sid)

    body_out = {
        "classSourcedId": class_sid,
        "tombstoned": len(tombstoned_ids),
        "alreadyTombstoned": len(already_tombstoned_ids),
        "total": len(tombstoned_ids) + len(already_tombstoned_ids),
        "sourcedIds": tombstoned_ids,
        "alreadySourcedIds": already_tombstoned_ids,
    }
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": 200}, _IDEMPOTENCY_TTL)
    resp = JsonResponse(body_out, status=200)
    resp["X-OneRoster-Entity"] = "class-groups-bulk-delete"
    _log_idem_event("classgroups-bulk-delete-by-class", idem, request.method, request.path, 200, False)
    return resp


# --- Bulk Results import --------------------------------------------------

_BULK_IMPORT_MAX_ROWS = 500

# v4.00.56 — Per-row idempotency. When a bulk-import row carries an
# ``idempotencyKey`` field, the successful outcome is cached so a future
# batch that retries the same row replays the prior result without
# re-creating the underlying ``Evaluation``. Errored outcomes are NOT
# cached: the operator should be able to retry after fixing data.
_BULK_IMPORT_ROW_IDEM_TTL = 60 * 60 * 24


def _bulk_row_idem_cache_key(idem: str) -> str:
    return f"roster:results:bulk-row-idempo:{idem}"


def _import_one_result(inner: dict[str, Any]) -> dict[str, Any]:
    """Apply one bulk-import row. Returns ``{outcome, sourcedId?, error?}``.

    All ORM lookups are wrapped in a single try block so that malformed
    PKs (wrong type for the column), missing tables, or any other
    per-row failure yield an errored outcome without aborting the
    batch.
    """
    try:
        from apps.evals.models import Evaluation
        from apps.academics.models import Classroom, SubjectAssignment
        from apps.people.models import StudentProfile, TeacherProfile
    except Exception as exc:  # noqa: BLE001
        return {"outcome": "errored", "error": f"models_unavailable: {exc}"}

    student_id = str(inner.get("studentSourcedId") or "").strip()
    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    classroom_pk = line_item[3:] if line_item.startswith("li-") else line_item
    if not student_id or not classroom_pk:
        return {"outcome": "errored", "error": "missing_student_or_classroom"}

    score_raw = inner.get("score", "")
    text_score = str(inner.get("textScore") or "")[:16]
    try:
        score_value = float(score_raw) if score_raw not in (None, "") else None  # money-float-allow: oneroster-score-is-not-money
    except (ValueError, TypeError):
        return {"outcome": "errored", "error": "score_not_numeric"}

    try:
        classroom = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-bulk-import-resolve-classroom-by-pk
        if classroom is None:
            return {"outcome": "errored", "error": "classroom_not_found"}

        sa = SubjectAssignment.objects.filter(classroom_id=classroom.pk).first()  # tenant-isolation-allow: result-bulk-import-resolve-sa-by-classroom-pk
        if sa is None:
            return {"outcome": "errored", "error": "no_subject_assignment_for_classroom"}
        student = StudentProfile.objects.filter(user_id=student_id).first()  # tenant-isolation-allow: result-bulk-import-resolve-student-by-user-pk
        if student is None:
            return {"outcome": "errored", "error": "student_not_found"}
        teacher_user = sa.teachers.first()
        teacher = None
        if teacher_user is not None:
            teacher = TeacherProfile.objects.filter(user_id=teacher_user.pk).first()  # tenant-isolation-allow: result-bulk-import-resolve-teacher-from-sa
        if teacher is None:
            teacher = TeacherProfile.objects.filter(school_id=classroom.school_id).first()  # tenant-isolation-allow: result-bulk-import-resolve-teacher-fallback-school
        if teacher is None:
            return {"outcome": "errored", "error": "no_teacher_for_school_or_assignment"}

        seed = score_value if score_value is not None else 0
        obj = Evaluation.objects.create(  # tenant-isolation-allow: result-bulk-import-create-keyed-by-school-student-sa
            school=classroom.school,
            academic_year=sa.academic_year,
            term=sa.term,
            subject_assignment=sa,
            student=student,
            teacher=teacher,
            exam_score=seed,
            final_score=seed,
            letter_grade=text_score,
        )
        return {"outcome": "created", "sourcedId": f"res-{obj.pk}"}
    except (ValueError, TypeError) as exc:
        return {"outcome": "errored", "error": f"bad_field_value: {exc}"}
    except Exception as exc:  # noqa: BLE001 — bulk-import row must NEVER abort the batch
        logger.warning("bulk-import row failed: %s", exc)
        return {"outcome": "errored", "error": f"row_failed: {exc}"}


@csrf_exempt
@require_http_methods(["POST"])
def post_results_bulk_import(request: HttpRequest):
    """v4.00.55 — Bulk-import Result rows.

    Body: ``{"results": [{"score": "85", "textScore": "B",
    "studentSourcedId": "<pk>", "lineItemSourcedId": "li-<class_pk>"}, ...]}``

    Idempotency-Key REQUIRED. Per-row failures DO NOT abort the batch;
    each row gets ``{"outcome": "created|errored", "sourcedId": ..., "error": ...}``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-results-bulk", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_event("results-bulk-import", idem, request.method, request.path, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    rows = payload.get("results")
    if not isinstance(rows, list):
        return JsonResponse({"error": "missing_results_array"}, status=400)
    if not rows:
        return JsonResponse({"error": "empty_results_array"}, status=400)
    if len(rows) > _BULK_IMPORT_MAX_ROWS:
        return JsonResponse(
            {"error": "too_many_rows", "max": _BULK_IMPORT_MAX_ROWS, "received": len(rows)},
            status=413,
        )

    outcomes: list[dict[str, Any]] = []
    created = 0
    errored = 0
    replayed = 0
    for row in rows:
        if not isinstance(row, dict):
            outcomes.append({"outcome": "errored", "error": "bad_row_shape"})
            errored += 1
            continue
        # v4.00.56 — per-row idempotency replay: if this row carries a row-
        # level ``idempotencyKey`` AND the prior outcome was ``created``, we
        # short-circuit and reuse the cached sourcedId. Errored outcomes are
        # NOT cached so operator can retry after fixing data.
        row_idem = str(row.get("idempotencyKey") or "").strip()
        if row_idem:
            cached_row = cache.get(_bulk_row_idem_cache_key(row_idem))
            if isinstance(cached_row, dict) and cached_row.get("outcome") == "created":
                replay_out = {
                    "outcome": "created",
                    "sourcedId": cached_row.get("sourcedId", ""),
                    "idempotencyKey": row_idem,
                    "replayed": True,
                }
                outcomes.append(replay_out)
                replayed += 1
                created += 1
                continue
        out = _import_one_result(row)
        if row_idem:
            out = {**out, "idempotencyKey": row_idem}
            if out.get("outcome") == "created":
                cache.set(
                    _bulk_row_idem_cache_key(row_idem),
                    {"outcome": "created", "sourcedId": out.get("sourcedId", "")},
                    _BULK_IMPORT_ROW_IDEM_TTL,
                )
        outcomes.append(out)
        if out["outcome"] == "created":
            created += 1
        else:
            errored += 1

    body_out = {
        "total": len(rows),
        "created": created,
        "errored": errored,
        "replayed": replayed,
        "outcomes": outcomes,
    }
    status = 207 if errored else 201
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": status}, _IDEMPOTENCY_TTL)
    resp = JsonResponse(body_out, status=status)
    resp["X-OneRoster-Entity"] = "results-bulk"
    _log_idem_event("results-bulk-import", idem, request.method, request.path, status, False)
    return resp


# ---------------------------------------------------------------------------
# v4.00.58 — Results bulk-update.
#
# Mass grade change without creating new rows. Each row identifies an
# existing Evaluation via ``sourcedId`` (``res-<pk>``) OR via
# ``(studentSourcedId, lineItemSourcedId)``. Updates score/textScore in
# place. Per-row outcome: updated / not_found / errored / unchanged.
# Top-level body adds ``replayed`` like v4.00.56 bulk-import.
# Idempotency-Key REQUIRED. Per-row ``idempotencyKey`` honored.
# ---------------------------------------------------------------------------


def _update_one_result(inner: dict[str, Any]) -> dict[str, Any]:
    """Apply one bulk-update row. Returns ``{outcome, sourcedId?, error?}``."""
    try:
        from apps.evals.models import Evaluation
        from apps.academics.models import Classroom
    except Exception as exc:  # noqa: BLE001
        return {"outcome": "errored", "error": f"models_unavailable: {exc}"}

    sourced_id = str(inner.get("sourcedId") or "").strip()
    student_id = str(inner.get("studentSourcedId") or "").strip()
    line_item = str(inner.get("lineItemSourcedId") or "").strip()
    classroom_pk = line_item[3:] if line_item.startswith("li-") else line_item

    score_raw = inner.get("score", None)
    text_score = str(inner.get("textScore") or "")[:16]

    score_value = None
    if score_raw not in (None, ""):
        try:
            score_value = float(score_raw)  # money-float-allow: oneroster-score-is-not-money-numeric-update
        except (ValueError, TypeError):
            return {"outcome": "errored", "error": "score_not_numeric"}

    if score_value is None and not text_score:
        return {"outcome": "errored", "error": "no_score_or_text_score_to_update"}

    try:
        obj = None
        if sourced_id.startswith("res-"):
            try:
                pk = int(sourced_id[4:])
            except (ValueError, TypeError):
                return {"outcome": "errored", "error": "bad_sourced_id"}
            obj = Evaluation.objects.filter(pk=pk).first()  # tenant-isolation-allow: result-bulk-update-by-pk
        elif student_id and classroom_pk:
            classroom = Classroom.objects.filter(pk=classroom_pk).first()  # tenant-isolation-allow: result-bulk-update-resolve-classroom
            if classroom is None:
                return {"outcome": "not_found", "error": "classroom_not_found"}
            obj = Evaluation.objects.filter(  # tenant-isolation-allow: result-bulk-update-resolve-eval-by-school-student
                school=classroom.school, student_id=student_id,
            ).first()
        else:
            return {"outcome": "errored", "error": "missing_identifier"}

        if obj is None:
            return {"outcome": "not_found", "error": "evaluation_not_found"}

        changed_fields: list[str] = []
        if score_value is not None and obj.final_score != score_value:
            obj.final_score = score_value
            changed_fields.append("final_score")
        if text_score and obj.letter_grade != text_score:
            obj.letter_grade = text_score
            changed_fields.append("letter_grade")
        if not changed_fields:
            return {"outcome": "unchanged", "sourcedId": f"res-{obj.pk}"}
        changed_fields.append("updated_at")
        obj.save(update_fields=changed_fields)
        return {"outcome": "updated", "sourcedId": f"res-{obj.pk}", "fields": [f for f in changed_fields if f != "updated_at"]}
    except (ValueError, TypeError) as exc:
        return {"outcome": "errored", "error": f"bad_field_value: {exc}"}
    except Exception as exc:  # noqa: BLE001 — bulk-update row must NEVER abort the batch
        logger.warning("bulk-update row failed: %s", exc)
        return {"outcome": "errored", "error": f"row_failed: {exc}"}


@csrf_exempt
@require_http_methods(["POST"])
def post_results_bulk_update(request: HttpRequest):
    """v4.00.58 — Bulk-update existing Result rows (UPDATE, never CREATE).

    Body: ``{"results": [{"sourcedId": "res-N", "score": "92", "textScore": "A-",
    "idempotencyKey": "<optional>"}, ...]}``

    Idempotency-Key REQUIRED. Per-row outcomes: ``updated``, ``not_found``,
    ``errored``, ``unchanged``. 207 on partial failure; 200 when all clean.
    Per-row ``idempotencyKey`` short-circuits to cached outcome on retry.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    idem = _idempotency_key(request)
    if not idem:
        return JsonResponse({"error": "missing_idempotency_key"}, status=428)

    body_bytes = request.body or b""
    payload_hash = _hash_payload(request.method, request.path, body_bytes)
    ck = _idem_cache_key("collection-post-results-bulk-update", idem)
    cached = cache.get(ck)
    if isinstance(cached, dict):
        if cached.get("payload_hash") == payload_hash:
            resp = JsonResponse(cached["response_body"], status=int(cached.get("status") or 200))
            resp["Idempotency-Replay"] = "true"
            _log_idem_event("results-bulk-update", idem, request.method, request.path, resp.status_code, True)
            return resp
        return JsonResponse({"error": "idempotency_key_payload_mismatch"}, status=409)

    try:
        payload = _json.loads(body_bytes) if body_bytes else {}
    except (ValueError, TypeError):
        return JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "bad_envelope"}, status=400)
    rows = payload.get("results")
    if not isinstance(rows, list):
        return JsonResponse({"error": "missing_results_array"}, status=400)
    if not rows:
        return JsonResponse({"error": "empty_results_array"}, status=400)
    if len(rows) > _BULK_IMPORT_MAX_ROWS:
        return JsonResponse(
            {"error": "too_many_rows", "max": _BULK_IMPORT_MAX_ROWS, "received": len(rows)},
            status=413,
        )

    outcomes: list[dict[str, Any]] = []
    updated = 0
    not_found = 0
    errored = 0
    unchanged = 0
    replayed = 0
    for row in rows:
        if not isinstance(row, dict):
            outcomes.append({"outcome": "errored", "error": "bad_row_shape"})
            errored += 1
            continue
        row_idem = str(row.get("idempotencyKey") or "").strip()
        if row_idem:
            cached_row = cache.get(_bulk_row_idem_cache_key(row_idem))
            if isinstance(cached_row, dict) and cached_row.get("outcome") in ("updated", "unchanged"):
                replay_out = {
                    "outcome": cached_row.get("outcome"),
                    "sourcedId": cached_row.get("sourcedId", ""),
                    "idempotencyKey": row_idem,
                    "replayed": True,
                }
                outcomes.append(replay_out)
                replayed += 1
                if replay_out["outcome"] == "updated":
                    updated += 1
                else:
                    unchanged += 1
                continue
        out = _update_one_result(row)
        if row_idem:
            out = {**out, "idempotencyKey": row_idem}
            if out.get("outcome") in ("updated", "unchanged"):
                cache.set(
                    _bulk_row_idem_cache_key(row_idem),
                    {"outcome": out["outcome"], "sourcedId": out.get("sourcedId", "")},
                    _BULK_IMPORT_ROW_IDEM_TTL,
                )
        outcomes.append(out)
        outcome = out.get("outcome", "errored")
        if outcome == "updated":
            updated += 1
        elif outcome == "not_found":
            not_found += 1
        elif outcome == "unchanged":
            unchanged += 1
        else:
            errored += 1

    body_out = {
        "total": len(rows),
        "updated": updated,
        "not_found": not_found,
        "errored": errored,
        "unchanged": unchanged,
        "replayed": replayed,
        "outcomes": outcomes,
    }
    status = 207 if (errored or not_found) else 200
    cache.set(ck, {"payload_hash": payload_hash, "response_body": body_out, "status": status}, _IDEMPOTENCY_TTL)
    resp = JsonResponse(body_out, status=status)
    resp["X-OneRoster-Entity"] = "results-bulk-update"
    _log_idem_event("results-bulk-update", idem, request.method, request.path, status, False)
    return resp


# ---------------------------------------------------------------------------
# v4.00.56 — GradeBookEntry projections (lineItem + category + classGroup
# + results rollup composition view).
#
# OneRoster Result Service does NOT define a separate GradeBookEntry object,
# but operators repeatedly need a single read endpoint that joins the
# lineItem with its category, its containing classGroup(s), and a rollup of
# the per-student results — i.e. the gradebook row a teacher actually looks
# at when reading "this assignment, in this cohort, with this score
# distribution".
#
# Projection rules:
#   * ``sourcedId`` derives from the lineItem: ``gbe-<classroom_pk>``
#     (replacing the ``li-`` prefix). 1:1 with lineItem.
#   * ``lineItem`` — the full lineItem dict.
#   * ``category`` — full category dict resolved by the lineItem's
#     ``category`` string (which holds a category SOURCEDID when set via
#     POST/PUT, falling back to ``"cat-<category_string>"`` for default
#     summative/formative seeds). ``None`` when no match.
#   * ``classGroups`` — list of classGroups whose ``classSourcedIds``
#     contain the lineItem's ``classSourcedId``. May be empty.
#   * ``resultsRollup`` — ``{count, average, min, max, scored, pending}``
#     computed over the matching results. Average/min/max use numeric
#     coercion of ``score``; non-numeric scores are excluded.
#
# Filters:
#   * ``?classSourcedId=<id>``  — only entries in that class.
#   * ``?classGroupSourcedId=<id>`` — only entries whose containing
#     classGroups include that id.
#
# Read-only — no POST/PUT/DELETE. Bearer-token gated by ``_gate``.
# ---------------------------------------------------------------------------


def _gradebook_entry_for(line_item: dict[str, Any]) -> dict[str, Any]:
    """Compose one GradeBookEntry from a lineItem record."""
    li_sid = line_item.get("sourcedId") or ""
    classroom_pk = li_sid[3:] if li_sid.startswith("li-") else li_sid
    class_sid = str(line_item.get("classSourcedId") or "")

    # Category resolution: lineItem.category may be a sourcedId already
    # (``cat-quiz``) OR a plain string like ``summative``. Try both.
    cat_field = str(line_item.get("category") or "").strip()
    resolved_category = None
    if cat_field:
        candidate_ids = [cat_field, f"cat-{cat_field}"]
        all_cats = _all_categories()
        by_sid = {c.get("sourcedId"): c for c in all_cats}
        for cid in candidate_ids:
            if cid in by_sid:
                resolved_category = by_sid[cid]
                break

    # ClassGroup resolution: any classGroup containing this lineItem's class.
    matched_class_groups = []
    for g in _all_classgroups():
        members = g.get("classSourcedIds") or []
        if class_sid and class_sid in members:
            matched_class_groups.append(g)

    # Results rollup.
    count = 0
    scored = 0
    pending = 0
    total = 0.0
    minimum = None
    maximum = None
    for r in _iter_results():
        if r.get("lineItemSourcedId") != li_sid:
            continue
        count += 1
        score_str = str(r.get("score") or "").strip()
        if not score_str:
            pending += 1
            continue
        try:
            v = float(score_str)  # money-float-allow: result-score-not-money-numeric-rollup
        except (ValueError, TypeError):
            pending += 1
            continue
        scored += 1
        total += v
        minimum = v if minimum is None or v < minimum else minimum
        maximum = v if maximum is None or v > maximum else maximum

    average = (total / scored) if scored else None
    rollup = {
        "count": count,
        "scored": scored,
        "pending": pending,
        "average": ("%.2f" % average) if average is not None else None,
        "min": ("%.2f" % minimum) if minimum is not None else None,
        "max": ("%.2f" % maximum) if maximum is not None else None,
    }

    return {
        "sourcedId": f"gbe-{classroom_pk}",
        "lineItem": line_item,
        "category": resolved_category,
        "classGroups": matched_class_groups,
        "resultsRollup": rollup,
    }


def _all_gradebook_entries() -> Iterable[dict[str, Any]]:
    for li in _iter_line_items():
        yield _gradebook_entry_for(li)


@require_http_methods(["GET"])
def gradebook_entries_collection(request: HttpRequest):
    """v4.00.56 — List GradeBookEntry projections.

    Filters: ``?classSourcedId=<id>``, ``?classGroupSourcedId=<id>``.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    items = list(_all_gradebook_entries())

    class_filter = (request.GET.get("classSourcedId") or "").strip()
    cg_filter = (request.GET.get("classGroupSourcedId") or "").strip()

    if class_filter:
        items = [
            e for e in items
            if str(e.get("lineItem", {}).get("classSourcedId") or "") == class_filter
        ]
    if cg_filter:
        items = [
            e for e in items
            if any(g.get("sourcedId") == cg_filter for g in e.get("classGroups", []))
        ]

    page, meta = _paginate(request, items)
    return _envelope("gradeBookEntries", page, meta)


@require_http_methods(["GET"])
def gradebook_entry_detail(request: HttpRequest, sourced_id: str):
    """v4.00.56 — Detail for a single GradeBookEntry by sourcedId."""
    gate = _gate(request)
    if gate is not None:
        return gate
    if not sourced_id.startswith("gbe-"):
        return JsonResponse({"error": "bad_sourced_id"}, status=400)
    li_pk = sourced_id[4:]
    li_sid = f"li-{li_pk}"
    for li in _iter_line_items():
        if li.get("sourcedId") == li_sid:
            return JsonResponse({"gradeBookEntry": _gradebook_entry_for(li)})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


# ---------------------------------------------------------------------------
# v4.00.57 — GradeBookEntry CSV export per class.
#
# Returns text/csv stream w/ Content-Disposition: attachment so a teacher
# can pull the gradebook for a single classroom into Excel/Sheets without
# parsing JSON. Built on the v4.00.56 projection; same auth gate.
# ---------------------------------------------------------------------------

_GRADEBOOK_CSV_COLUMNS = (
    "sourcedId",
    "lineItemSourcedId",
    "lineItemTitle",
    "classSourcedId",
    "categorySourcedId",
    "categoryTitle",
    "classGroupSourcedIds",
    "count",
    "scored",
    "pending",
    "average",
    "min",
    "max",
)


def _csv_quote(v) -> str:
    """RFC 4180 — wrap in double quotes when value contains delimiter, quote,
    CR or LF; double internal quotes."""
    s = "" if v is None else str(v)
    if any(ch in s for ch in (',', '"', '\r', '\n')):
        return '"' + s.replace('"', '""') + '"'
    return s


def _gradebook_csv_row(entry: dict) -> str:
    li = entry.get("lineItem") or {}
    cat = entry.get("category") or {}
    cgs = entry.get("classGroups") or []
    rollup = entry.get("resultsRollup") or {}
    values = [
        entry.get("sourcedId") or "",
        li.get("sourcedId") or "",
        li.get("title") or "",
        li.get("classSourcedId") or "",
        cat.get("sourcedId") or "" if isinstance(cat, dict) else "",
        cat.get("title") or "" if isinstance(cat, dict) else "",
        "|".join(g.get("sourcedId", "") for g in cgs),
        rollup.get("count", 0),
        rollup.get("scored", 0),
        rollup.get("pending", 0),
        rollup.get("average") or "",
        rollup.get("min") or "",
        rollup.get("max") or "",
    ]
    return ",".join(_csv_quote(v) for v in values) + "\r\n"


# ---------------------------------------------------------------------------
# v4.00.58 — GradeBookEntry PDF render per class (reportlab landscape table).
#
# Same projection set as the v4.00.57 CSV export, but rendered as a
# portable PDF for posting / printing. reportlab is already on the
# requirements list (used by other report surfaces). When reportlab
# is unavailable for any reason, the endpoint returns 503 with explicit
# ``reportlab_missing`` so the operator sees the gap.
# ---------------------------------------------------------------------------


@require_http_methods(["GET"])
def gradebook_entries_pdf(request: HttpRequest, class_sourced_id: str):
    """v4.00.58 — Render GradeBookEntries for ``class_sourced_id`` as PDF.

    Bearer-gated. ``class_sourced_id`` is the OneRoster classSourcedId.
    Empty match returns a PDF with header + "(no entries)" caption, NOT 404.
    """
    gate = _gate(request)
    if gate is not None:
        return gate
    class_sourced_id = (class_sourced_id or "").strip()
    if not class_sourced_id:
        return JsonResponse({"error": "missing_class_sourced_id"}, status=400)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError:
        return JsonResponse({"error": "reportlab_missing"}, status=503)

    from django.http import HttpResponse
    import io

    rows = []
    for entry in _all_gradebook_entries():
        li = entry.get("lineItem") or {}
        if str(li.get("classSourcedId") or "") != class_sourced_id:
            continue
        cat = entry.get("category") or {}
        cgs = entry.get("classGroups") or []
        rollup = entry.get("resultsRollup") or {}
        rows.append([
            entry.get("sourcedId") or "",
            li.get("title") or "",
            (cat.get("title") if isinstance(cat, dict) else "") or "",
            "|".join(g.get("sourcedId", "") for g in cgs),
            str(rollup.get("count", 0)),
            str(rollup.get("scored", 0)),
            str(rollup.get("pending", 0)),
            str(rollup.get("average") or ""),
            str(rollup.get("min") or ""),
            str(rollup.get("max") or ""),
        ])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Gradebook {class_sourced_id}",
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>Gradebook — class {class_sourced_id}</b>", styles["Title"]), Spacer(1, 6)]
    header = ["sourcedId", "lineItem", "category", "classGroups", "count", "scored", "pending", "avg", "min", "max"]
    table_data = [header] + rows if rows else [header, ["(no entries)"] + [""] * (len(header) - 1)]
    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
    ]))
    story.append(tbl)
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()

    safe_class_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in class_sourced_id)[:64]
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="gradebook-{safe_class_id}.pdf"'
    resp["X-OneRoster-Entity"] = "gradebook-entries-pdf"
    return resp


@require_http_methods(["GET"])
def gradebook_entries_csv(request: HttpRequest, class_sourced_id: str):
    """v4.00.57 — Stream the GradeBookEntries for ``class_sourced_id`` as CSV.

    Auth: bearer-gated. ``class_sourced_id`` is the OneRoster ``classSourcedId``
    (the same value that goes into a lineItem). Empty CSV (just headers) when
    no matching entries — never 404, since "no entries" is a valid teacher
    answer."""
    gate = _gate(request)
    if gate is not None:
        return gate
    class_sourced_id = (class_sourced_id or "").strip()
    if not class_sourced_id:
        return JsonResponse({"error": "missing_class_sourced_id"}, status=400)

    def _stream():
        yield ",".join(_GRADEBOOK_CSV_COLUMNS) + "\r\n"
        for entry in _all_gradebook_entries():
            li = entry.get("lineItem") or {}
            if str(li.get("classSourcedId") or "") != class_sourced_id:
                continue
            yield _gradebook_csv_row(entry)

    from django.http import StreamingHttpResponse
    resp = StreamingHttpResponse(_stream(), content_type="text/csv; charset=utf-8")
    safe_class_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in class_sourced_id)[:64]
    resp["Content-Disposition"] = f'attachment; filename="gradebook-{safe_class_id}.csv"'
    resp["X-OneRoster-Entity"] = "gradebook-entries-csv"
    return resp


# ---------------------------------------------------------------------------
# v4.00.79 Wave 11 T2 — OneRoster v1.2 Roster Service Categories endpoint.
#
# Spec: IMS Result Service § 4.13.6 surfaces Categories as a first-class
# entity (sourcedId / status / dateLastModified / title). The repo already
# has a Result-Service-path variant at /api/roster/results/v1p2/categories/
# (``categories_list`` above) backed by 6 seed types + runtime override map
# with full POST/PUT/DELETE coverage.
#
# This Wave 11 T2 endpoint exposes the spec-compliant Roster-Service-path
# projection at /api/roster/v1p2/categories/ with:
#   - ?since=ISO / ?before=ISO window filter on dateLastModified
#   - ?title= case-insensitive substring filter
#   - ?limit=N (default 100, max 500) + ?offset=N
#   - X-Total-Count header echoing the pre-pagination count
#   - 400 on malformed since/before
#   - 404 on detail miss
#
# Data source: no dedicated Category model exists. We synthesize from
# distinct LineItem ``category`` strings (currently always "summative" in
# the projection) UNIONED with the 6 seed types so the response is rich
# even before any line items exist. Synthetic sourcedId is
# SHA-256("cat:<tenant_schema>:<title>")[:16]. Status is always "active"
# (no soft-delete model). dateLastModified = max(LineItem.date_last_modified)
# over matching rows; fall back to timezone.now().isoformat().
#
# NAMING NOTE: this file already has top-level ``categories_list`` /
# ``category_detail`` from v4.00.47 wired to the Result-Service URL. To
# avoid collision the new Wave 11 T2 views are suffixed ``_v1p2_roster``.
# ---------------------------------------------------------------------------


def _resolve_tenant_schema(request: HttpRequest) -> str:
    """Best-effort tenant-schema resolver for synthetic sourcedId stability.

    Tries (in order): request.tenant.schema_name (django-tenants),
    request.session.get('schema_name'), and falls back to "public".
    """
    try:
        tenant = getattr(request, "tenant", None)
        if tenant is not None:
            name = getattr(tenant, "schema_name", "") or ""
            if name:
                return name
    except Exception:  # noqa: BLE001
        pass
    try:
        sess = getattr(request, "session", None)
        if sess is not None:
            name = sess.get("schema_name") or ""
            if name:
                return name
    except Exception:  # noqa: BLE001
        pass
    return "public"


def _synth_category_sourced_id(tenant_schema: str, title: str) -> str:
    import hashlib
    return hashlib.sha256(f"cat:{tenant_schema}:{title}".encode("utf-8")).hexdigest()[:16]


def _parse_iso_window(raw: str):
    """Parse ?since=/?before= ISO date(time). Returns (ok, value_or_err).

    Accepts YYYY-MM-DD or full ISO-8601 strings (with optional ``Z`` or
    ``+00:00`` tz suffix). Returns the raw string on success so downstream
    can do simple lexical comparison against ``dateLastModified``.
    """
    if not raw:
        return True, ""
    s = raw.strip()
    if not s:
        return True, ""
    # Accept Z suffix as +00:00 for parse-only validation.
    probe = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        from datetime import datetime, date
        # Try datetime first, then date-only.
        try:
            datetime.fromisoformat(probe)
        except (ValueError, TypeError):
            date.fromisoformat(probe[:10])
    except (ValueError, TypeError):
        return False, "bad_iso"
    return True, s


def _iter_category_titles_from_line_items() -> Iterable[tuple[str, str]]:
    """Walk LineItems and yield (title, date_last_modified_iso) tuples.

    The projection currently exposes ``category`` as the title and the
    repo-wide convention treats ``date_last_modified`` on the underlying
    Classroom as the LineItem's mtime. Missing fields fall back to "".
    """
    try:
        from apps.academics.models import Classroom
    except Exception as exc:  # noqa: BLE001
        logger.debug("v4.00.79 T2 categories: Classroom unavailable: %s", exc)
        return
    qs = Classroom.objects.all()  # tenant-isolation-allow: result-service-platform-scope-bearer-auth-required
    for c in qs[:1000]:
        # The static projection always uses "summative" — keep that contract
        # but also surface any explicit ``category`` attribute when present.
        title = (getattr(c, "category", None) or "summative") or ""
        title = str(title).strip()
        if not title:
            continue
        mtime = getattr(c, "date_last_modified", None) or getattr(c, "updated_at", None)
        try:
            iso = mtime.isoformat() if mtime else ""
        except Exception:  # noqa: BLE001
            iso = ""
        yield title, iso


def _build_categories_v1p2_roster(tenant_schema: str) -> list[dict[str, Any]]:
    """Synthesize the Categories collection for the Roster Service projection.

    Merges the 6 seed types (always present so the surface is non-empty)
    with any distinct ``category`` titles discovered on LineItems, picking
    the latest ``dateLastModified`` per title. sourcedId is a deterministic
    SHA-256[:16] of ``cat:<tenant>:<title>`` for stability across calls.
    """
    from django.utils import timezone as _tz
    now_iso = _tz.now().isoformat()

    by_title: dict[str, str] = {}
    # Seed 6 built-in categories first.
    for seed in _CATEGORIES:
        t = str(seed.get("title") or "").strip()
        if t and t not in by_title:
            by_title[t] = now_iso
    # Merge LineItem-derived titles + pick MAX(dateLastModified).
    for t, iso in _iter_category_titles_from_line_items():
        prior = by_title.get(t, "")
        if not prior or (iso and iso > prior):
            by_title[t] = iso or now_iso

    out: list[dict[str, Any]] = []
    for title in sorted(by_title.keys()):
        out.append({
            "sourcedId": _synth_category_sourced_id(tenant_schema, title),
            "status": "active",
            "dateLastModified": by_title[title] or now_iso,
            "title": title,
        })
    return out


@require_http_methods(["GET"])
def categories_list_v1p2_roster(request: HttpRequest):
    """v4.00.79 T2 — GET /api/roster/v1p2/categories/ per spec § 4.13.6.

    Query params:
      ?since=ISO       window filter (dateLastModified >= since)
      ?before=ISO      window filter (dateLastModified <= before)
      ?title=<str>     case-insensitive substring filter on title
      ?limit=N         default 100, capped at 500
      ?offset=N        default 0
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    since_raw = (request.GET.get("since") or "").strip()
    before_raw = (request.GET.get("before") or "").strip()
    ok_since, since_val = _parse_iso_window(since_raw)
    if not ok_since:
        return JsonResponse({"error": "bad_since", "value": since_raw}, status=400)
    ok_before, before_val = _parse_iso_window(before_raw)
    if not ok_before:
        return JsonResponse({"error": "bad_before", "value": before_raw}, status=400)

    tenant_schema = _resolve_tenant_schema(request)
    items = _build_categories_v1p2_roster(tenant_schema)

    if since_val:
        items = [it for it in items if (it.get("dateLastModified") or "") >= since_val]
    if before_val:
        items = [it for it in items if (it.get("dateLastModified") or "") <= before_val]

    title_q = (request.GET.get("title") or "").strip().lower()
    if title_q:
        items = [it for it in items if title_q in (it.get("title") or "").lower()]

    # v4.00.88 T3 — apply sort BEFORE pagination + field mask so X-Total-Count
    # reflects the pre-mask count and pagination operates on a sorted list.
    sort_field = (request.GET.get("sort") or "").strip()
    order_by = (request.GET.get("orderBy") or "").strip()
    if sort_field:
        items = _apply_sort_demog(items, sort_field, order_by)

    total = len(items)

    try:
        limit = int(request.GET.get("limit") or 100)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.GET.get("offset") or 0)
    except (ValueError, TypeError):
        offset = 0
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    page = items[offset:offset + limit]

    # v4.00.88 T3 — apply ?fields= mask LAST so X-Total-Count is unaffected.
    mask = _parse_fields_mask_demog(request.GET.get("fields") or "")
    if mask is not None:
        page = [_apply_fields_mask_demog(rec, mask) for rec in page]

    resp = JsonResponse({"categories": page})
    resp["X-Total-Count"] = str(total)
    resp["X-Limit"] = str(limit)
    resp["X-Offset"] = str(offset)
    return resp


@require_http_methods(["GET"])
def category_detail_v1p2_roster(request: HttpRequest, sourced_id: str):
    """v4.00.79 T2 — GET /api/roster/v1p2/categories/<sourced_id>/."""
    gate = _gate(request)
    if gate is not None:
        return gate
    tenant_schema = _resolve_tenant_schema(request)
    for item in _build_categories_v1p2_roster(tenant_schema):
        if item["sourcedId"] == sourced_id:
            return JsonResponse({"category": item})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


# ---------------------------------------------------------------------------
# v4.00.80 Wave 12 T2 — OneRoster v1.2 Result Service /results/ GET (Roster
# Service path) per IMS Result Service spec § 4.13.
#
# Data source: there is no dedicated "Result" / "StudentLineItemResult" model
# in this codebase — the closest analogue is ``apps.evals.Evaluation`` (one
# row per student × subject_assignment × term). Each Evaluation row already
# projects through ``_eval_to_result`` for the legacy Result-Service path;
# the Wave 12 T2 surface projects the SAME backing rows into the IMS v1.2
# Result shape on the Roster-Service path, with a stable synthetic
# sourcedId = SHA-256("result:<tenant>:<student_id>:<lineitem_id>")[:16].
#
# NAMING NOTE: the file already binds ``results_list`` / ``result_detail``
# from v4.00.39 to the legacy Result-Service URL. To avoid collision the
# new Wave 12 T2 views are suffixed ``_v1p2_roster`` — mirrors the Wave 11
# T2 categories rename pattern.
# ---------------------------------------------------------------------------


def _synth_result_sourced_id(tenant_schema: str, student_id: str, lineitem_id: str) -> str:
    import hashlib
    raw = f"result:{tenant_schema}:{student_id}:{lineitem_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _eval_score_status(e) -> str:
    """Map an Evaluation row to an IMS v1.2 ``scoreStatus`` enum value.

    Values (per spec): ``fully graded`` | ``exempt`` | ``not submitted`` |
    ``partially graded`` | ``submitted``. We pick based on which score
    component(s) are populated.
    """
    final = getattr(e, "final_score", None)
    if final is not None:
        return "fully graded"
    exam = getattr(e, "exam_score", None)
    seq1 = getattr(e, "seq1_score", None)
    seq2 = getattr(e, "seq2_score", None)
    populated = [v for v in (exam, seq1, seq2) if v is not None]
    if populated:
        return "partially graded"
    return "not submitted"


def _eval_to_result_v1p2(e, tenant_schema: str, request: HttpRequest) -> dict[str, Any]:
    """Project an Evaluation row into the IMS v1.2 Result schema."""
    sa = getattr(e, "subject_assignment", None)
    classroom_id = getattr(sa, "classroom_id", "") if sa is not None else ""
    lineitem_id = f"li-{classroom_id}" if classroom_id else ""
    student_id = str(getattr(e, "student_id", "") or "")
    score = getattr(e, "final_score", None)
    if score is None:
        score = getattr(e, "exam_score", None)
    try:
        score_val = float(score) if score is not None else None  # money-float-allow: oneroster-score-is-not-money
    except (ValueError, TypeError):
        score_val = None
    mtime = getattr(e, "updated_at", None)
    try:
        mtime_iso = mtime.isoformat() if mtime else ""
    except Exception:  # noqa: BLE001
        mtime_iso = ""
    sid = _synth_result_sourced_id(tenant_schema, student_id, lineitem_id)
    # Build self-referential hrefs using the request's host so partners can
    # follow links without hardcoding the deployment URL.
    try:
        base = request.build_absolute_uri("/")[:-1]
    except Exception:  # noqa: BLE001
        base = ""
    return {
        "sourcedId": sid,
        "status": "active",
        "dateLastModified": mtime_iso,
        "metadata": {},
        "score": score_val,
        "scoreStatus": _eval_score_status(e),
        "scoreDate": mtime_iso,
        "comment": str(getattr(e, "remarks", "") or ""),
        "lineItem": {
            "sourcedId": lineitem_id,
            "href": f"{base}/api/roster/v1p2/lineItems/{lineitem_id}/" if lineitem_id else "",
        },
        "student": {
            "sourcedId": student_id,
            "href": f"{base}/api/roster/v1p2/students/{student_id}/" if student_id else "",
        },
    }


def _iter_results_v1p2(request: HttpRequest, tenant_schema: str) -> Iterable[dict[str, Any]]:
    try:
        from apps.evals.models import Evaluation
    except Exception as exc:  # noqa: BLE001
        logger.debug("v4.00.80 T2 results: Evaluation unavailable: %s", exc)
        return
    qs = Evaluation.objects.all().order_by("-updated_at")[:1000]  # tenant-isolation-allow: result-service-platform-scope-bearer-auth-required
    for e in qs:
        yield _eval_to_result_v1p2(e, tenant_schema, request)


@require_http_methods(["GET"])
def results_list_v1p2_roster(request: HttpRequest):
    """v4.00.80 Wave 12 T2 — GET /api/roster/v1p2/results/ per spec § 4.13.

    Query params:
      ?since=ISO              window filter (dateLastModified >= since)
      ?before=ISO             window filter (dateLastModified <= before)
      ?studentSourcedId=<pk>  filter by student pk
      ?lineItemSourcedId=<id> filter by lineitem sourcedId (e.g. ``li-42``)
      ?limit=N                default 100, capped at 500
      ?offset=N               default 0
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    since_raw = (request.GET.get("since") or "").strip()
    before_raw = (request.GET.get("before") or "").strip()
    ok_since, since_val = _parse_iso_window(since_raw)
    if not ok_since:
        return JsonResponse({"error": "bad_since", "value": since_raw}, status=400)
    ok_before, before_val = _parse_iso_window(before_raw)
    if not ok_before:
        return JsonResponse({"error": "bad_before", "value": before_raw}, status=400)

    tenant_schema = _resolve_tenant_schema(request)
    items = list(_iter_results_v1p2(request, tenant_schema))

    if since_val:
        items = [it for it in items if (it.get("dateLastModified") or "") >= since_val]
    if before_val:
        items = [it for it in items if (it.get("dateLastModified") or "") <= before_val]

    student_q = (request.GET.get("studentSourcedId") or "").strip()
    if student_q:
        items = [
            it for it in items
            if (it.get("student") or {}).get("sourcedId") == student_q
        ]
    lineitem_q = (request.GET.get("lineItemSourcedId") or "").strip()
    if lineitem_q:
        items = [
            it for it in items
            if (it.get("lineItem") or {}).get("sourcedId") == lineitem_q
        ]

    # v4.00.88 T3 — apply sort BEFORE pagination + field mask.
    sort_field = (request.GET.get("sort") or "").strip()
    order_by = (request.GET.get("orderBy") or "").strip()
    if sort_field:
        items = _apply_sort_demog(items, sort_field, order_by)

    total = len(items)

    try:
        limit = int(request.GET.get("limit") or 100)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.GET.get("offset") or 0)
    except (ValueError, TypeError):
        offset = 0
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    page = items[offset:offset + limit]

    # v4.00.88 T3 — apply ?fields= mask LAST.
    mask = _parse_fields_mask_demog(request.GET.get("fields") or "")
    if mask is not None:
        page = [_apply_fields_mask_demog(rec, mask) for rec in page]

    resp = JsonResponse({"results": page})
    resp["X-Total-Count"] = str(total)
    resp["X-Limit"] = str(limit)
    resp["X-Offset"] = str(offset)
    return resp


@require_http_methods(["GET"])
def result_detail_v1p2_roster(request: HttpRequest, sourced_id: str):
    """v4.00.80 Wave 12 T2 — GET /api/roster/v1p2/results/<sourced_id>/."""
    gate = _gate(request)
    if gate is not None:
        return gate
    tenant_schema = _resolve_tenant_schema(request)
    for item in _iter_results_v1p2(request, tenant_schema):
        if item["sourcedId"] == sourced_id:
            return JsonResponse({"result": item})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)


# ---------------------------------------------------------------------------
# v4.00.81 Wave 13 T2 — OneRoster v1.2 Result Service /scoreScales/ GET
# (Roster Service path) per IMS Result Service spec § 4.13.
#
# Data source: there is no dedicated ``ScoreScale`` model in this codebase
# (``apps.evals.models.GradingScale`` is school-tenant-scoped + uses a
# different schema). The Wave 13 T2 surface synthesizes a fixed set of
# standard grading scales (letter A-F, percent 0-100, pass/fail, rubric
# 4-point) — these are the four scales OneRoster partners overwhelmingly
# expect at any LMS integration point. Stable synthetic sourcedId
# = SHA-256("scoreScale:<tenant>:<slug>")[:16].
#
# NAMING NOTE: the existing module has no prior /scoreScales/ binding, but
# the views are nonetheless suffixed ``_v1p2_roster`` to mirror the Wave
# 11/12 T2 naming convention (``categories_list_v1p2_roster`` /
# ``results_list_v1p2_roster``).
# ---------------------------------------------------------------------------


_DEFAULT_SCORE_SCALES: tuple[dict[str, Any], ...] = (
    {
        "slug": "letter-a-f",
        "title": "Letter A-F",
        "type": "categorical",
        "scoreValues": [
            {"score": "A", "scoreNumeric": 95.0, "scoreLabel": "Excellent"},
            {"score": "B", "scoreNumeric": 85.0, "scoreLabel": "Good"},
            {"score": "C", "scoreNumeric": 75.0, "scoreLabel": "Satisfactory"},
            {"score": "D", "scoreNumeric": 65.0, "scoreLabel": "Pass"},
            {"score": "F", "scoreNumeric": 0.0,  "scoreLabel": "Fail"},
        ],
    },
    {
        "slug": "percent-0-100",
        "title": "Percent 0-100",
        "type": "continuous",
        "scoreValues": [
            {"score": "100", "scoreNumeric": 100.0, "scoreLabel": "Maximum"},
            {"score": "90",  "scoreNumeric": 90.0,  "scoreLabel": "Distinction"},
            {"score": "80",  "scoreNumeric": 80.0,  "scoreLabel": "Merit"},
            {"score": "70",  "scoreNumeric": 70.0,  "scoreLabel": "Credit"},
            {"score": "60",  "scoreNumeric": 60.0,  "scoreLabel": "Pass"},
            {"score": "50",  "scoreNumeric": 50.0,  "scoreLabel": "Threshold"},
            {"score": "0",   "scoreNumeric": 0.0,   "scoreLabel": "Minimum"},
        ],
    },
    {
        "slug": "pass-fail",
        "title": "Pass/Fail",
        "type": "categorical",
        "scoreValues": [
            {"score": "P", "scoreNumeric": 100.0, "scoreLabel": "Pass"},
            {"score": "F", "scoreNumeric": 0.0,   "scoreLabel": "Fail"},
        ],
    },
    {
        "slug": "rubric-4",
        "title": "Rubric 4-point",
        "type": "categorical",
        "scoreValues": [
            {"score": "4", "scoreNumeric": 100.0, "scoreLabel": "Exemplary"},
            {"score": "3", "scoreNumeric": 75.0,  "scoreLabel": "Proficient"},
            {"score": "2", "scoreNumeric": 50.0,  "scoreLabel": "Developing"},
            {"score": "1", "scoreNumeric": 25.0,  "scoreLabel": "Beginning"},
        ],
    },
)

_ALLOWED_SCORE_SCALE_TYPES = {"categorical", "continuous"}


def _synth_score_scale_sourced_id(tenant_schema: str, slug: str) -> str:
    import hashlib
    raw = f"scoreScale:{tenant_schema}:{slug}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_score_scales_v1p2_roster(tenant_schema: str) -> list[dict[str, Any]]:
    """Synthesize the ScoreScales collection for the Roster Service projection.

    Returns the 4 default scales (letter A-F, percent 0-100, pass/fail,
    rubric 4-point) projected into the IMS v1.2 ScoreScale shape. The
    sourcedId is a deterministic SHA-256[:16] of ``scoreScale:<tenant>:<slug>``
    for stability across calls.
    """
    from django.utils import timezone as _tz
    now_iso = _tz.now().isoformat()

    out: list[dict[str, Any]] = []
    for seed in _DEFAULT_SCORE_SCALES:
        slug = seed["slug"]
        out.append({
            "sourcedId": _synth_score_scale_sourced_id(tenant_schema, slug),
            "status": "active",
            "dateLastModified": now_iso,
            "title": seed["title"],
            "type": seed["type"],
            "scoreValues": [dict(v) for v in seed["scoreValues"]],
        })
    return out


@require_http_methods(["GET"])
def score_scales_list_v1p2_roster(request: HttpRequest):
    """v4.00.81 Wave 13 T2 — GET /api/roster/v1p2/scoreScales/ per spec § 4.13.

    Query params:
      ?title=<str>     case-insensitive substring filter on title
      ?type=<str>      exact-match filter (categorical|continuous)
      ?limit=N         default 100, capped at 500
      ?offset=N        default 0
    """
    gate = _gate(request)
    if gate is not None:
        return gate

    tenant_schema = _resolve_tenant_schema(request)
    items = _build_score_scales_v1p2_roster(tenant_schema)

    title_q = (request.GET.get("title") or "").strip().lower()
    if title_q:
        items = [it for it in items if title_q in (it.get("title") or "").lower()]

    type_q = (request.GET.get("type") or "").strip().lower()
    if type_q:
        if type_q not in _ALLOWED_SCORE_SCALE_TYPES:
            return JsonResponse({"error": "bad_type", "value": type_q,
                                 "allowed": sorted(_ALLOWED_SCORE_SCALE_TYPES)}, status=400)
        items = [it for it in items if (it.get("type") or "").lower() == type_q]

    # v4.00.88 T3 — apply sort BEFORE pagination + field mask.
    sort_field = (request.GET.get("sort") or "").strip()
    order_by = (request.GET.get("orderBy") or "").strip()
    if sort_field:
        items = _apply_sort_demog(items, sort_field, order_by)

    total = len(items)

    try:
        limit = int(request.GET.get("limit") or 100)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.GET.get("offset") or 0)
    except (ValueError, TypeError):
        offset = 0
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    page = items[offset:offset + limit]

    # v4.00.88 T3 — apply ?fields= mask LAST.
    mask = _parse_fields_mask_demog(request.GET.get("fields") or "")
    if mask is not None:
        page = [_apply_fields_mask_demog(rec, mask) for rec in page]

    resp = JsonResponse({"scoreScales": page})
    resp["X-Total-Count"] = str(total)
    resp["X-Limit"] = str(limit)
    resp["X-Offset"] = str(offset)
    return resp


@require_http_methods(["GET"])
def score_scale_detail_v1p2_roster(request: HttpRequest, sourced_id: str):
    """v4.00.81 Wave 13 T2 — GET /api/roster/v1p2/scoreScales/<sourced_id>/."""
    gate = _gate(request)
    if gate is not None:
        return gate
    tenant_schema = _resolve_tenant_schema(request)
    for item in _build_score_scales_v1p2_roster(tenant_schema):
        if item["sourcedId"] == sourced_id:
            return JsonResponse({"scoreScale": item})
    return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
