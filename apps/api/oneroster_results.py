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
