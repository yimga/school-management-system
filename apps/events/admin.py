"""Admin for the domain-event outbox and webhook runtime.

Registered on ``platform_admin_site`` (the manager host), NOT Django's default
``admin.site``. The default site is mounted on NO urlconf in this project — see
``config/admin.py``, which builds ``tenant_admin_site`` and ``platform_admin_site``
and mounts only those — so ``@admin.register(Model)`` without a ``site=`` argument
produced three registrations an operator could never open. These rows are
platform-scoped (cross-tenant outbox / subscriptions / deliveries carrying a bare
``school_id`` UUID rather than a School FK), so the platform site is their home,
exactly as in ``apps/automation/admin.py``. Sealed by
``scripts/scan_admin_registered_on_unmounted_site.py``.
"""

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from config.admin import platform_admin_site

from .models import DomainEvent, WebhookSubscription, WebhookDelivery


@admin.register(WebhookSubscription, site=platform_admin_site)
class WebhookSubscriptionAdmin(ModelAdmin):
    list_display = ("url", "school_id", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("url", "description")


@admin.register(WebhookDelivery, site=platform_admin_site)
class WebhookDeliveryAdmin(ModelAdmin):
    list_display = (
        "subscription",
        "domain_event",
        "status",
        "http_status",
        "retry_count",
        "max_attempts",
        "scheduled_for",
        "created_at",
    )
    list_filter = ("status",)
    raw_id_fields = ("subscription", "domain_event")
    readonly_fields = ("created_at", "attempted_at", "delivered_at")


@admin.register(DomainEvent, site=platform_admin_site)
class DomainEventAdmin(ModelAdmin):
    list_display = (
        "event_type",
        "status",
        "school_id",
        "created_at",
        "processed_at",
        "retry_count",
    )
    list_filter = ("status", "event_type")
    search_fields = ("event_type", "idempotency_key")
    readonly_fields = (
        "id",
        "created_at",
        "processed_at",
        "retry_count",
        "payload_preview",
    )
    ordering = ("-created_at",)

    def payload_preview(self, obj):
        if not obj.payload:
            return "-"
        import json

        try:
            s = json.dumps(obj.payload)[:500]
            return format_html("<pre>{}</pre>", s)
        except (TypeError, ValueError):
            return str(obj.payload)[:500]

    payload_preview.short_description = "Payload (preview)"
