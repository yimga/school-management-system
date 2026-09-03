"""Payment admin classes (Phase 2.0).

Until 2026-09-01 every class here registered with a bare ``@admin.register(Model)``,
which names no site and therefore targeted Django's default ``admin.site`` -- a site
no urlconf in this repo mounts. The module was also imported by nothing, so those
registrations never even ran. Transaction, RefundRequest, PaymentReconciliation and
PaymentAuditLog consequently had no admin screen anywhere, and
RefundRequestAdmin.process_selected_refunds -- the only path that applies a refund to
the ledger instead of just flipping a status -- was unreachable.

They now register on the tenant site, and apps/finance/admin.py imports this module so
the registrations execute. The duplicate PaymentAdmin that lived here was removed:
Payment already has a live, current ModelAdmin in apps/finance/admin.py, and a second
same-named class sitting next to live code only invites drift.
"""

from django.contrib import admin, messages
from django.utils.html import format_html
from config.admin import register_tenant_admin
from apps.finance.models import (
    Transaction,
    RefundRequest,
    PaymentReconciliation,
    PaymentAuditLog,
)


class TransactionAdmin(admin.ModelAdmin):
    """Admin for Transaction model."""

    list_display = (
        "id",
        "payment",
        "transaction_type",
        "amount_display",
        "status_badge",
        "timestamp",
    )
    list_filter = ("transaction_type", "status", "timestamp")
    search_fields = ("payment__reference_number", "gateway_reference")
    readonly_fields = ("id", "timestamp", "metadata")

    def amount_display(self, obj):
        return f"{obj.amount} {obj.currency}"

    amount_display.short_description = "Amount"

    def status_badge(self, obj):
        colors = {"success": "#90EE90", "failed": "#FF6347", "pending": "#FFA500"}
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, "#808080"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


class RefundRequestAdmin(admin.ModelAdmin):
    """Admin for RefundRequest model."""

    actions = ["process_selected_refunds"]

    @admin.action(description="Process selected refund requests (reduce invoice balance)")
    def process_selected_refunds(self, request, queryset):
        """Apply each selected refund to the ledger via the canonical producer.

        Before this action a RefundRequest could be flipped to 'processed' in
        the change form with no effect on the payment or invoice — the refund
        was recorded but the money kept counting as received. This routes every
        selected request through ``process_refund_request`` so the payment's
        ``refunded_amount`` grows (and it flips to 'refunded' when fully
        refunded) and the invoice balance is recomputed.
        """
        from apps.finance.services import (
            RefundProcessingError,
            process_refund_request,
        )

        processed = 0
        skipped = 0
        for refund in queryset:
            if refund.status in ("processed", "rejected"):
                skipped += 1
                continue
            try:
                process_refund_request(refund, processed_by=request.user)
                processed += 1
            except RefundProcessingError as exc:
                self.message_user(
                    request, f"Refund {refund.pk}: {exc}", level=messages.ERROR
                )
        if processed:
            self.message_user(
                request,
                f"Processed {processed} refund request(s).",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Skipped {skipped} already-processed or rejected request(s).",
                level=messages.WARNING,
            )

    list_display = (
        "id",
        "payment",
        "amount_display",
        "reason",
        "status_badge",
        "created_at",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = ("payment__reference_number", "description")
    readonly_fields = ("id", "created_at", "updated_at", "processed_at")
    fieldsets = (
        (
            "Refund Info",
            {"fields": ("id", "payment", "region", "amount", "reason", "description")},
        ),
        ("Status", {"fields": ("status", "status_notes", "approved_by")}),
        (
            "Processing",
            {"fields": ("requested_by", "processed_at", "created_at", "updated_at")},
        ),
    )

    def amount_display(self, obj):
        return f"{obj.amount}"

    amount_display.short_description = "Refund Amount"

    def status_badge(self, obj):
        colors = {
            "pending": "#FFA500",
            "approved": "#87CEEB",
            "rejected": "#FF6347",
            "processed": "#90EE90",
        }
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, "#808080"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


class PaymentReconciliationAdmin(admin.ModelAdmin):
    """Admin for PaymentReconciliation model."""

    list_display = (
        "region",
        "payment_method",
        "period_display",
        "net_amount_display",
        "status_badge",
    )
    list_filter = ("status", "period_end", "region", "payment_method")
    readonly_fields = ("id", "created_at", "reconciled_at")
    fieldsets = (
        (
            "Period",
            {
                "fields": (
                    "id",
                    "region",
                    "payment_method",
                    "period_start",
                    "period_end",
                )
            },
        ),
        (
            "Totals",
            {"fields": ("total_payments", "total_refunds", "total_fees", "net_amount")},
        ),
        (
            "Reconciliation",
            {
                "fields": (
                    "status",
                    "discrepancy_amount",
                    "discrepancy_notes",
                    "reconciled_by",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "reconciled_at"), "classes": ("collapse",)},
        ),
    )

    def period_display(self, obj):
        return f"{obj.period_start} to {obj.period_end}"

    period_display.short_description = "Period"

    def net_amount_display(self, obj):
        color = "green" if obj.net_amount > 0 else "red"
        return format_html('<span style="color: {};">{}</span>', color, obj.net_amount)

    net_amount_display.short_description = "Net Amount"

    def status_badge(self, obj):
        colors = {
            "pending": "#FFA500",
            "reconciled": "#90EE90",
            "discrepancy": "#FF6347",
        }
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.status, "#808080"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"


class PaymentAuditLogAdmin(admin.ModelAdmin):
    """Admin for PaymentAuditLog model."""

    list_display = ("action_type", "region", "severity_badge", "user", "timestamp")
    list_filter = ("action_type", "severity", "timestamp", "region")
    search_fields = ("description", "user__username")
    readonly_fields = ("id", "timestamp", "details")

    def severity_badge(self, obj):
        colors = {
            "low": "#90EE90",
            "medium": "#FFA500",
            "high": "#FF6347",
            "critical": "#8B0000",
        }
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; border-radius: 3px; color: white;">{}</span>',
            colors.get(obj.severity, "#808080"),
            obj.get_severity_display(),
        )

    severity_badge.short_description = "Severity"

    # No add/delete for audit logs
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# apps.finance is in TENANT_APPS, so these tables live inside the tenant's own
# schema under django-tenants and are confined by RLS in single-schema mode --
# TenantAdminSite therefore needs no scoping mixin for them. This matches every
# other finance registration in apps/finance/admin.py.
register_tenant_admin(Transaction, TransactionAdmin)
register_tenant_admin(RefundRequest, RefundRequestAdmin)
register_tenant_admin(PaymentReconciliation, PaymentReconciliationAdmin)
register_tenant_admin(PaymentAuditLog, PaymentAuditLogAdmin)
