from django.contrib import admin

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
    Payment,
    TaxBracket,
)


@admin.register(ComplianceProfile)
class ComplianceProfileAdmin(ModelAdmin):
    list_display = ("name", "country_code", "currency_code", "chart_template", "is_active")
    list_filter = ("country_code", "chart_template", "is_active")
    search_fields = ("name", "country_code")


@admin.register(TaxBracket)
class TaxBracketAdmin(ModelAdmin):
    list_display = ("profile", "lower_bound", "upper_bound", "rate")
    list_filter = ("profile",)


@admin.register(ContributionRule)
class ContributionRuleAdmin(ModelAdmin):
    list_display = ("profile", "code", "name", "employee_rate", "employer_rate", "cap_amount")
    list_filter = ("profile",)
    search_fields = ("code", "name")


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ModelAdmin):
    list_display = ("profile", "code", "name", "account_type", "is_active")
    list_filter = ("profile", "account_type", "is_active")
    search_fields = ("code", "name")


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(ModelAdmin):
    list_display = ("entry_date", "reference", "profile", "posted_at")
    list_filter = ("profile",)
    search_fields = ("reference", "memo")
    inlines = [JournalLineInline]


@admin.register(Counterparty)
class CounterpartyAdmin(ModelAdmin):
    list_display = ("name", "counterparty_type", "student", "user")
    list_filter = ("counterparty_type",)
    search_fields = ("name", "email", "phone")


class FeeItemInline(admin.TabularInline):
    model = FeeItem
    extra = 0


@admin.register(FeePlan)
class FeePlanAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "classroom", "specialty", "is_active")
    list_filter = ("academic_year", "classroom", "specialty", "is_active")
    search_fields = ("name",)
    inlines = [FeeItemInline]


@admin.register(FeeInstallment)
class FeeInstallmentAdmin(ModelAdmin):
    list_display = ("fee_item", "installment_number", "amount", "due_date")
    list_filter = ("fee_item",)


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = ("invoice_type", "reference", "status", "student", "total_amount", "balance_amount", "issued_date")
    list_filter = ("invoice_type", "status", "issued_date")
    search_fields = ("reference", "student__student_code", "counterparty__name")
    inlines = [InvoiceLineInline]


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ("invoice", "amount", "method", "paid_at", "receipt_number")
    list_filter = ("method", "paid_at")
    search_fields = ("reference", "receipt_number")


@admin.register(Budget)
class BudgetAdmin(ModelAdmin):
    list_display = ("name", "academic_year", "department", "total_amount")
    list_filter = ("academic_year", "department")


@admin.register(BudgetLine)
class BudgetLineAdmin(ModelAdmin):
    list_display = ("budget", "account", "amount")
    list_filter = ("budget",)


@admin.register(AssetCategory)
class AssetCategoryAdmin(ModelAdmin):
    list_display = ("name",)


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = ("name", "category", "status", "purchase_cost")
    list_filter = ("status", "category")
    search_fields = ("name", "asset_tag")


class GrantAllocationInline(admin.TabularInline):
    model = GrantAllocation
    extra = 0


@admin.register(Grant)
class GrantAdmin(ModelAdmin):
    list_display = ("name", "funder", "amount", "start_date", "end_date")
    search_fields = ("name", "funder")
    inlines = [GrantAllocationInline]
