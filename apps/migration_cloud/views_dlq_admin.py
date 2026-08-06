"""v4.00.80 Wave 12 T4 — Staff-only operator surface for WebhookDeadLetter replay.

Companion to ``apps.integrations_marketplace.webhook_dead_letter`` (the
Wave 11 model + helpers). When the outbound webhook dispatcher exhausts
its retry budget (1m/5m/30m/2h/12h/24h then ``exhausted``), the failed
delivery is parked as a ``WebhookDeadLetter`` row for operator review.

This module exposes two staff-gated views:

  * :class:`WebhookDeadLetterListView` — GET ``/super/migration/operator/dlq/``
    returns JSON of pending DLQ rows for triage (never includes the
    payload body bytes; only ``payload_bytes_length``). Cross-tenant
    safety: ``tenant_schema`` is omitted from the response shape.

  * :class:`WebhookDeadLetterReplayView` — POST
    ``/super/migration/operator/dlq/<int:dlq_id>/replay/`` decodes the
    payload, attempts a best-effort live outbound replay against the
    original subscription (if it can be resolved from ``tenant_schema``
    + ``event_type``), and flips the DLQ row to ``status=replayed``.

Failure taxonomy (502 reasons):
  * ``target_endpoint_unreachable`` — network/connection layer failed
  * ``target_returned_5xx`` — outbound POST got HTTP 5xx
  * ``target_returned_4xx`` — outbound POST got HTTP 4xx
  * ``internal_error`` — uncaught exception during replay

Defense-in-depth: even though the endpoints are staff-gated, the
response JSON NEVER includes ``payload_b64`` content or
``tenant_schema``.

Design notes:
  * Subscription resolution: a DLQ row stores ``tenant_schema`` (e.g.
    "tenant_acme") but not a subscription_id, so we look up the active
    subscription via the ``School.tenant`` relation and match on
    ``event_classes`` glob. If no subscription is found OR it is
    inactive, we still ``mark_replayed`` (the operator's intent is to
    acknowledge the row); response includes ``note: "marked_no_live_target"``
    and returns 200 instead of 202.
  * The replay endpoint NEVER amends the FSM of the original
    ``MigrationCloudWebhookDelivery`` — that row remains ``exhausted``
    in the delivery log as a permanent record. The DLQ replay surface is
    additive.
  * GET on the replay endpoint returns 405 (Django CBV default).
"""

from __future__ import annotations

import logging

from apps.schools.control_plane import require_control_plane_access
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)

# Maximum DLQ rows surfaced by the list endpoint in one call (operator
# triage view; pagination is not required for the in-flight backlog).
LIST_PAGE_LIMIT = 100


