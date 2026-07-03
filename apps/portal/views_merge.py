"""Operator record-merge console — /portal/super/merges/ (Wave C).

Mirrors the transfers console pattern: staff-only, JSON+HTML off one view
(``?format=json``), row caps, best-effort compliance audit on every
mutation. The console drives the RecordMergeOperation FSM (create →
preview → approve → apply) and surfaces the ai_dedup candidates that the
migration-cloud student lander has been writing into bundle
``mapping_summary["dedup_candidates"]`` — previously visible nowhere, now
the merge inbox.
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
_INBOX_BUNDLE_CAP = 200


def _wants_json(request) -> bool:
    source = request.GET if request.method == "GET" else request.POST
    return (source.get("format") or request.GET.get("format") or "").lower() == "json"


def _op_row(op) -> dict:
    history = op.history or []
    last = history[-1] if history else {}
    return {
        "id": str(op.pk),
        "kind": op.kind,
        "status": op.status,
        "school": getattr(op.school, "name", ""),
        "primary_pk": op.primary_pk,
        "secondary_pk": op.secondary_pk,
        "total_rows": (op.preview or {}).get("total_rows"),
        "collisions": len(op.collisions or []),
        "last_note": last.get("note")
        or (f"{last.get('from', '')} → {last.get('to', '')}" if last else ""),
        "created_at": op.created_at.isoformat() if op.created_at else "",
    }


def _respond(request, payload: dict, ok: bool = True, status: int = 200):
    if _wants_json(request):
        return JsonResponse({"ok": ok, **payload}, status=status)
    return HttpResponseRedirect(reverse("portal:merge_ops_index"))


def _audit_merge_action(request, action: str, op, note: str) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=action,
            user=request.user if request.user.is_authenticated else None,
            model_name="RecordMergeOperation",
            object_id=str(op.pk)[:200],
            object_repr=f"record merge ({note})"[:200],
            app_label="people",
            new_values={"status": op.status},
        )
    except Exception:  # noqa: BLE001 — audit must never block the console
        logger.warning("merge_console_audit_failed op=%s", op.pk)


def _dedup_inbox() -> list[dict]:
    """ai_dedup candidates surfaced by the student lander — the merge inbox."""
    try:
        from apps.migration_cloud.models import MigrationBundle
    except ImportError:
        return []
    items: list[dict] = []
    bundles = MigrationBundle.objects.order_by("-id").only(  # tenant-isolation-allow: operator-console-platform-scope-staff-required
        "id", "school_id", "mapping_summary"
    )[:_INBOX_BUNDLE_CAP]
    for bundle in bundles:
        for cand in (bundle.mapping_summary or {}).get("dedup_candidates", []):
            items.append(
                {
                    "bundle_id": bundle.pk,
                    "school_id": str(bundle.school_id or ""),
                    "new_pk": str(cand.get("new_pk", "")),
                    "other_pk": str(cand.get("other_pk", "")),
                    "deterministic_score": cand.get("deterministic_score"),
                    "ai_same_person": cand.get("ai_same_person"),
                    "ai_confidence": cand.get("ai_confidence"),
                }
            )
            if len(items) >= _ROW_CAP:
                return items
    return items


@staff_member_required
@require_http_methods(["GET"])
def merge_ops_index(request):
    """List merge operations + the dedup inbox (platform scope)."""
    from apps.people.models_merge import RecordMergeOperation

    qs = RecordMergeOperation.objects.select_related("school").order_by("-created_at")  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    status = (request.GET.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    rows = list(qs[:_ROW_CAP])
    inbox = _dedup_inbox()
    if _wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "count": len(rows),
                "operations": [_op_row(o) for o in rows],
                "dedup_inbox": inbox,
            }
        )
    return render(
        request,
        "super/merges/index.html",
        {"operations": rows, "dedup_inbox": inbox, "status_filter": status},
    )


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def merge_op_create(request):
    """Open a draft merge for two same-school person rows and preview it."""
    from apps.people.merge_service import (
        MergeBlockedError,
        person_model_for,
        preview_merge,
    )
    from apps.people.models_merge import RecordMergeOperation

    kind = (request.POST.get("kind") or RecordMergeOperation.Kind.STUDENT).strip()
    primary_pk = (request.POST.get("primary_pk") or "").strip()
    secondary_pk = (request.POST.get("secondary_pk") or "").strip()
    if not primary_pk or not secondary_pk:
        return _respond(request, {"error": "primary_pk and secondary_pk required"}, ok=False, status=400)
    if primary_pk == secondary_pk:
        return _respond(request, {"error": "primary and secondary must differ"}, ok=False, status=400)
    try:
        person_model = person_model_for(kind)
    except MergeBlockedError as exc:
        return _respond(request, {"error": str(exc)}, ok=False, status=400)
    primary = person_model._default_manager.filter(pk=primary_pk).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    secondary = person_model._default_manager.filter(pk=secondary_pk).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if primary is None or secondary is None:
        return _respond(request, {"error": "primary or secondary not found"}, ok=False, status=404)
    school = getattr(primary, "school", None)
    if school is None and getattr(primary, "student", None) is not None:
        school = primary.student.school
    if school is None:
        return _respond(request, {"error": "could not resolve school for primary"}, ok=False, status=400)

    op = RecordMergeOperation.objects.create(
        school=school,
        kind=kind,
        primary_pk=primary_pk,
        secondary_pk=secondary_pk,
        created_by=request.user if request.user.is_authenticated else None,
    )
    try:
        preview = preview_merge(op)
    except MergeBlockedError as exc:
        op.advance(RecordMergeOperation.Status.CANCELLED, note=str(exc)[:200])
        return _respond(request, {"error": str(exc), "operation": _op_row(op)}, ok=False, status=409)
    _audit_merge_action(request, "CREATE", op, "merge previewed")
    return _respond(request, {"operation": _op_row(op), "preview": preview}, status=201)


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def merge_op_approve(request):
    from apps.people.merge_service import MergeBlockedError, approve_merge
    from apps.people.models_merge import RecordMergeOperation

    op = RecordMergeOperation.objects.filter(pk=(request.POST.get("operation_id") or "").strip()).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if op is None:
        return _respond(request, {"error": "operation not found"}, ok=False, status=404)
    try:
        approve_merge(op, request.user)
    except MergeBlockedError as exc:
        return _respond(request, {"error": str(exc), "operation": _op_row(op)}, ok=False, status=409)
    _audit_merge_action(request, "UPDATE", op, "merge approved")
    return _respond(request, {"operation": _op_row(op)})


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def merge_op_apply(request):
    from apps.people.merge_service import MergeBlockedError, apply_merge
    from apps.people.models_merge import RecordMergeOperation

    op = RecordMergeOperation.objects.filter(pk=(request.POST.get("operation_id") or "").strip()).first()  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    if op is None:
        return _respond(request, {"error": "operation not found"}, ok=False, status=404)
    try:
        summary = apply_merge(op, actor=request.user)
    except MergeBlockedError as exc:
        return _respond(request, {"error": str(exc), "operation": _op_row(op)}, ok=False, status=409)
    except Exception as exc:  # noqa: BLE001 — surface, never blank-500 the console
        logger.exception("merge_console_apply_failed op=%s", op.pk)
        op.refresh_from_db()
        return _respond(
            request,
            {"error": f"{type(exc).__name__}: {exc}", "operation": _op_row(op)},
            ok=False,
            status=500,
        )
    _audit_merge_action(request, "UPDATE", op, "merge applied")
    return _respond(request, {"operation": _op_row(op), "summary": summary})
