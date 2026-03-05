from django.contrib import admin
from django.utils.html import format_html
from .models import DomainEvent, WebhookSubscription, WebhookDelivery


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("url", "school_id", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("url", "description")


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("subscription", "domain_event", "status", "http_status", "retry_count", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("subscription", "domain_event")
    readonly_fields = ("created_at",)


@admin.register(DomainEvent)
class DomainEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "status", "school_id", "created_at", "processed_at", "retry_count")
    list_filter = ("status", "event_type")
    search_fields = ("event_type", "idempotency_key")
    readonly_fields = ("id", "created_at", "processed_at", "retry_count", "payload_preview")
    ordering = ("-created_at",)

    def payload_preview(self, obj):
        if not obj.payload:
            return "-"
        import json
        try:
            s = json.dumps(obj.payload)[:500]
            return format_html("<pre>{}</pre>", s)
        except Exception:
            return str(obj.payload)[:500]

    payload_preview.short_description = "Payload (preview)"