def _dlq_row_for_listing(row) -> dict:
    """Project a ``WebhookDeadLetter`` row for the operator list JSON.

    Defense-in-depth: NEVER emits ``payload_b64`` content (only the
    bytes-length) and NEVER emits ``tenant_schema`` (the cross-tenant
    marker stays server-side even though the surface is staff-gated).
    """
    try:
        import base64
        payload_bytes_length = len(
            base64.b64decode((row.payload_b64 or "").encode("ascii"))
        )
    except Exception:  # noqa: BLE001 — defensive; length on a corrupt row is 0
        payload_bytes_length = 0
    return {
        "id": row.pk,
        "provider": row.provider,
        "event_type": row.event_type,
        "attempt_count": row.attempt_count,
        "last_error_reason": row.last_error_reason or "",
        "status": row.status,
        "payload_bytes_length": payload_bytes_length,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


# rbac-allow: super-staff-webhook-dlq-list
@method_decorator(require_control_plane_access, name="dispatch")
class WebhookDeadLetterListView(View):
    """GET — list up to 100 pending DLQ rows for operator triage.

    Default response shape is JSON. When ``?format=html`` is set, renders
    the human-readable operator triage template
    ``migration_cloud/operator/dlq_list.html`` (v4.00.87 Wave 19 T5).
    The JSON shape is unchanged for back-compat with v4.00.80 Wave 12 T4
    callers.
    """

    template_name = "migration_cloud/operator/dlq_list.html"

    def get(self, request, *args, **kwargs):
        from apps.integrations_marketplace import webhook_dead_letter as _dlq
        status_filter = (request.GET.get("status") or "pending").strip()
        # Only "pending" or "replayed" / "expired" / "discarded" are valid;
        # default to "pending" (operator backlog) on any unknown value.
        if status_filter not in ("pending", "replayed", "expired", "discarded"):
            status_filter = "pending"
        rows = _dlq.list_due(status=status_filter, limit=LIST_PAGE_LIMIT)
        serializable = [_dlq_row_for_listing(r) for r in rows]
        logger.info(
            "migration_cloud_operator_dlq_list user_id=%s status=%s count=%s",
            getattr(request.user, "pk", None), status_filter, len(rows),
        )

        # v4.00.87 Wave 19 T5 — human-readable operator triage UI.
        # The JSON shape MUST stay default to preserve v4.00.80 Wave 12 T4
        # callers (smoke + tests + any external runbook tooling).
        if (request.GET.get("format") or "").strip() == "html":
            context = {
                "page_title": "Webhook dead letter queue",
                "shell": kwargs.get("shell", "super"),
                "rows": serializable,
                "status_filter": status_filter,
                "row_count": len(serializable),
                "limit": LIST_PAGE_LIMIT,
            }
            return render(request, self.template_name, context)

        body = {
            "rows": serializable,
            "count": len(rows),
            "status_filter": status_filter,
            "limit": LIST_PAGE_LIMIT,
        }
        return JsonResponse(body, status=200)


def _attempt_outbound_replay(row, payload_bytes: bytes) -> tuple[bool, str, int | None]:
    """Best-effort outbound POST attempt.

    Looks up an active subscription via the DLQ row's ``tenant_schema``
    marker (matching School.tenant.schema_name) AND the event_type glob.
    If no subscription can be resolved, returns ``(False, "no_live_target", None)``
    — caller treats this as a soft success (mark replayed + 200).

    On a live attempt:
      * 2xx -> ``(True, "ok", status_code)``
      * 5xx -> ``(False, "target_returned_5xx", status_code)``
      * 4xx -> ``(False, "target_returned_4xx", status_code)``
      * network err -> ``(False, "target_endpoint_unreachable", None)``
    """
    try:
        from apps.migration_cloud.models import (
            MigrationCloudWebhookSubscription,
        )
        # tenant-isolation-allow: operator-shell-staff-dlq-replay-resolves-original-subscription
        candidates = MigrationCloudWebhookSubscription.objects.filter(
            active=True,
        )
        target = None
        # Filter by tenant_schema if present (defensive — a missing marker
        # falls back to provider+event_type matching only).
        tenant_schema = (row.tenant_schema or "").strip()
        for sub in candidates.iterator():
            tenant_obj = getattr(sub, "tenant", None)
            sub_schema = getattr(tenant_obj, "schema_name", "") or ""
            if tenant_schema and sub_schema != tenant_schema:
                continue
            # Match on event_types list if non-empty; empty list = all events.
            ev_types = list(getattr(sub, "event_types", None) or [])
            if ev_types and row.event_type not in ev_types:
                continue
            target = sub
            break
        if target is None:
            return False, "no_live_target", None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_operator_dlq_replay_subscription_lookup_failed "
            "dlq_id=%s exc=%s",
            row.pk, type(exc).__name__,
        )
        return False, "no_live_target", None

    # Live POST. Re-uses the dispatcher's signing + header logic so
    # receivers can verify identically to a first-attempt delivery.
    try:
        from apps.migration_cloud.api.webhook_dispatch import (
            _build_outbound_headers,
            _emit_legacy_headers_enabled,
            _sign,
        )
        import time
        secret_bytes = bytes(target.secret_ciphertext or b"")
        signature = _sign(secret_bytes, payload_bytes) if secret_bytes else ""
        timestamp = str(int(time.time()))
        headers = _build_outbound_headers(
            signature=signature,
            event_type=row.event_type,
            delivery_id=f"dlq-replay-{row.pk}",
            timestamp=timestamp,
            emit_legacy=_emit_legacy_headers_enabled(),
        )
        try:
            import requests  # type: ignore
            response = requests.post(
                target.url, data=payload_bytes, headers=headers, timeout=15,
            )
            status_code = int(response.status_code)
        except ImportError:
            # urllib fallback — keeps the replay path importable in lean envs.
            from urllib import error as _urlerr
            from urllib import request as _urlreq
            req = _urlreq.Request(
                target.url, data=payload_bytes, headers=headers, method="POST",
            )
            try:
                with _urlreq.urlopen(req, timeout=15) as resp:
                    status_code = int(resp.status)
            except _urlerr.HTTPError as http_err:
                status_code = int(http_err.code)
    except Exception as exc:  # noqa: BLE001 — any network err is "unreachable"
        logger.info(
            "migration_cloud_operator_dlq_replay_unreachable "
            "dlq_id=%s exc=%s",
            row.pk, type(exc).__name__,
        )
        return False, "target_endpoint_unreachable", None

    if 200 <= status_code < 300:
        return True, "ok", status_code
    if 500 <= status_code < 600:  # magic-number-allow: http-status-code-range
        return False, "target_returned_5xx", status_code
    if 400 <= status_code < 500:
        return False, "target_returned_4xx", status_code
    # 1xx/3xx — treat as unreachable (we POST'd but got nothing useful).
    return False, "target_endpoint_unreachable", status_code


