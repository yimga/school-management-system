from config.admin import register_tenant_admin

from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from .models import (
    TermPublishStatus,
    ReportCard,
    PromotionRule,
    EMISSubmission,
    ReportPack,
    TenantReportSchedule,
)


class TermPublishStatusAdmin(ModelAdmin):
    list_display = (
        "academic_year",
        "term",
        "classroom",
        "is_published",
        "published_at",
        "published_by",
    )
    list_filter = ("academic_year", "term", "is_published", "classroom")
    search_fields = ("academic_year__name",)


class ReportCardAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "term", "type", "generated_at")


class PromotionRuleAdmin(ModelAdmin):
    list_display = (
        "academic_year",
        "classroom",
        "promotion_average",
        "demotion_average",
    )
    list_filter = ("academic_year", "classroom")


class EMISSubmissionAdmin(ModelAdmin):
    list_display = (
        "school",
        "report_type",
        "period_label",
        "status",
        "submitted_at",
        "created_at",
    )
    list_filter = ("school", "report_type", "status")
    search_fields = ("school__name", "period_label", "external_id")
    raw_id_fields = ("school", "academic_year", "term", "submitted_by")


class ReportPackAdmin(ModelAdmin):
    """Phase 10 — 10.3: Report library pack (preview, dependency mapping)."""

    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


class TenantReportScheduleActiveEmptyRecipientsFilter(admin.SimpleListFilter):
    """Surface active rows that cannot send mail until addresses are added."""

    title = "Recipient addresses"
    parameter_name = "trs_recipient_gap"

    def lookups(self, request, model_admin):
        return (("active_empty", "Active with no addresses"),)

    def queryset(self, request, queryset):
        if self.value() == "active_empty":
            return queryset.filter(is_active=True, recipients=[])
        return queryset


class TenantReportScheduleAdmin(ModelAdmin):
    """Tenant scheduled report delivery rows (API + hub + send_scheduled_reports)."""

    actions = ("deactivate_active_empty_recipients",)

    list_display = (
        "name",
        "school",
        "report_key",
        "schedule_frequency",
        "last_run",
        "next_run",
        "recipient_count_display",
        "is_active",
    )
    list_filter = (
        TenantReportScheduleActiveEmptyRecipientsFilter,
        "is_active",
        "schedule_frequency",
        "school",
    )
    search_fields = ("name", "report_key", "school__name", "school__slug")
    raw_id_fields = ("school", "created_by")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Recipients")
    def recipient_count_display(self, obj: TenantReportSchedule) -> int:
        r = obj.recipients
        return len(r) if isinstance(r, list) else 0

    @admin.action(description="Deactivate active rows with no recipient addresses")
    def deactivate_active_empty_recipients(self, request, queryset):
        updated = queryset.filter(is_active=True, recipients=[]).update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {updated} schedule(s) that had no addresses while active.",
            messages.SUCCESS,
        )


# Register all models with tenant admin only
register_tenant_admin(TermPublishStatus, TermPublishStatusAdmin)
register_tenant_admin(ReportCard, ReportCardAdmin)
register_tenant_admin(PromotionRule, PromotionRuleAdmin)
register_tenant_admin(EMISSubmission, EMISSubmissionAdmin)
register_tenant_admin(ReportPack, ReportPackAdmin)
register_tenant_admin(TenantReportSchedule, TenantReportScheduleAdmin)
