"""Operator-shell screens for Migration Cloud outbound webhooks.

Staff-only Django views (NOT DRF) for the partner-success team to
register, list, deactivate, retry, and audit outbound webhook
subscriptions and their delivery log.

Secret material is rendered on the create response page ONCE — never
again. The list view returns ``whsec_...XXXX`` previews only.

Mirrors the discipline of :mod:`views_token_admin` (the sibling
operator surface for scoped tokens).
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.views import View

from apps.migration_cloud.models import (
    MigrationCloudWebhookDelivery,
    MigrationCloudWebhookSubscription,
    WebhookDeliveryStatus,
)
# v3.38.0 Agent 5 — append-only audit log.
from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent as _AuditEvent,
)

logger = logging.getLogger(__name__)


def _safe_audit(tenant_slug: str, event_type: str, **kwargs) -> None:
    """Best-effort audit emit; never break the view path."""
    try:
        _AuditEvent.objects.record(tenant_slug or "", event_type, **kwargs)
    except Exception as exc:  # broad-by-design
        logger.error(
            "migration_cloud.audit: emit failed event_type=%s err=%s",
            event_type, type(exc).__name__,
        )


def _slug_for_tenant_id(tenant_id) -> str:
    """Best-effort tenant slug lookup; returns empty string on failure."""
    if tenant_id in (None, ""):
        return ""
    try:
        from apps.schools.models import School
        # tenant-isolation-allow: audit-slug-lookup-cross-tenant-staff-view
        row = School.objects.filter(pk=tenant_id).only("slug").first()
        return getattr(row, "slug", "") or ""
    except Exception:  # broad-by-design — audit must never fail caller
        return ""


def _generate_webhook_secret() -> tuple[str, bytes, str]:
    """Return (plaintext, ciphertext_bytes, sha256_hex) for a fresh secret.

    Mirrors :func:`apps.migration_cloud.api.webhooks._generate_secret`
    so the operator-side mint produces identical material; we duplicate
    the helper (rather than import the private one) because the API
    side may evolve the storage shape (crypto-pending marker) and we
    want the operator surface to follow naturally.
    """
    plaintext = "whsec_" + secrets.token_urlsafe(32)
    ciphertext = plaintext.encode("utf-8")
    digest = hashlib.sha256(ciphertext).hexdigest()
    return plaintext, ciphertext, digest


def _row_for_table(row: MigrationCloudWebhookSubscription) -> dict:
    """Mask a subscription row for the list template — never includes secret."""
    return {
        "id": row.pk,
        "tenant_id": row.tenant_id,
        "url": row.url,
        "event_types": list(row.event_types or []),
        "active": row.active,
        "last_delivery_status": row.last_delivery_status,
        "preview": f"whsec_...{row.secret_hash[-4:]}" if row.secret_hash else "",
        "created_at": row.created_at,
    }


def _delivery_row(row: MigrationCloudWebhookDelivery) -> dict:
    """Mask a delivery row — payload + signature truncated to summary."""
    return {
        "id": row.pk,
        "subscription_id": row.subscription_id,
        "event_type": row.event_type,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "last_response_code": row.last_response_code,
        "next_retry_at": row.next_retry_at,
        "deferred_until": row.deferred_until,
        "deferred_reason": row.deferred_reason,
        "created_at": row.created_at,
        "delivered_at": row.delivered_at,
    }


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudWebhookListView(View):
    """GET — list all webhook subscriptions (staff cross-tenant view)."""

    template_name = "migration_cloud/operator/webhook_list.html"

    def get(self, request, *args, **kwargs):
        tenant_filter = request.GET.get("tenant_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        qs = MigrationCloudWebhookSubscription.objects.all().order_by("-created_at")
        try:
            if tenant_filter:
                qs = qs.filter(tenant_id=int(tenant_filter))
        except (TypeError, ValueError):
            pass
        paginator = Paginator(qs.order_by("-created_at"), 25)
        page_obj = paginator.get_page(request.GET.get("page") or 1)
        extra = request.GET.copy()
        extra.pop("page", None)
        rows = [_row_for_table(r) for r in page_obj.object_list]
        # v3.35.0 — webhook header family migration banner state.
        from apps.migration_cloud.api.webhook_dispatch import (
            _emit_legacy_headers_enabled,
            _legacy_header_deprecation_cutover_date,
            _legacy_header_window_active,
        )
        deadline = _legacy_header_deprecation_cutover_date().isoformat()
        emit_legacy = _emit_legacy_headers_enabled()
        context = {
            "page_title": "Migration Cloud — webhook subscriptions",
            "shell": kwargs.get("shell", "super"),
            "rows": rows,
            "page_obj": page_obj,
            "pagination_extra_query": extra.urlencode(),
            "filter_tenant_id": tenant_filter or "",
            "header_migration_window_active": _legacy_header_window_active(),
            "header_migration_deadline": deadline,
            "emit_legacy_headers": emit_legacy,
        }
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudWebhookSubscribeView(View):
    """GET form + POST creates subscription; secret shown ONCE."""

    template_name = "migration_cloud/operator/webhook_subscribe.html"
    result_template = "migration_cloud/operator/webhook_subscribe.html"

    def get(self, request, *args, **kwargs):
        context = {
            "page_title": "Subscribe to Migration Cloud webhooks",
            "shell": kwargs.get("shell", "super"),
            "result": None,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        url = (request.POST.get("url") or "").strip()
        tenant_id_raw = (request.POST.get("tenant_id") or "").strip()
        event_types_raw = (request.POST.get("event_types") or "").strip()
        if not url.lower().startswith("https://"):
            messages.error(request, "URL must start with https://")
            return HttpResponseRedirect(request.path)
        try:
            tenant_id = int(tenant_id_raw)
        except (TypeError, ValueError):
            messages.error(request, "tenant_id must be an integer.")
            return HttpResponseRedirect(request.path)
        event_types = [s.strip() for s in event_types_raw.split(",") if s.strip()]

        plaintext, ciphertext, digest = _generate_webhook_secret()
        row = MigrationCloudWebhookSubscription.objects.create(
            tenant_id=tenant_id,
            url=url,
            event_types=event_types,
            secret_hash=digest,
            secret_ciphertext=ciphertext,
            created_by=request.user,
        )
        logger.info(
            "migration_cloud_operator_webhook_subscribed user_id=%s sub_id=%s "
            "tenant_id=%s url_host=%s",
            request.user.pk, row.pk, tenant_id, url.split("/", 3)[2],
        )
        _safe_audit(
            _slug_for_tenant_id(tenant_id),
            "webhook.subscription.created",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={
                "url_host": url.split("/", 3)[2][:128],
                "event_types_count": len(event_types),
            },
        )
        context = {
            "page_title": "Webhook subscription created",
            "shell": kwargs.get("shell", "super"),
            "result": {
                "row": _row_for_table(row),
                "plaintext": plaintext,
            },
        }
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudWebhookDeliveryLogView(View):
    """GET — paginated delivery log for one subscription (or all if no id)."""

    template_name = "migration_cloud/operator/webhook_delivery_log.html"

    def get(self, request, *args, **kwargs):
        sub_id_raw = request.GET.get("subscription_id") or kwargs.get("subscription_id")
        try:
            page_no = int(request.GET.get("page") or 1)
        except (TypeError, ValueError):
            page_no = 1
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        qs = MigrationCloudWebhookDelivery.objects.all().order_by("-created_at")
        sub_id = None
        try:
            if sub_id_raw:
                sub_id = int(sub_id_raw)
                qs = qs.filter(subscription_id=sub_id)
        except (TypeError, ValueError):
            sub_id = None
        paginator = Paginator(qs, 50)
        page = paginator.get_page(page_no)
        rows = [_delivery_row(r) for r in page.object_list]
        context = {
            "page_title": "Webhook delivery log",
            "shell": kwargs.get("shell", "super"),
            "rows": rows,
            "page_obj": page,
            "subscription_id": sub_id,
        }
        return render(request, self.template_name, context)


# ─── v3.37.0 — Per-subscription audit + manual replay (Agent 5) ──────────
#
# Audit and replay surfaces close the operator support loop for
# subscribers who report "we never got delivery X". The audit view shows
# the last 200 deliveries for one subscription with full FSM context but
# ZERO sensitive material (no signatures, no payload bodies — both are
# zero-knowledge for the operator UI). The replay view creates a fresh
# delivery row that points at the original via ``replay_of`` and re-runs
# the dispatcher; the immediate next ``deliver_due`` tick attempts it.
#
# Both views are staff-only and audit-logged. Neither logs payload bytes,
# signature material, or HMAC secret material.


def _audit_row(row: MigrationCloudWebhookDelivery) -> dict:
    """Mask a delivery row for the AUDIT view.

    Differs from :func:`_delivery_row` (used by the wider delivery log
    that hides per-tenant filtering) by surfacing extra forensics fields
    the support team needs WITHOUT ever exposing signature bytes or
    payload contents:

      * ``signature_present`` — boolean ONLY (never the bytes).
      * ``payload_bytes_length`` — integer ONLY (never the bytes).
      * ``replay_of_id`` — points to the predecessor for replay chains.
    """
    raw_payload = row.payload_json
    # JSONField default is ``dict``; legacy NULL rows would short-circuit.
    if raw_payload:
        try:
            import json as _json  # local import keeps file-level deps minimal
            payload_length = len(
                _json.dumps(
                    raw_payload, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
            )
        except (TypeError, ValueError):
            payload_length = 0
    else:
        payload_length = 0
    return {
        "id": row.pk,
        "subscription_id": row.subscription_id,
        "event_type": row.event_type,
        "status": row.status,
        "http_status_code": row.last_response_code,
        "attempt_count": row.attempt_count,
        "last_attempted_at": row.delivered_at or row.next_retry_at,
        "signature_present": bool(row.request_signature),
        "payload_bytes_length": payload_length,
        "created_at": row.created_at,
        "delivered_at": row.delivered_at,
        "replay_of_id": getattr(row, "replay_of_id", None),
        "replayed_by_id": getattr(row, "replayed_by_id", None),
        "replayed_at": getattr(row, "replayed_at", None),
        "deferred_reason": row.deferred_reason,
    }


# rbac-allow: super-staff-webhook-audit-view-deliveries
@method_decorator(staff_member_required, name="dispatch")
class WebhookSubscriptionAuditView(View):
    """GET — paginated last-200 delivery audit for one subscription.

    Filters: ``?status=<s>`` exact-match; ``?date_from=YYYY-MM-DD`` and
    ``?date_to=YYYY-MM-DD`` (inclusive on ``created_at`` date).

    The template renders summary columns only. Signature bytes and
    payload body content are NEVER serialized into the response.
    """

    template_name = "migration_cloud/operator/webhook_audit.html"
    AUDIT_WINDOW_LIMIT = 200
    PAGE_SIZE = 50

    def get(self, request, *args, **kwargs):
        sub_id = kwargs.get("sub_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        subscription = get_object_or_404(
            MigrationCloudWebhookSubscription, pk=sub_id,
        )
        status_filter = (request.GET.get("status") or "").strip()
        date_from_raw = (request.GET.get("date_from") or "").strip()
        date_to_raw = (request.GET.get("date_to") or "").strip()
        page_no_raw = request.GET.get("page") or "1"
        try:
            page_no = int(page_no_raw)
        except (TypeError, ValueError):
            page_no = 1

        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        qs = MigrationCloudWebhookDelivery.objects.filter(
            subscription_id=subscription.pk,
        ).order_by("-created_at")

        valid_statuses = {c.value for c in WebhookDeliveryStatus}
        if status_filter and status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        date_from = parse_date(date_from_raw) if date_from_raw else None
        date_to = parse_date(date_to_raw) if date_to_raw else None
        if date_from is not None:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__date__lte=date_to)

        # Cap at the audit window — the support workflow only needs the
        # last 200 rows. Beyond that, queries belong in the wider log
        # view or in offline analytics.
        qs = qs[: self.AUDIT_WINDOW_LIMIT]
        rows_materialized = list(qs)
        paginator = Paginator(rows_materialized, self.PAGE_SIZE)
        page = paginator.get_page(page_no)
        rows = [_audit_row(r) for r in page.object_list]

        logger.info(
            "migration_cloud_operator_webhook_audit_view "
            "user_id=%s sub_id=%s status_filter=%s row_count=%s",
            request.user.pk, subscription.pk, status_filter or "*", len(rows),
        )

        context = {
            "page_title": f"Webhook audit — subscription #{subscription.pk}",
            "shell": kwargs.get("shell", "super"),
            "subscription": {
                "id": subscription.pk,
                "tenant_id": subscription.tenant_id,
                "url": subscription.url,
                "active": subscription.active,
            },
            "rows": rows,
            "page_obj": page,
            "status_filter": status_filter,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "valid_statuses": sorted(valid_statuses),
        }
        return render(request, self.template_name, context)


# rbac-allow: super-staff-webhook-manual-replay
@method_decorator(staff_member_required, name="dispatch")
class WebhookDeliveryReplayView(View):
    """POST — manually replay a webhook delivery.

    Creates a NEW :class:`MigrationCloudWebhookDelivery` row with:

      * ``replay_of`` pointing at the original delivery
      * ``replayed_by`` = the staff user who clicked
      * ``replayed_at`` = wall-clock now
      * Fresh FSM: ``status=pending``, ``attempt_count=0``,
        ``next_retry_at=now`` (immediate Celery dispatch eligibility).

    The new row shares the original ``event_type``, ``subscription`` and
    ``payload_json``. We re-compute the signature against the
    subscription's current secret (so post-rotation replays sign with the
    fresh key — receivers verify with what they have NOW).

    Returns ``409 Conflict`` if the original row's payload is empty /
    missing (we refuse to replay an empty payload — that would push
    meaningless traffic).
    """

    def post(self, request, *args, **kwargs):
        delivery_id = kwargs.get("delivery_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        original = get_object_or_404(
            MigrationCloudWebhookDelivery, pk=delivery_id,
        )
        if not original.payload_json:
            logger.warning(
                "migration_cloud_operator_webhook_replay_refused_empty "
                "user_id=%s delivery_id=%s",
                request.user.pk, original.pk,
            )
            return HttpResponse(
                "Original delivery payload is empty — cannot replay.",
                status=409,
            )

        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        subscription = MigrationCloudWebhookSubscription.objects.filter(
            pk=original.subscription_id,
        ).first()
        if subscription is None:
            logger.warning(
                "migration_cloud_operator_webhook_replay_refused_no_sub "
                "user_id=%s delivery_id=%s",
                request.user.pk, original.pk,
            )
            return HttpResponse(
                "Original subscription no longer exists — cannot replay.",
                status=409,
            )

        # Re-sign against the CURRENT secret. Receivers verify with the
        # secret they have NOW; signing with stale material would force
        # them to roll back their key book.
        request_signature = ""
        try:
            from apps.migration_cloud.api.webhook_dispatch import (
                _canonical_payload_bytes,
                _sign,
            )
            secret_bytes = bytes(subscription.secret_ciphertext or b"")
            if secret_bytes:
                request_signature = _sign(
                    secret_bytes,
                    _canonical_payload_bytes(original.payload_json),
                )
        except ImportError:
            # Dispatcher module unavailable in this env — leave unsigned.
            # Receiver will reject; operator gets a clear failure mode.
            request_signature = ""

        now = timezone.now()
        replay = MigrationCloudWebhookDelivery.objects.create(
            subscription=subscription,
            event_type=original.event_type,
            payload_json=original.payload_json,
            request_signature=request_signature,
            attempt_count=0,
            status=WebhookDeliveryStatus.PENDING,
            next_retry_at=now,
            replay_of=original,
            replayed_by=request.user,
            replayed_at=now,
            # Operator replay does NOT inherit the original idempotency
            # key — it's a deliberate duplicate, not a producer-side
            # double-fire. Empty key disables the 24h collision guard
            # for this row.
            idempotency_key="",
        )
        logger.info(
            "migration_cloud_operator_webhook_replay_created "
            "user_id=%s original_delivery_id=%s replay_delivery_id=%s "
            "sub_id=%s event=%s",
            request.user.pk, original.pk, replay.pk,
            subscription.pk, replay.event_type,
        )
        _safe_audit(
            _slug_for_tenant_id(subscription.tenant_id),
            "webhook.delivery.replay",
            actor=request.user,
            subject=str(replay.pk),
            payload_summary={
                "original_delivery_id": original.pk,
                "subscription_id": subscription.pk,
                "event_type": replay.event_type[:64],
                "signed": bool(request_signature),
            },
        )

        # Trigger immediate Celery dispatch — best-effort, non-blocking.
        # If Celery isn't configured (tests), the Celery beat tick will
        # pick the row up on next sweep.
        try:
            from apps.migration_cloud.api.webhook_dispatch import (
                deliver_due_task,
            )
            deliver_due_task.delay(batch_size=10)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — broker unavailable in tests
            logger.info(
                "migration_cloud_operator_webhook_replay_dispatch_deferred "
                "replay_delivery_id=%s",
                replay.pk,
            )

        if request.GET.get("format") == "json" or request.headers.get(
            "Accept", ""
        ).startswith("application/json"):
            return JsonResponse(
                {
                    "replay_delivery_id": replay.pk,
                    "replay_of_id": original.pk,
                    "status": replay.status,
                },
                status=201,
            )

        messages.success(
            request,
            f"Replay delivery #{replay.pk} created (original #{original.pk}).",
        )
        shell = kwargs.get("shell", "super")
        namespace = (
            "migration_cloud_portal" if shell == "portal" else "migration_cloud_super"
        )
        target = reverse(
            f"{namespace}:operator_webhook_audit",
            kwargs={"sub_id": subscription.pk},
        )
        return HttpResponseRedirect(target)


# rbac-allow: super-staff-webhook-subscription-deactivate
@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudWebhookDeactivateView(View):
    """POST — deactivate (soft-delete) a webhook subscription.

    Mirrors the API's ``DELETE /api/v1/webhooks/<id>/`` behavior:
    flips ``active=False`` rather than removing the row, so delivery
    history remains queryable for the support workflow. Idempotent —
    already-inactive subscriptions are a no-op (still emits an audit
    event so the operator action is traceable).
    """

    def post(self, request, *args, **kwargs):
        sub_id = kwargs.get("sub_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        row = get_object_or_404(MigrationCloudWebhookSubscription, pk=sub_id)
        was_active = bool(row.active)
        if was_active:
            row.active = False
            row.updated_at = timezone.now()
            row.save(update_fields=["active", "updated_at"])
        logger.info(
            "migration_cloud_operator_webhook_deactivated user_id=%s sub_id=%s "
            "was_active=%s",
            request.user.pk, row.pk, was_active,
        )
        # v3.39.0 Agent 2 — wire reserved ``webhook.subscription.deleted``
        # event. The platform deactivates rather than hard-deletes, so
        # the "deleted" name covers both semantics (deactivated row is
        # effectively deleted from the dispatcher's POV).
        _safe_audit(
            _slug_for_tenant_id(row.tenant_id),
            "webhook.subscription.deleted",
            actor=request.user,
            subject=str(row.pk),
            payload_summary={
                "action": "deactivated",
                "subscription_id_hash_prefix": hashlib.sha256(
                    str(row.pk).encode("utf-8")
                ).hexdigest()[:12],
                "was_active": was_active,
            },
        )
        messages.success(request, f"Subscription #{row.pk} deactivated.")
        shell = kwargs.get("shell", "super")
        namespace = (
            "migration_cloud_portal" if shell == "portal" else "migration_cloud_super"
        )
        return HttpResponseRedirect(reverse(f"{namespace}:operator_webhook_list"))


@method_decorator(staff_member_required, name="dispatch")
class MigrationCloudWebhookRetryView(View):
    """POST — manually re-enqueue a failed/exhausted delivery."""

    def post(self, request, *args, **kwargs):
        delivery_id = kwargs.get("delivery_id")
        # tenant-isolation-allow: operator-shell-staff-cross-tenant-webhook-administration
        row = get_object_or_404(MigrationCloudWebhookDelivery, pk=delivery_id)
        row.status = WebhookDeliveryStatus.PENDING
        row.next_retry_at = timezone.now()
        row.deferred_until = None
        row.deferred_reason = ""
        row.save(update_fields=[
            "status", "next_retry_at", "deferred_until", "deferred_reason",
        ])
        logger.info(
            "migration_cloud_operator_webhook_retry user_id=%s delivery_id=%s",
            request.user.pk, row.pk,
        )
        messages.success(request, f"Delivery #{row.pk} re-enqueued.")
        shell = kwargs.get("shell", "super")
        namespace = (
            "migration_cloud_portal" if shell == "portal" else "migration_cloud_super"
        )
        target = reverse(f"{namespace}:operator_webhook_delivery_log")
        return HttpResponseRedirect(f"{target}?subscription_id={row.subscription_id}")
