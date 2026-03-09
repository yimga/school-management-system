from django.contrib import admin

from config.admin import platform_admin_site

from apps.billing.models import (
    BillingAccount,
    BillingProcessorSyncEvent,
    PlatformLedgerEntry,
    PlatformBillingProcessorConfig,
    Quote,
    RevenueSharePayout,
    TenantSubscription,
    UsageMeter,
)


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
    search_fields = ("school__name", "billing_email", "external_customer_ref", "processor_code")


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


@admin.register(UsageMeter, site=platform_admin_site)
class UsageMeterAdmin(admin.ModelAdmin):
    list_display = ("school", "metric_code", "period_start", "period_end", "quantity", "updated_at")
    list_filter = ("metric_code",)
    search_fields = ("school__name", "metric_code")


@admin.register(PlatformLedgerEntry, site=platform_admin_site)
class PlatformLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("school", "entry_type", "status", "amount", "currency_code", "reference", "happened_at")
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
    search_fields = ("school__name", "external_customer_ref", "external_subscription_ref", "message")


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
    list_display = ("id", "school", "plan", "status", "amount", "currency_code", "valid_until", "created_at")
    list_filter = ("status", "currency_code")
    search_fields = ("school__name", "plan__name")
    actions = ["accept_quote_convert_to_contract"]

    @admin.action(description="Accept quote (convert to contract)")
    def accept_quote_convert_to_contract(self, request, queryset):
        from apps.billing.services import convert_quote_to_contract
        done, errors = 0, []
        for quote in queryset:
            try:
                convert_quote_to_contract(quote)
                done += 1
            except Exception as e:
                errors.append(f"Quote #{quote.id}: {e}")
        if done:
            self.message_user(request, f"Converted {done} quote(s) to contract.")
        if errors:
            self.message_user(request, "; ".join(errors[:5]) + ("..." if len(errors) > 5 else ""), level=40)


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
