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
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.migration_cloud.models import (
    MigrationCloudWebhookDelivery,
    MigrationCloudWebhookSubscription,
    WebhookDeliveryStatus,
)

logger = logging.getLogger(__name__)


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
        qs = MigrationCloudWebhookSubscription.objects.all()
        try:
            if tenant_filter:
                qs = qs.filter(tenant_id=int(tenant_filter))
        except (TypeError, ValueError):
            pass
        rows = [_row_for_table(r) for r in qs[:500]]
        context = {
            "page_title": "Migration Cloud — webhook subscriptions",
            "shell": kwargs.get("shell", "super"),
            "rows": rows,
            "filter_tenant_id": tenant_filter or "",
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
        page_no = int(request.GET.get("page") or 1)
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
