from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin
from .models import TermPublishStatus, ReportCard, PromotionRule, EMISSubmission


class TermPublishStatusAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "is_published", "published_at", "published_by")
    list_filter = ("academic_year", "term", "is_published", "classroom")
    search_fields = ("academic_year__name",)


class ReportCardAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "term", "type", "generated_at")


class PromotionRuleAdmin(ModelAdmin):
    list_display = ("academic_year", "classroom", "promotion_average", "demotion_average")
    list_filter = ("academic_year", "classroom")


class EMISSubmissionAdmin(ModelAdmin):
    list_display = ("school", "report_type", "period_label", "status", "submitted_at", "created_at")
    list_filter = ("school", "report_type", "status")
    search_fields = ("school__name", "period_label", "external_id")
    raw_id_fields = ("school", "academic_year", "term", "submitted_by")


# Register all models with custom admin site
admin_site.register(TermPublishStatus, TermPublishStatusAdmin)
admin_site.register(ReportCard, ReportCardAdmin)
admin_site.register(PromotionRule, PromotionRuleAdmin)
admin_site.register(EMISSubmission, EMISSubmissionAdmin)
