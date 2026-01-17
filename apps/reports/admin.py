from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import TermPublishStatus, ReportCard


@admin.register(TermPublishStatus)
class TermPublishStatusAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "is_published", "published_at", "published_by")
    list_filter = ("academic_year", "term", "is_published", "classroom")
    search_fields = ("academic_year__name",)


@admin.register(ReportCard)
class ReportCardAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "term", "type", "generated_at")
    list_filter = ("academic_year", "term", "type")
    search_fields = ("student__student_code", "student__first_name", "student__last_name")

