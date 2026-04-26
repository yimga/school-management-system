from django.contrib import admin

from config.admin import platform_admin_site

from apps.sales.models import ActivityLog, Lead, PipelineStage


@admin.register(PipelineStage, site=platform_admin_site)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "sort_order")
    ordering = ("sort_order", "pk")


class ActivityLogInline(admin.TabularInline):
    model = ActivityLog
    extra = 0
    readonly_fields = ("created_at", "created_by")


@admin.register(Lead, site=platform_admin_site)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("school_name", "contact_name", "email", "stage", "next_follow_up")
    list_filter = ("stage",)
    search_fields = ("school_name", "email", "contact_name")
    inlines = (ActivityLogInline,)
