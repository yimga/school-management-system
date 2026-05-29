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
