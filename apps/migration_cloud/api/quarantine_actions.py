"""REST API actions for held-row (quarantine) triage on ``BundleViewSet`` (v3.29+).

Endpoints (all tenant-scoped via ``get_object()``):

    GET  /bundles/<pk>/quarantine/          — list pending + summary
    POST /bundles/<pk>/quarantine/resolve/  — apply row / bulk actions
    GET  /bundles/<pk>/quarantine/export/   — CSV download
    POST /bundles/<pk>/ai-explain/          — plain-language row explanation

Mirrors the HTML POST surfaces in ``MigrationCloudQuarantineResolveView`` and
``TenantMigrationQuarantineResolveView`` so partners can automate held-row
workflows without scraping the wizard.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.migration_cloud.reliability import idempotent_post, safe_500

logger = logging.getLogger(__name__)


def _require_quarantine_tenant_admin(request, *, detail: str):
    """Tenant held-row surfaces require admin — mirrors connector HTML gate."""
    from apps.accounts.decorators import user_is_tenant_admin

    from .permissions import _is_operator_shell_request

    if _is_operator_shell_request(request):
        return None
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
    if not user_is_tenant_admin(user, school):
        return Response(
            {"error": "forbidden", "detail": detail},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _require_quarantine_write_access(request):
    return _require_quarantine_tenant_admin(
        request,
        detail="tenant admin required for held-row writes",
    )


def _require_quarantine_read_access(request):
    return _require_quarantine_tenant_admin(
        request,
        detail="tenant admin required for held-row review",
    )


def _resolve_payload(request) -> dict:
    if hasattr(request, "data") and isinstance(request.data, dict):
        return dict(request.data)
    try:
        body = request.body or b"{}"
        if body:
            return json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def _apply_resolve(*, bundle, user, payload: dict) -> tuple[dict, int]:
    from apps.migration_cloud.quarantine_resolution import apply_quarantine_action
    from apps.migration_cloud.repair import repair_bundle

    action_name = (payload.get("action") or "").strip().lower()
    if action_name in ("retry_import", "auto_repair", "smart_repair"):
        result = repair_bundle(bundle_id=bundle.pk, off_http=True)
        return (
            {
                "action": action_name,
                "ok": result.ok or result.queued,
                "queued": result.queued,
                "ran": result.ran,
                "message": result.message,
                "created": result.created,
                "updated": result.updated,
                "quarantined": result.quarantined,
                "auto_remediate": result.auto_remediate,
            },
            status.HTTP_200_OK,
        )

    bulk_actions = {
        "dismiss_informational",
        "waive_all_pending",
        "deny_all_pending",
        "clear_queue",
    }
    if action_name in bulk_actions:
        outcome = apply_quarantine_action(
            bundle=bundle,
            user=user,
            action=action_name,
            note=str(payload.get("note") or ""),
        )
        if payload.get("auto_retry") or outcome.get("queue_reimport"):
            repair_result = repair_bundle(bundle_id=bundle.pk, off_http=True)
            outcome["retry_queued"] = repair_result.queued or repair_result.ran
            outcome["retry_message"] = repair_result.message
        return outcome, status.HTTP_200_OK

    record_ids = payload.get("record_ids") or []
    if isinstance(record_ids, (str, int)):
        record_ids = [record_ids]
    edited = payload.get("edited_source_row")
    if isinstance(edited, str):
        try:
            edited = json.loads(edited)
        except json.JSONDecodeError:
            edited = None
    if edited is not None and not isinstance(edited, dict):
        edited = None

    outcome = apply_quarantine_action(
        bundle=bundle,
        user=user,
        action=action_name,
        record_ids=[int(x) for x in record_ids if str(x).isdigit()],
        note=str(payload.get("note") or ""),
        edited_source_row=edited,
    )
    if not outcome.get("ok"):
        return outcome, status.HTTP_400_BAD_REQUEST

    if payload.get("auto_retry") or outcome.get("queue_reimport"):
        repair_result = repair_bundle(bundle_id=bundle.pk, off_http=True)
        outcome["retry_queued"] = repair_result.queued or repair_result.ran
        outcome["retry_message"] = repair_result.message
    return outcome, status.HTTP_200_OK


def quarantine_list_action_factory():
    """Register ``GET /quarantine/`` on ``BundleViewSet``."""

    @extend_schema(
        tags=["Migration Cloud"],
        summary="List held rows awaiting review",
        description=(
            "Returns pending quarantine records enriched for display, plus "
            "counts and issue-class breakdown. Tenant-scoped via the bundle "
            "lookup."
        ),
        responses={
            200: OpenApiResponse(description="Held-row list + summary JSON"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    @action(detail=True, methods=["get"], url_path="quarantine")
    def quarantine_list(self, request, pk=None):
        denied = _require_quarantine_read_access(request)
        if denied is not None:
            return denied
        from apps.migration_cloud.quarantine_resolution import (
            enrich_quarantine_row,
            pending_quarantine_count,
            quarantine_breakdown,
            quarantine_queryset_for_bundle,
        )

        bundle = self.get_object()
        pending_qs = quarantine_queryset_for_bundle(bundle, pending_only=True).order_by(
            "issue_class", "domain", "row_index", "pk"
        )
        rows = [enrich_quarantine_row(rec) for rec in pending_qs[:200]]
        apply_held = int(
            ((bundle.mapping_summary or {}).get("apply_totals") or {}).get("quarantined") or 0
        )
        pending = pending_quarantine_count(bundle)
        return Response(
            {
                "bundle_id": bundle.pk,
                "pending": pending,
                "total": quarantine_queryset_for_bundle(bundle, pending_only=False).count(),
                "breakdown": quarantine_breakdown(bundle, pending_only=True),
                "apply_held_total": apply_held,
                "review_gap": max(0, apply_held - pending) if apply_held else 0,
                "rows": rows,
            }
        )

    return quarantine_list


def quarantine_resolve_action_factory():
    """Register ``POST /quarantine/resolve/`` on ``BundleViewSet``."""

    resolve_request = inline_serializer(
        name="QuarantineResolveRequest",
        fields={
            "action": serializers.CharField(
                help_text=(
                    "dismiss|waive|deny|accept_edit|dismiss_informational|"
                    "waive_all_pending|deny_all_pending|clear_queue|retry_import"
                ),
            ),
            "record_ids": serializers.ListField(
                child=serializers.IntegerField(),
                required=False,
            ),
            "note": serializers.CharField(required=False, allow_blank=True),
            "edited_source_row": serializers.JSONField(required=False),
            "auto_retry": serializers.BooleanField(required=False, default=False),
        },
    )

    @extend_schema(
        tags=["Migration Cloud"],
        summary="Resolve one or more held rows",
        description=(
            "Applies the same actions as the wizard held-row workspace. "
            "Pass ``record_ids`` for per-row actions; omit for bulk actions. "
            "Set ``auto_retry=true`` to queue repair after accept/clear."
        ),
        request=resolve_request,
        responses={
            200: OpenApiResponse(description="Action outcome JSON"),
            400: OpenApiResponse(description="Invalid action or record ids"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    @action(detail=True, methods=["post"], url_path="quarantine/resolve")
    @idempotent_post
    @safe_500
    def quarantine_resolve(self, request, pk=None):
        denied = _require_quarantine_write_access(request)
        if denied is not None:
            return denied
        bundle = self.get_object()
        payload = _resolve_payload(request)
        outcome, code = _apply_resolve(bundle=bundle, user=request.user, payload=payload)
        return Response(outcome, status=code)

    return quarantine_resolve


def quarantine_export_action_factory():
    """Register ``GET /quarantine/export/`` on ``BundleViewSet``."""

    @extend_schema(
        tags=["Migration Cloud"],
        summary="Export held rows as CSV",
        description=(
            "Downloads held rows for offline triage. Pass ``?scope=all`` to "
            "include resolved rows."
        ),
        responses={
            200: OpenApiResponse(description="text/csv attachment"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    @action(detail=True, methods=["get"], url_path="quarantine/export")
    def quarantine_export(self, request, pk=None):
        denied = _require_quarantine_read_access(request)
        if denied is not None:
            return denied
        from apps.migration_cloud.quarantine_resolution import export_quarantine_csv

        bundle = self.get_object()
        pending_only = (request.query_params.get("scope") or "").strip().lower() != "all"
        csv_text = export_quarantine_csv(bundle, pending_only=pending_only)
        response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        suffix = "pending" if pending_only else "all"
        response["Content-Disposition"] = (
            f'attachment; filename="bundle-{bundle.pk}-held-{suffix}.csv"'
        )
        return response

    return quarantine_export


def ai_explain_action_factory():
    """Register ``POST /ai-explain/`` on ``BundleViewSet``."""

    explain_request = inline_serializer(
        name="QuarantineAIExplainRequest",
        fields={
            "row": serializers.JSONField(help_text="Source row dict from held record"),
            "reason": serializers.CharField(help_text="Raw quarantine reason string"),
        },
    )

    @extend_schema(
        tags=["Migration Cloud"],
        summary="Explain a held row in plain language (AI)",
        description=(
            "Returns a plain-language explanation when AI is enabled for the "
            "tenant. Falls back with ``ai_available=false`` when disabled."
        ),
        request=explain_request,
        responses={
            200: OpenApiResponse(description="Explanation JSON"),
            400: OpenApiResponse(description="Missing reason or invalid row"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Bundle not found"),
        },
    )
    @action(detail=True, methods=["post"], url_path="ai-explain")
    @idempotent_post
    @safe_500
    def ai_explain_row(self, request, pk=None):
        denied = _require_quarantine_read_access(request)
        if denied is not None:
            return denied
        from apps.migration_cloud.ai_bridge import explain_quarantine_row

        bundle = self.get_object()
        payload = _resolve_payload(request)
        row = payload.get("row") or {}
        reason = (payload.get("reason") or "").strip()
        if not isinstance(row, (dict, list)):
            return Response({"error": "row must be an object or array"}, status=400)
        if not reason:
            return Response({"error": "reason required"}, status=400)

        explanation = explain_quarantine_row(school=bundle.school, row=row, reason=reason)
        return Response(
            {
                "bundle_id": bundle.pk,
                "explanation": explanation.answer if explanation else None,
                "confidence": explanation.confidence if explanation else 0.0,
                "ai_available": explanation is not None,
            }
        )

    return ai_explain_row
