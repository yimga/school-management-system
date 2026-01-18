from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import TermPublishStatus, ReportCard, PromotionRule


@admin.register(TermPublishStatus)
class TermPublishStatusAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "is_published", "published_at", "published_by")
    list_filter = ("academic_year", "term", "is_published", "classroom")
    search_fields = ("academic_year__name",)


@admin.register(ReportCard)
class ReportCardAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "term", "type", "generated_at")


@admin.register(PromotionRule)
class PromotionRuleAdmin(ModelAdmin):
    list_display = ("academic_year", "classroom", "promotion_average", "demotion_average")
    list_filter = ("academic_year", "classroom")
