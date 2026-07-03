"""Operator school merge/split console — /portal/super/school-batches/ (Wave D).

Same grammar as the transfers/merges consoles: staff-only, JSON+HTML off one
view (``?format=json``), csrf-protected mutations, 500-row cap, best-effort
compliance audit. The console drives the SchoolTransferBatch FSM:
create-and-preview → dual approval (two DISTINCT operators, each retyping the
source slug) → start (fan out cases) → advance (chunked) → wind-down handoff
(merge only; export + deactivate, never purge).
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_ROW_CAP = 500
_MAX_ADVANCE_CHUNK = 20


def _wants_json(request) -> bool:
    source = request.GET if request.method == "GET" else request.POST
    return (source.get("format") or request.GET.get("format") or "").lower() == "json"


def _respond(request, payload: dict, ok: bool = True, status: int = 200):
    if _wants_json(request):
        return JsonResponse({"ok": ok, **payload}, status=status)
    return HttpResponseRedirect(reverse("portal:school_batches_index"))


def _batch_row(batch, rollup: dict | None = None) -> dict:
    history = batch.history or []
    last = history[-1] if history else {}
    return {
        "id": str(batch.pk),
        "kind": batch.kind,
        "status": batch.status,
        "consent_mode": batch.consent_mode,
        "source_school": getattr(batch.source_school, "name", ""),
        "target_school": getattr(batch.target_school, "name", ""),
        "to_move": (batch.preview or {}).get("to_move"),
        "cases": rollup or {},
        "wind_down": bool((batch.wind_down or {}).get("deactivated")),
        "created_at": batch.created_at.isoformat() if batch.created_at else "",
        "last_note": last.get("note")
        or (f"{last.get('from', '')} → {last.get('to', '')}" if last else ""),
    }


def _rollups(batches) -> dict:
    """One aggregate query: case counts by status per batch."""
    from django.db.models import Count

    from apps.people.models_transfer import TransferCase

    out: dict = {}
    rows = (
        TransferCase.objects.filter(batch__in=list(batches))  # tenant-isolation-allow: operator-console-platform-scope-staff-required
        .values("batch_id", "status")
        .annotate(n=Count("id"))
    )
    for row in rows:
        out.setdefault(str(row["batch_id"]), {})[row["status"]] = row["n"]
    return out


def _audit_batch_action(request, batch, note: str) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            user=request.user if request.user.is_authenticated else None,
            model_name="SchoolTransferBatch",
            object_id=str(batch.pk)[:200],
            object_repr=f"school batch ({note})"[:200],
            app_label="people",
            new_values={"status": batch.status},
        )
    except Exception:  # noqa: BLE001 — audit must never block the console
        logger.warning("school_batch_console_audit_failed batch=%s", batch.pk)


def _load_batch(request):
    from django.core.exceptions import ValidationError

    from apps.people.models_school_batch import SchoolTransferBatch

    batch_pk = (request.POST.get("batch_id") or "").strip()
    try:
        return SchoolTransferBatch.objects.select_related(
            "source_school", "target_school"
        ).filter(pk=batch_pk).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    except (ValidationError, ValueError):
        # UUID fields raise ValidationError on malformed input (Wave B lesson).
        return None


@staff_member_required
@require_http_methods(["GET"])
def school_batches_index(request):
    """List school merge/split batches (platform scope — operator console)."""
    from apps.people.models_school_batch import SchoolTransferBatch

    qs = SchoolTransferBatch.objects.select_related(
        "source_school", "target_school"
    ).order_by("-created_at")  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    status = (request.GET.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    rows = list(qs[:_ROW_CAP])
    rollups = _rollups(rows) if rows else {}
    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "count": len(rows),
                "batches": [_batch_row(b, rollups.get(str(b.pk))) for b in rows],
            }
        )
    display_rows = [
        (
            batch,
            " ".join(
                f"{case_status}:{n}"
                for case_status, n in sorted(
                    (rollups.get(str(batch.pk)) or {}).items()
                )
            ),
        )
        for batch in rows
    ]
    return render(
        request,
        "super/school_batches/index.html",
        {"rows": display_rows, "status_filter": status},
    )


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_create(request):
    """Open a batch and preview its fan-out in one step."""
    from apps.people.models_school_batch import SchoolTransferBatch
    from apps.people.school_batch_service import BatchBlockedError, preview_batch
    from apps.schools.models import School

    kind = (request.POST.get("kind") or "").strip()
    consent_mode = (
        request.POST.get("consent_mode") or SchoolTransferBatch.ConsentMode.INSTITUTIONAL
    ).strip()
    if kind not in SchoolTransferBatch.Kind.values:
        return _respond(request, {"error": "kind must be merge or split"}, ok=False, status=400)
    if consent_mode not in SchoolTransferBatch.ConsentMode.values:
        return _respond(request, {"error": "unknown consent_mode"}, ok=False, status=400)

    source = School.objects.filter(pk=(request.POST.get("source_school_id") or "").strip(), is_active=True).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    target = School.objects.filter(pk=(request.POST.get("target_school_id") or "").strip(), is_active=True).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if source is None or target is None:
        return _respond(request, {"error": "source or target school not found"}, ok=False, status=404)
    if source.pk == target.pk:
        return _respond(request, {"error": "target school must differ from source"}, ok=False, status=400)

    def _ids(name: str) -> list[str]:
        raw = (request.POST.get(name) or "").strip()
        return [part.strip() for part in raw.split(",") if part.strip()]

    cohort = {}
    classroom_ids = _ids("classroom_ids")
    student_pks = _ids("student_pks")
    if classroom_ids:
        cohort["classroom_ids"] = classroom_ids
    if student_pks:
        cohort["student_pks"] = student_pks

    batch = SchoolTransferBatch.objects.create(
        kind=kind,
        source_school=source,
        target_school=target,
        consent_mode=consent_mode,
        consent_basis=(request.POST.get("consent_basis") or "").strip(),
        cohort=cohort,
        created_by=request.user if request.user.is_authenticated else None,
    )
    try:
        preview_batch(batch)
    except BatchBlockedError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    _audit_batch_action(request, batch, "batch opened + previewed")
    return _respond(request, {"batch": _batch_row(batch)}, status=201)


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_approve(request):
    """Record one of the two distinct-operator approvals (confirm slug typed)."""
    from apps.people.school_batch_service import (
        BatchBlockedError,
        record_batch_approval,
    )

    batch = _load_batch(request)
    if batch is None:
        return _respond(request, {"error": "batch not found"}, ok=False, status=404)
    try:
        outcome = record_batch_approval(
            batch, request.user, request.POST.get("confirm_slug") or ""
        )
    except BatchBlockedError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    _audit_batch_action(request, batch, "approval recorded")
    return _respond(request, {"batch": _batch_row(batch), **outcome})


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_start(request):
    """Fan out the cases; batch → RUNNING."""
    from apps.people.school_batch_service import BatchBlockedError, start_batch

    batch = _load_batch(request)
    if batch is None:
        return _respond(request, {"error": "batch not found"}, ok=False, status=404)
    try:
        outcome = start_batch(batch, actor=request.user)
    except BatchBlockedError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    _audit_batch_action(request, batch, "batch started")
    return _respond(request, {"batch": _batch_row(batch), **outcome})


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_advance(request):
    """Run one chunk of cases now (the periodic job does the same off-console)."""
    from apps.people.school_batch_service import (
        DEFAULT_CHUNK,
        BatchBlockedError,
        advance_batch,
    )

    batch = _load_batch(request)
    if batch is None:
        return _respond(request, {"error": "batch not found"}, ok=False, status=404)
    try:
        chunk = min(int(request.POST.get("max_cases") or DEFAULT_CHUNK), _MAX_ADVANCE_CHUNK)
    except (TypeError, ValueError):
        chunk = DEFAULT_CHUNK
    try:
        summary = advance_batch(batch, actor=request.user, max_cases=chunk)
    except BatchBlockedError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    except Exception as exc:  # noqa: BLE001 — surface, never 500 the console
        logger.exception("school_batch_console_advance_failed batch=%s", batch.pk)
        batch.refresh_from_db()
        return _respond(
            request,
            {"error": f"{type(exc).__name__}: {exc}", "batch": _batch_row(batch)},
            ok=False,
            status=500,
        )
    _audit_batch_action(request, batch, "batch advanced")
    return _respond(request, {"batch": _batch_row(batch), "summary": summary})


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_cancel(request):
    """Stop scheduling; in-flight cases finish their own FSM."""
    from apps.people.models_school_batch import BatchStateError
    from apps.people.school_batch_service import cancel_batch

    batch = _load_batch(request)
    if batch is None:
        return _respond(request, {"error": "batch not found"}, ok=False, status=404)
    try:
        cancel_batch(batch, actor=request.user)
    except BatchStateError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    _audit_batch_action(request, batch, "batch cancelled")
    return _respond(request, {"batch": _batch_row(batch)})


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def school_batch_wind_down(request):
    """Merge handoff: export + deactivate the source (confirm slug re-typed)."""
    from apps.people.school_batch_service import BatchBlockedError, wind_down_source

    batch = _load_batch(request)
    if batch is None:
        return _respond(request, {"error": "batch not found"}, ok=False, status=404)
    try:
        receipt = wind_down_source(
            batch,
            actor=request.user,
            confirm_slug=request.POST.get("confirm_slug") or "",
        )
    except BatchBlockedError as exc:
        return _respond(request, {"error": str(exc), "batch": _batch_row(batch)}, ok=False, status=409)
    _audit_batch_action(request, batch, "source wound down")
    return _respond(request, {"batch": _batch_row(batch), "wind_down": receipt})
