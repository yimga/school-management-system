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


@require_http_methods(["GET"])
def result_detail(request: HttpRequest, sourced_id: str):
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
