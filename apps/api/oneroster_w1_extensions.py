"""OneRoster v1p2 bulk write surfaces (Studio-OS W1 Pillar D).

D2  POST   /roster/v1p2/classes/bulk/        bulk POST (cap 500, idempotency)
D3  POST   /roster/v1p2/enrollments/bulk/    bulk POST (cap 500, idempotency)

These require the same auth model as the existing OneRoster surface (via
``django.contrib.auth`` middleware + ``_require_write_scope``).

The read-side projection / delta / lineItem helpers that once lived here
(D1/D11/D12/D13/D14) were retired 2026-06-15: they were unrouted dead code
referencing models that do not exist in this codebase
(``assessments.Evaluation``, ``grading.Evaluation``, ``people.Employment``,
``schools.Section``, ``schools.Enrollment``). See
``docs/CSS_RETIREMENT_DOCKET.md``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from apps.api.oneroster import _gate, _require_write_scope
from apps.api.oneroster_writes import _upsert_class, _upsert_enrollment
from apps.platform_runtime.workflow_tracker import track_workflow

logger = logging.getLogger(__name__)

_BULK_CAP = 500


def _bulk_post_payload(request: HttpRequest) -> tuple[list[dict] | None, JsonResponse | None]:
    if not request.body:
        return None, JsonResponse({"error": "empty_body"}, status=400)
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return None, JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "bad_envelope"}, status=400)
    rows = (
        payload.get("rows")
        or payload.get("items")
        or payload.get("classes")
        or payload.get("enrollments")
        or []
    )
    if not isinstance(rows, list):
        return None, JsonResponse({"error": "rows_must_be_list"}, status=400)
    if len(rows) > _BULK_CAP:
        return None, JsonResponse({
            "error": "bulk_cap_exceeded", "received": len(rows), "max": _BULK_CAP,
        }, status=400)
    return rows, None


def _bulk_write_response(
    *,
    operation: str,
    rows: list[dict],
    upsert,
) -> JsonResponse:
    results: list[dict[str, Any]] = []
    summary = {"created": 0, "updated": 0, "error": 0, "total": len(rows)}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            results.append(
                {"index": index, "status": "error", "reason": "row_must_be_object"}
            )
            summary["error"] += 1
            continue
        sourced_id = str(row.get("sourcedId") or "").strip()
        if not sourced_id:
            results.append(
                {"index": index, "status": "error", "reason": "missing_sourced_id"}
            )
            summary["error"] += 1
            continue
        try:
            payload, status_code = upsert(sourced_id, row)
        except Exception:
            logger.exception("%s failed sourced_id=%s", operation, sourced_id)
            payload, status_code = {"error": "upsert_failed"}, 500
        if status_code in (200, 201):
            outcome = "created" if status_code == 201 else "updated"
            results.append({"sourcedId": sourced_id, "status": outcome})
            summary[outcome] += 1
        else:
            results.append(
                {
                    "sourcedId": sourced_id,
                    "status": "error",
                    "reason": str(payload.get("error") or "upsert_failed"),
                }
            )
            summary["error"] += 1
    return JsonResponse(
        {"operation": operation, "summary": summary, "results": results},
        status=207,
    )


def _bulk_idempotency(
    request: HttpRequest,
    *,
    operation: str,
) -> tuple[str, dict[str, Any] | None, JsonResponse | None]:
    key = request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()[:200]
    if not key:
        return "", None, JsonResponse(
            {"error": "missing_idempotency_key"},
            status=428,
        )
    digest = hashlib.sha256(request.body or b"").hexdigest()
    cache_key = f"oneroster:w1-bulk:{operation}:{key}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        if cached.get("digest") != digest:
            return key, None, JsonResponse(
                {"error": "idempotency_key_payload_mismatch"},
                status=409,
            )
        return key, cached, None
    return key, {"cache_key": cache_key, "digest": digest}, None


def _persist_bulk_idempotency(
    state: dict[str, Any],
    response: JsonResponse,
) -> None:
    cache.set(
        state["cache_key"],
        {
            "digest": state["digest"],
            "body": json.loads(response.content),
            "status": response.status_code,
        },
        timeout=60 * 60 * 24,
    )


@require_POST
@track_workflow(
    "oneroster_classes_bulk_post",
    steps=("parse", "validate", "persist"),
    expected_duration_seconds=20,
)
def classes_bulk_post(request: HttpRequest) -> HttpResponse:
    gate = _gate(request)
    if gate is not None:
        return gate
    scope_gate = _require_write_scope(request)
    if scope_gate is not None:
        return scope_gate
    rows, err = _bulk_post_payload(request)
    if err is not None:
        return err
    _, state, idem_error = _bulk_idempotency(
        request,
        operation="classes_bulk_post",
    )
    if idem_error is not None:
        return idem_error
    if state and "body" in state:
        response = JsonResponse(state["body"], status=int(state["status"]))
        response["Idempotency-Replay"] = "true"
        return response
    response = _bulk_write_response(
        operation="classes_bulk_post",
        rows=rows,
        upsert=_upsert_class,
    )
    _persist_bulk_idempotency(state or {}, response)
    return response


@require_POST
@track_workflow(
    "oneroster_enrollments_bulk_post",
    steps=("parse", "validate", "persist"),
    expected_duration_seconds=20,
)
def enrollments_bulk_post(request: HttpRequest) -> HttpResponse:
    gate = _gate(request)
    if gate is not None:
        return gate
    scope_gate = _require_write_scope(request)
    if scope_gate is not None:
        return scope_gate
    rows, err = _bulk_post_payload(request)
    if err is not None:
        return err
    _, state, idem_error = _bulk_idempotency(
        request,
        operation="enrollments_bulk_post",
    )
    if idem_error is not None:
        return idem_error
    if state and "body" in state:
        response = JsonResponse(state["body"], status=int(state["status"]))
        response["Idempotency-Replay"] = "true"
        return response
    response = _bulk_write_response(
        operation="enrollments_bulk_post",
        rows=rows,
        upsert=_upsert_enrollment,
    )
    _persist_bulk_idempotency(state or {}, response)
    return response