# rbac-allow: super-staff-webhook-dlq-manual-replay
@method_decorator(require_control_plane_access, name="dispatch")
class WebhookDeadLetterReplayView(View):
    """POST — replay one parked WebhookDeadLetter row.

    Lookup outcomes:
      * row missing -> 404 ``{"error": "not_found", "dlq_id": id}``
      * row exists but not pending -> 409 ``{"error": "not_pending",
        "dlq_id": id, "status": <current>}``

    Replay outcomes (row pending):
      * live target hit + 2xx -> 200 ``{"replayed": true, "dlq_id": id,
        "http_status": <code>}`` (DLQ row flipped to ``replayed``)
      * live target failed -> 502 ``{"replayed": false, "dlq_id": id,
        "reason": "<taxonomy>", "http_status": <code or null>}``
        (DLQ row stays ``pending`` for another attempt)
      * no live target resolvable -> 200 ``{"replayed": true,
        "dlq_id": id, "note": "marked_no_live_target"}`` (operator
        acknowledged; DLQ row flipped to ``replayed``)
      * uncaught error -> 502 ``{"replayed": false, "dlq_id": id,
        "reason": "internal_error"}`` (DLQ row stays ``pending``)
    """

    def post(self, request, *args, **kwargs):
        dlq_id = kwargs.get("dlq_id")
        try:
            from apps.integrations_marketplace.models import WebhookDeadLetter
            from apps.integrations_marketplace import webhook_dead_letter as _dlq
        except Exception:  # noqa: BLE001
            logger.exception(
                "migration_cloud_operator_dlq_replay_import_failed dlq_id=%s",
                dlq_id,
            )
            return JsonResponse(
                {"replayed": False, "dlq_id": dlq_id, "reason": "internal_error"},
                status=502,
            )

        # tenant-isolation-allow: operator-shell-staff-cross-tenant-dlq-administration
        row = WebhookDeadLetter.objects.filter(pk=dlq_id).first()
        if row is None:
            return JsonResponse(
                {"error": "not_found", "dlq_id": dlq_id},
                status=404,
            )
        if row.status != "pending":
            return JsonResponse(
                {
                    "error": "not_pending",
                    "dlq_id": dlq_id,
                    "status": row.status,
                },
                status=409,
            )

        # Decode payload (Wave 11 helper handles the b64 round-trip).
        try:
            payload_bytes = _dlq.decode_payload(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "migration_cloud_operator_dlq_replay_decode_failed "
                "dlq_id=%s exc=%s",
                dlq_id, type(exc).__name__,
            )
            return JsonResponse(
                {
                    "replayed": False,
                    "dlq_id": dlq_id,
                    "reason": "internal_error",
                },
                status=502,
            )

        # Best-effort live attempt. Wrap in try/except so an uncaught
        # exception falls into the ``internal_error`` taxonomy without
        # ever flipping the DLQ row (it stays pending).
        try:
            succeeded, reason, http_status = _attempt_outbound_replay(
                row, payload_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "migration_cloud_operator_dlq_replay_uncaught dlq_id=%s exc=%s",
                dlq_id, type(exc).__name__,
            )
            return JsonResponse(
                {
                    "replayed": False,
                    "dlq_id": dlq_id,
                    "reason": "internal_error",
                },
                status=502,
            )

        if succeeded:
            flipped = _dlq.mark_replayed(dlq_id)
            logger.info(
                "migration_cloud_operator_dlq_replay_ok "
                "user_id=%s dlq_id=%s http_status=%s mark_replayed=%s",
                getattr(request.user, "pk", None), dlq_id, http_status, flipped,
            )
            return JsonResponse(
                {
                    "replayed": True,
                    "dlq_id": dlq_id,
                    "http_status": http_status,
                },
                status=200,
            )

        if reason == "no_live_target":
            # Soft-success: operator acknowledged the row; no subscription
            # exists to attempt against (subscription may have been
            # deactivated since the original delivery exhausted). Flip
            # DLQ row to replayed so it doesn't keep showing up in the
            # triage list — but return 200 with a note so the caller
            # knows we didn't actually push bytes anywhere.
            flipped = _dlq.mark_replayed(dlq_id)
            logger.info(
                "migration_cloud_operator_dlq_replay_no_target "
                "user_id=%s dlq_id=%s mark_replayed=%s",
                getattr(request.user, "pk", None), dlq_id, flipped,
            )
            return JsonResponse(
                {
                    "replayed": True,
                    "dlq_id": dlq_id,
                    "note": "marked_no_live_target",
                },
                status=200,
            )

        # Real failure — row stays pending for another operator attempt.
        logger.info(
            "migration_cloud_operator_dlq_replay_failed "
            "user_id=%s dlq_id=%s reason=%s http_status=%s",
            getattr(request.user, "pk", None), dlq_id, reason, http_status,
        )
        return JsonResponse(
            {
                "replayed": False,
                "dlq_id": dlq_id,
                "reason": reason,
                "http_status": http_status,
            },
            status=502,
        )
