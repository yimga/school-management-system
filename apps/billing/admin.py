import logging

from django.contrib import admin
from django.db import DatabaseError

from config.admin import platform_admin_site

logger = logging.getLogger(__name__)

from apps.billing.models import (
    BillingAccount,
    BillingProcessorSyncEvent,
    Entitlement,
    PlatformLedgerEntry,
    PlatformBillingProcessorConfig,
    Quote,
    RevenueSharePayout,
    StripePlanPrice,
    TenantSubscription,
    UsageMeter,
)
from apps.billing.models_usage_caps import UsageCap


@admin.register(BillingAccount, site=platform_admin_site)
class BillingAccountAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "status",
        "processor_code",
        "billing_email",
        "currency_code",
        "external_customer_ref",
        "last_processor_sync_at",
        "updated_at",
    )
    list_filter = ("status", "currency_code", "processor_code")
    search_fields = (
        "school__name",
        "billing_email",
        "external_customer_ref",
        "processor_code",
    )


@admin.register(TenantSubscription, site=platform_admin_site)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "status",
        "plan",
        "billing_cycle",
        "external_subscription_ref",
        "base_amount",
        "billed_amount",
        "updated_at",
    )
    list_filter = ("status", "billing_cycle")
    search_fields = ("school__name", "plan__name", "external_subscription_ref")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # A direct plan/status edit here must re-materialize entitlements + bust the
        # gate cache, otherwise the tenant's feature access stays at the pre-edit
        # state until the next cache TTL or lifecycle run. The operator console
        # (tenant_subscription_manage) already reconciles; this closes the same gap
        # for the Django-admin fallback path. Best-effort: the row is already saved,
        # so a reconcile failure must not roll the edit back — log and move on.
        if not (obj.pk and obj.school_id and obj.billing_account_id):
            return
        try:
            from apps.billing.services import reconcile_subscription_entitlements

            reconcile_subscription_entitlements(obj)
        except (DatabaseError, AttributeError, TypeError, ValueError, ImportError):
            logger.warning(
                "admin_subscription_reconcile_failed for subscription %s",
                obj.pk,
                exc_info=True,
            )


@admin.register(Entitlement, site=platform_admin_site)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "code",
        "kind",
        "source",
        "is_enabled",
        "limit_value",
        "effective_until",
        "updated_at",
    )
    list_filter = ("kind", "source", "is_enabled")
    search_fields = ("school__name", "code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UsageMeter, site=platform_admin_site)
class UsageMeterAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "metric_code",
        "period_start",
        "period_end",
        "quantity",
        "updated_at",
    )
    list_filter = ("metric_code",)
    search_fields = ("school__name", "metric_code")


@admin.register(PlatformLedgerEntry, site=platform_admin_site)
class PlatformLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "entry_type",
        "status",
        "amount",
        "currency_code",
        "reference",
        "happened_at",
    )
    list_filter = ("entry_type", "status", "currency_code")
    search_fields = ("school__name", "reference", "description", "source_ref")


@admin.register(BillingProcessorSyncEvent, site=platform_admin_site)
class BillingProcessorSyncEventAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "processor_code",
        "event_type",
        "status",
        "external_customer_ref",
        "external_subscription_ref",
        "happened_at",
    )
    list_filter = ("processor_code", "event_type", "status")
    search_fields = (
        "school__name",
        "external_customer_ref",
        "external_subscription_ref",
        "message",
    )


@admin.register(StripePlanPrice, site=platform_admin_site)
class StripePlanPriceAdmin(admin.ModelAdmin):
    list_display = (
        "plan_code",
        "stripe_price_id",
        "billing_cycle",
        "currency",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "billing_cycle", "currency")
    search_fields = ("plan_code", "stripe_price_id")


@admin.register(PlatformBillingProcessorConfig, site=platform_admin_site)
class PlatformBillingProcessorConfigAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "display_name",
        "is_active",
        "signature_style",
        "signature_header",
        "last_webhook_at",
        "updated_at",
    )
    list_filter = ("is_active", "signature_style", "signature_algorithm")
    search_fields = ("code", "display_name")


@admin.register(Quote, site=platform_admin_site)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "school",
        "plan",
        "status",
        "amount",
        "currency_code",
        "valid_until",
        "created_at",
    )
    list_filter = ("status", "currency_code")
    search_fields = ("school__name", "plan__name")
    actions = ["accept_quote_convert_to_contract"]

    @admin.action(description="Accept quote (convert to contract)")
    def accept_quote_convert_to_contract(self, request, queryset):
        from apps.billing.services import convert_quote_to_contract

        done, errors = 0, []
        from django.core.exceptions import ValidationError
        from django.db import DatabaseError

        for quote in queryset:
            try:
                convert_quote_to_contract(quote)
                done += 1
            except (
                ValidationError,
                ValueError,
                TypeError,
                DatabaseError,
                KeyError,
                AttributeError,
            ) as e:
                errors.append(f"Quote #{quote.id}: {e}")
        if done:
            self.message_user(request, f"Converted {done} quote(s) to contract.")
        if errors:
            self.message_user(
                request,
                "; ".join(errors[:5]) + ("..." if len(errors) > 5 else ""),
                level=40,
            )


@admin.register(RevenueSharePayout, site=platform_admin_site)
class RevenueSharePayoutAdmin(admin.ModelAdmin):
    list_display = (
        "payee_name",
        "payout_scope",
        "status",
        "processor_code",
        "net_amount",
        "currency_code",
        "scheduled_for",
        "paid_at",
    )
    list_filter = ("payout_scope", "status", "processor_code", "currency_code")
    search_fields = ("payee_name", "payee_ref", "external_payout_ref")


@admin.register(UsageCap, site=platform_admin_site)
class UsageCapAdmin(admin.ModelAdmin):
    """v4.00.36 Phase 3: per-tenant usage caps + soft-warn + auto-freeze.

    Use ``soft_warn_at = 0`` to disable the soft warning; ``hard_cap = 0``
    to disable auto-suspension. ``enforce_cap_actions(school, dimension)``
    writes a ``usage_cap_events`` audit trail into BillingAccount.metadata
    on every soft-warn / hard-cap evaluation.
    """

    list_display = (
        "school",
        "dimension",
        "soft_warn_at",
        "hard_cap",
        "period_grain",
        "headroom_pct",
        "updated_at",
    )
    list_filter = ("dimension", "period_grain")
    search_fields = ("school__name", "dimension")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("school__name", "dimension")

    def headroom_pct(self, obj):
        """Quick operator scan: percent of hard_cap consumed in the current period.

        Read-only, computed on render. ``--`` when ``hard_cap`` is 0.
        """
        if not obj or not obj.hard_cap:
            return "--"
        try:
            from apps.billing.usage_caps import evaluate_cap

            verdict = evaluate_cap(obj.school, obj.dimension)
        except (ImportError, RuntimeError):
            return "--"
        if verdict.hard_cap <= 0:
            return "--"
        pct = (verdict.current * 100) // verdict.hard_cap
        return f"{pct}% ({verdict.band})"

    headroom_pct.short_description = "Headroom"
