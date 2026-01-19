from django.contrib import admin

from unfold.admin import ModelAdmin

from .models import GradingDeadline


@admin.register(GradingDeadline)
class GradingDeadlineAdmin(ModelAdmin):
    list_display = (
        "academic_year",
        "term",
        "classroom",
        "deadline_at",
        "updated_at",
    )
    list_filter = (
        "academic_year",
        "term",
        "classroom",
    )
    ordering = ("-deadline_at",)
