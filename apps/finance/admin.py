from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin

from .models import (
    Asset,
    AssetCategory,
    Budget,
    BudgetLine,
    ComplianceProfile,
    ContributionRule,
    Counterparty,
    FeeInstallment,
    FeeItem,
    FeePlan,
    Grant,
    GrantAllocation,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    FinanceRequestAudit,
    Payment,
    ReferralReward,
    TaxBracket,
    PaymentReminder,
    PaymentReminderLog,
    Notification,
    ReportRequest,
)


class ComplianceProfileAdmin(ModelAdmin):
    list_display = ("name", "country_code", "currency_code", "chart_template", "timezone", "is_active")
    list_filter = ("country_code", "chart_template", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("name", "country_code")
    fieldsets = (
        ("Identity", {"fields": ("name", "country_code", "currency_code")}),
        ("Localization", {"fields": ("timezone",), "description": "Default timezone for date/time operations; overrides settings.TIME_ZONE."}),
        ("Configuration", {"fields": ("chart_template", "available_payment_methods")}),
        ("Status", {"fields": ("is_active",)}),
    )


class TaxBracketAdmin(ModelAdmin):
    list_display = ("profile", "lower_bound", "upper_bound", "rate")
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination


class ContributionRuleAdmin(ModelAdmin):
    list_display = ("profile", "code", "name", "employee_rate", "employer_rate", "cap_amount")
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("code", "name")


class LedgerAccountAdmin(ModelAdmin):
    list_display = ("profile", "code", "name", "account_type", "is_active")
    list_filter = ("profile", "account_type", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("code", "name")


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


class JournalEntryAdmin(ModelAdmin):
    list_display = ("entry_date", "reference", "profile", "posted_at")
    list_filter = ("profile",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("reference", "memo")
    inlines = [JournalLineInline]


class CounterpartyAdmin(ModelAdmin):
    list_display = ("name", "counterparty_type", "student", "user")
    list_filter = ("counterparty_type",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("name", "email", "phone")


class FeeItemInline(admin.TabularInline):
    model = FeeItem
    extra = 0


class FeePlanAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "classroom", "specialty", "is_active")
    list_filter = ("academic_year", "classroom", "specialty", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("name",)
    inlines = [FeeItemInline]


class FeeInstallmentAdmin(ModelAdmin):
    list_display = ("fee_item", "installment_number", "amount", "due_date")
    list_filter = ("fee_item",)
    list_per_page = 50  # PERFORMANCE: Add pagination


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class InvoiceAdmin(ModelAdmin):
    list_display = (
        "invoice_type",
        "reference",
        "status",
        "student",
        "total_amount",
        "balance_amount",
        "issued_date",
        "attachment",
    )
    list_filter = ("invoice_type", "status", "issued_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("reference", "student__student_code", "counterparty__name")
    inlines = [InvoiceLineInline]


class PaymentAdmin(ModelAdmin):
    list_display = ("invoice", "amount", "method", "paid_at", "receipt_number", "receipt_file")
    list_filter = ("method", "paid_at")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("reference", "receipt_number")


class PaymentReminderAdmin(ModelAdmin):
    list_display = ("invoice", "is_active", "next_send_at", "reminder_days_before")
    list_filter = ("is_active",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("invoice__reference", "invoice__student__student_code")


class PaymentReminderLogAdmin(ModelAdmin):
    list_display = ("reminder", "sent_at", "status")
    list_filter = ("status",)
    list_per_page = 50  # PERFORMANCE: Add pagination


class BudgetAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "department", "total_amount")
    list_filter = ("academic_year", "department")
    list_per_page = 50  # PERFORMANCE: Add pagination


class BudgetLineAdmin(ModelAdmin):
    list_display = ("budget", "account", "amount")
    list_filter = ("budget",)
    list_per_page = 50  # PERFORMANCE: Add pagination


class AssetCategoryAdmin(ModelAdmin):
    list_display = ("name",)
    list_per_page = 50  # PERFORMANCE: Add pagination


class AssetAdmin(ModelAdmin):
    list_display = ("name", "category", "status", "purchase_cost")
    list_filter = ("status", "category")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("name", "asset_tag")


class GrantAllocationInline(admin.TabularInline):
    model = GrantAllocation
    extra = 0


class GrantAdmin(ModelAdmin):
    list_display = ("name", "funder", "amount", "start_date", "end_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("name", "funder")
    inlines = [GrantAllocationInline]


class NotificationAdmin(ModelAdmin):
    list_display = ("title", "severity", "is_read", "created_at", "recipient", "created_by")
    list_filter = ("severity", "is_read")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("title", "message", "created_by__username", "recipient__username")


class ReportRequestAdmin(ModelAdmin):
    list_display = ("report_type", "requested_by", "status", "created_at")
    list_filter = ("report_type", "status")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("requested_by__username", "description")


class FinanceRequestAuditAdmin(ModelAdmin):
    list_display = ("notification", "action", "user", "created_at")
    list_filter = ("action",)
    list_per_page = 50
    search_fields = ("notification__title", "user__username", "action")


class ReferralRewardAdmin(ModelAdmin):
    list_display = ("student", "guardian", "amount", "status", "awarded_by", "created_at")
    list_filter = ("status",)
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("student__student_code", "guardian__guardian_user__username", "guardian__guardian_user__email")


# Register all models with custom admin site
admin_site.register(ComplianceProfile, ComplianceProfileAdmin)
admin_site.register(TaxBracket, TaxBracketAdmin)
admin_site.register(ContributionRule, ContributionRuleAdmin)
admin_site.register(LedgerAccount, LedgerAccountAdmin)
admin_site.register(JournalEntry, JournalEntryAdmin)
admin_site.register(Counterparty, CounterpartyAdmin)
admin_site.register(FeePlan, FeePlanAdmin)
admin_site.register(FeeInstallment, FeeInstallmentAdmin)
admin_site.register(Invoice, InvoiceAdmin)
admin_site.register(Payment, PaymentAdmin)
admin_site.register(PaymentReminder, PaymentReminderAdmin)
admin_site.register(PaymentReminderLog, PaymentReminderLogAdmin)
admin_site.register(Budget, BudgetAdmin)
admin_site.register(BudgetLine, BudgetLineAdmin)
admin_site.register(AssetCategory, AssetCategoryAdmin)
admin_site.register(Asset, AssetAdmin)
admin_site.register(Grant, GrantAdmin)
admin_site.register(Notification, NotificationAdmin)
admin_site.register(ReportRequest, ReportRequestAdmin)
admin_site.register(FinanceRequestAudit, FinanceRequestAuditAdmin)
admin_site.register(ReferralReward, ReferralRewardAdmin)
