from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin
from .models import (
    TermPublishStatus,
    ReportCard,
    PromotionRule,
    EMISSubmission,
    ReportPack,
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


# Register all models with tenant admin only
register_tenant_admin(TermPublishStatus, TermPublishStatusAdmin)
register_tenant_admin(ReportCard, ReportCardAdmin)
register_tenant_admin(PromotionRule, PromotionRuleAdmin)
register_tenant_admin(EMISSubmission, EMISSubmissionAdmin)
register_tenant_admin(ReportPack, ReportPackAdmin)
