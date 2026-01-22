from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin
from .models import TermPublishStatus, ReportCard, PromotionRule


class TermPublishStatusAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "is_published", "published_at", "published_by")
    list_filter = ("academic_year", "term", "is_published", "classroom")
    search_fields = ("academic_year__name",)


class ReportCardAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "term", "type", "generated_at")


class PromotionRuleAdmin(ModelAdmin):
    list_display = ("academic_year", "classroom", "promotion_average", "demotion_average")
    list_filter = ("academic_year", "classroom")


# Register all models with custom admin site
admin_site.register(TermPublishStatus, TermPublishStatusAdmin)
admin_site.register(ReportCard, ReportCardAdmin)
admin_site.register(PromotionRule, PromotionRuleAdmin)
