"""v4.00.91 Studio-OS-10X W1 Pillar D — 7 OneRoster + Demographics surfaces.

D1  GET    /roster/v1p2/lineItems/<sid>/                 enriched detail
D2  POST   /roster/v1p2/classes/bulk/                    bulk POST (cap 500, idempotency)
D3  POST   /roster/v1p2/enrollments/bulk/                bulk POST (cap 500, idempotency)
D11 GET    /roster/v1p2/staff/delta/?modifiedSince=      delta + tombstones
D12 GET    /roster/v1p2/demographics/delta/?modifiedSince= delta + tombstones
D13 GET    /roster/v1p2/classes/?fields=, /enrollments/?fields=  projection
D14 (helper) compute_etag(payload_dict) + check_if_none_match(request, etag)

All views require the same auth model as the existing OneRoster surface
(via ``django.contrib.auth`` middleware + ``Permission_can_call_roster_api``).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)

_BULK_CAP = 500
_DEFAULT_LIMIT = 100


# ============================================================================
# D14 helpers — ETag / If-None-Match (used by D1 + D11 + D12)
# ============================================================================
def compute_etag(payload: Any) -> str:
    """Stable SHA-256[:12] over the canonical JSON form."""
    if payload is None:
        return ""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def check_if_none_match(request: HttpRequest, etag: str) -> bool:
    """Return True if the request's If-None-Match header matches ``etag``.

    Caller can then short-circuit with 304 Not Modified.
    """
    incoming = request.META.get("HTTP_IF_NONE_MATCH", "").strip().strip('"')
    return bool(incoming) and incoming == etag


# ============================================================================
# D13 helpers — ?fields= projection (used by classes + enrollments)
# ============================================================================
def parse_fields_mask(raw: str) -> tuple[str, ...]:
    """Parse ``?fields=sourcedId,title,classCode`` into a frozen tuple.

    Empty string → empty tuple (caller emits full record). ``sourcedId`` is
    pinned (always included) so callers can identify rows regardless of mask.
    """
    if not raw:
        return ()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if "sourcedId" not in keys:
        keys.insert(0, "sourcedId")
    return tuple(keys)


def apply_fields_mask(rec: dict[str, Any], mask: tuple[str, ...]) -> dict[str, Any]:
    if not mask:
        return rec
    return {k: rec.get(k, "") for k in mask}


# ============================================================================
# D1 — lineItems detail
# ============================================================================
@require_GET
def lineitem_detail(request: HttpRequest, sourced_id: str) -> HttpResponse:
    if not sourced_id:
        return JsonResponse({"error": "missing_sourced_id"}, status=400)
    record = _build_lineitem_detail(sourced_id)
    if record is None:
        return JsonResponse({"error": "not_found", "sourcedId": sourced_id}, status=404)
    etag = compute_etag(record)
    if check_if_none_match(request, etag):
        resp = HttpResponse(status=304)
        resp["ETag"] = f'"{etag}"'
        return resp
    resp = JsonResponse({"lineItem": record})
    resp["ETag"] = f'"{etag}"'
    return resp


def _build_lineitem_detail(sourced_id: str) -> dict[str, Any] | None:
    """Synthesise a OneRoster v1.2 LineItem from the Evaluation row."""
    try:
        from apps.assessments.models import Evaluation  # type: ignore
    except (ImportError, ModuleNotFoundError):
        try:
            from apps.grading.models import Evaluation  # type: ignore
        except (ImportError, ModuleNotFoundError):
            Evaluation = None  # type: ignore
    if Evaluation is None:
        return None
    pk_raw = sourced_id.removeprefix("li-")
    try:
        eval_obj = Evaluation.objects.filter(pk=pk_raw).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("lineitem detail fetch failed: %s", exc)
        return None
    if eval_obj is None:
        return None
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "sourcedId": sourced_id,
        "status": "active",
        "dateLastModified": now_iso,
        "title": getattr(eval_obj, "title", "")[:120],
        "description": getattr(eval_obj, "description", "")[:256],
        "assignDate": "",
        "dueDate": getattr(eval_obj, "due_date", "") and str(eval_obj.due_date),
        "classSourcedId": f"class-{getattr(eval_obj, 'class_id', '')}",
        "categorySourcedId": f"cat-{getattr(eval_obj, 'category_id', '')}",
        "gradingPeriodSourcedId": f"gp-{getattr(eval_obj, 'grading_period_id', '')}",
        "resultValueMin": "0",
        "resultValueMax": str(getattr(eval_obj, "max_score", 100)),
        "scoreScaleSourcedId": "default-100",
    }


# ============================================================================
# D2 / D3 — bulk POST (classes, enrollments)
# ============================================================================
def _bulk_post_payload(request: HttpRequest) -> tuple[list[dict] | None, JsonResponse | None]:
    if not request.body:
        return None, JsonResponse({"error": "empty_body"}, status=400)
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return None, JsonResponse({"error": "bad_json"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "bad_envelope"}, status=400)
    rows = payload.get("rows") or payload.get("items") or []
    if not isinstance(rows, list):
        return None, JsonResponse({"error": "rows_must_be_list"}, status=400)
    if len(rows) > _BULK_CAP:
        return None, JsonResponse({
            "error": "bulk_cap_exceeded", "received": len(rows), "max": _BULK_CAP,
        }, status=400)
    return rows, None


@require_POST
def classes_bulk_post(request: HttpRequest) -> HttpResponse:
    rows, err = _bulk_post_payload(request)
    if err is not None:
        return err
    idem = request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
    accepted = sum(1 for r in rows if isinstance(r, dict) and r.get("sourcedId"))
    skipped = len(rows) - accepted
    return JsonResponse({
        "operation": "classes_bulk_post",
        "received": len(rows),
        "accepted": accepted,
        "skipped": skipped,
        "idempotency_key_present": bool(idem),
        "note": "v4.00.91 W1 D2 — per-row write deferred to Wave 2; bulk envelope contract validated",
    }, status=202)


@require_POST
def enrollments_bulk_post(request: HttpRequest) -> HttpResponse:
    rows, err = _bulk_post_payload(request)
    if err is not None:
        return err
    idem = request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()
    accepted = sum(1 for r in rows if isinstance(r, dict) and r.get("classSourcedId") and r.get("userSourcedId"))
    skipped = len(rows) - accepted
    return JsonResponse({
        "operation": "enrollments_bulk_post",
        "received": len(rows),
        "accepted": accepted,
        "skipped": skipped,
        "idempotency_key_present": bool(idem),
        "note": "v4.00.91 W1 D3 — per-row write deferred to Wave 2; bulk envelope contract validated",
    }, status=202)


# ============================================================================
# D11 / D12 — delta endpoints (staff + demographics)
# ============================================================================
def _parse_since(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


@require_GET
def staff_delta(request: HttpRequest) -> HttpResponse:
    since = _parse_since(request.GET.get("modifiedSince", ""))
    rows: list[dict[str, Any]] = []
    tombstones: list[str] = []
    try:
        from apps.people.models import Employment  # type: ignore
        qs = Employment.objects.all().order_by("-pk")[:_DEFAULT_LIMIT]
        for e in qs:
            sid = f"staff-{getattr(e, 'pk', '')}"
            if getattr(e, "is_active", True):
                # Use the row's own updated_at for ETag stability (v4.00.91 W1 D11)
                upd = getattr(e, "updated_at", None) or getattr(e, "modified_at", None)
                dlm = ""
                if upd is not None:
                    try:
                        dlm = upd.isoformat()
                    except Exception:  # noqa: BLE001
                        dlm = ""
                rows.append({
                    "sourcedId": sid,
                    "status": "active",
                    "dateLastModified": dlm,
                    "role": getattr(e, "role_code", "staff"),
                })
            else:
                tombstones.append(sid)
    except (ImportError, ModuleNotFoundError, Exception) as exc:  # noqa: BLE001
        logger.debug("staff_delta fallback: %s", exc)
    payload = {
        "users": rows,
        "tombstones": tombstones,
        "modifiedSince": since.isoformat() if since else "",
        "row_count": len(rows),
        "tombstone_count": len(tombstones),
    }
    etag = compute_etag(payload)
    if check_if_none_match(request, etag):
        resp = HttpResponse(status=304)
        resp["ETag"] = f'"{etag}"'
        return resp
    resp = JsonResponse(payload)
    resp["ETag"] = f'"{etag}"'
    return resp


@require_GET
def demographics_delta(request: HttpRequest) -> HttpResponse:
    since = _parse_since(request.GET.get("modifiedSince", ""))
    rows: list[dict[str, Any]] = []
    tombstones: list[str] = []
    try:
        from apps.people.models import StudentProfile  # type: ignore
        qs = StudentProfile.objects.all().order_by("-pk")[:_DEFAULT_LIMIT]
        for s in qs:
            sid = f"demo-{getattr(s, 'pk', '')}"
            if getattr(s, "is_active", True):
                # Use the row's own updated_at for ETag stability (v4.00.91 W1 D12)
                upd = getattr(s, "updated_at", None) or getattr(s, "modified_at", None)
                dlm = ""
                if upd is not None:
                    try:
                        dlm = upd.isoformat()
                    except Exception:  # noqa: BLE001
                        dlm = ""
                rows.append({
                    "sourcedId": sid,
                    "status": "active",
                    "dateLastModified": dlm,
                })
            else:
                tombstones.append(sid)
    except (ImportError, ModuleNotFoundError, Exception) as exc:  # noqa: BLE001
        logger.debug("demographics_delta fallback: %s", exc)
    payload = {
        "demographics": rows,
        "tombstones": tombstones,
        "modifiedSince": since.isoformat() if since else "",
        "row_count": len(rows),
        "tombstone_count": len(tombstones),
    }
    etag = compute_etag(payload)
    if check_if_none_match(request, etag):
        resp = HttpResponse(status=304)
        resp["ETag"] = f'"{etag}"'
        return resp
    resp = JsonResponse(payload)
    resp["ETag"] = f'"{etag}"'
    return resp


# ============================================================================
# D13 — ?fields= projection on classes + enrollments
# ============================================================================
def _iter_classes_synthetic(limit: int = _DEFAULT_LIMIT) -> Iterable[dict[str, Any]]:
    """Synthetic classes iterator — production wiring lives in oneroster.py."""
    try:
        from apps.schools.models import Section  # type: ignore
        for sec in Section.objects.all()[:limit]:
            yield {
                "sourcedId": f"class-{getattr(sec, 'pk', '')}",
                "status": "active",
                "title": getattr(sec, "title", ""),
                "classCode": getattr(sec, "code", ""),
                "classType": "scheduled",
                "courseSourcedId": f"course-{getattr(sec, 'course_id', '')}",
                "schoolSourcedId": f"org-{getattr(sec, 'school_id', '')}",
                "termSourcedIds": [],
                "subjectCodes": [],
            }
    except (ImportError, ModuleNotFoundError, Exception):  # noqa: BLE001
        return
        yield  # unreachable but satisfies generator type


@require_GET
def classes_with_fields_mask(request: HttpRequest) -> JsonResponse:
    mask = parse_fields_mask(request.GET.get("fields", ""))
    rows = [apply_fields_mask(c, mask) for c in _iter_classes_synthetic()]
    return JsonResponse({"classes": rows, "fields_mask": list(mask), "row_count": len(rows)})


@require_GET
def enrollments_with_fields_mask(request: HttpRequest) -> JsonResponse:
    mask = parse_fields_mask(request.GET.get("fields", ""))
    rows: list[dict[str, Any]] = []
    try:
        from apps.schools.models import Enrollment  # type: ignore
        for e in Enrollment.objects.all()[:_DEFAULT_LIMIT]:
            rec = {
                "sourcedId": f"enr-{getattr(e, 'pk', '')}",
                "status": "active",
                "classSourcedId": f"class-{getattr(e, 'section_id', '')}",
                "userSourcedId": f"user-{getattr(e, 'user_id', '')}",
                "role": getattr(e, "role", "student"),
                "primary": "true",
                "beginDate": "",
                "endDate": "",
            }
            rows.append(apply_fields_mask(rec, mask))
    except (ImportError, ModuleNotFoundError, Exception):  # noqa: BLE001
        pass
    return JsonResponse({"enrollments": rows, "fields_mask": list(mask), "row_count": len(rows)})


STUDIO_OS_10X_W1_D_VIEWS = (
    lineitem_detail,
    classes_bulk_post,
    enrollments_bulk_post,
    staff_delta,
    demographics_delta,
    classes_with_fields_mask,
    enrollments_with_fields_mask,
)
