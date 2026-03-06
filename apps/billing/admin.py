from django.contrib import admin

from config.admin import admin_site

from apps.billing.models import BillingAccount, PlatformLedgerEntry, TenantSubscription, UsageMeter


@admin.register(BillingAccount, site=admin_site)
class BillingAccountAdmin(admin.ModelAdmin):
    list_display = ("school", "status", "billing_email", "currency_code", "external_customer_ref", "updated_at")
    list_filter = ("status", "currency_code")
    search_fields = ("school__name", "billing_email", "external_customer_ref")


@admin.register(TenantSubscription, site=admin_site)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("school", "status", "plan", "billing_cycle", "base_amount", "billed_amount", "updated_at")
    list_filter = ("status", "billing_cycle")
    search_fields = ("school__name", "plan__name")


@admin.register(UsageMeter, site=admin_site)
class UsageMeterAdmin(admin.ModelAdmin):
    list_display = ("school", "metric_code", "period_start", "period_end", "quantity", "updated_at")
    list_filter = ("metric_code",)
    search_fields = ("school__name", "metric_code")


@admin.register(PlatformLedgerEntry, site=admin_site)
class PlatformLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("school", "entry_type", "status", "amount", "currency_code", "reference", "happened_at")
    list_filter = ("entry_type", "status", "currency_code")
    search_fields = ("school__name", "reference", "description", "source_ref")
