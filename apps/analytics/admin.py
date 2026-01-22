from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin

from .models import GradingDeadline


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


# Register all models with custom admin site
admin_site.register(GradingDeadline, GradingDeadlineAdmin)
