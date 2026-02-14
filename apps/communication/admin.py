from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html

from config.admin import admin_site
from apps.communication.models import Message, Announcement, AnnouncementAuditLog


class FinanceRequestFilter(SimpleListFilter):
    title = "Finance access requests"
    parameter_name = "finance_request"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Finance access"),
            ("unread", "Finance access (unread)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(subject__icontains="finance access request")
        if self.value() == "unread":
            return queryset.filter(subject__icontains="finance access request", is_read=False)
        return queryset


@admin.register(Message, site=admin_site)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "recipient", "is_read", "is_finance_request", "created_at")
    list_filter = ("is_read", "is_archived", FinanceRequestFilter, "created_at")
    search_fields = ("subject", "body", "sender__username", "recipient__username", "sender__email", "recipient__email")
    readonly_fields = ("created_at", "updated_at")

    def is_finance_request(self, obj):
        return "Finance access" if "finance access request" in obj.subject.lower() else ""

    is_finance_request.short_description = "Tags"


@admin.register(Announcement, site=admin_site)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "audience", "is_active", "created_by", "approved_by", "created_at")
    list_filter = ("status", "audience", "is_active", "announcement_type")
    search_fields = ("title", "content")
    readonly_fields = ("created_at", "updated_at", "approved_at")
    list_editable = ("is_active",)


@admin.register(AnnouncementAuditLog, site=admin_site)
class AnnouncementAuditLogAdmin(admin.ModelAdmin):
    list_display = ("announcement_id", "action", "user", "created_at", "notes_preview")
    list_filter = ("action", "created_at")
    search_fields = ("notes", "announcement__title")
    readonly_fields = ("announcement", "user", "action", "notes", "created_at")

    def notes_preview(self, obj):
        return (obj.notes or "")[:60] + ("..." if len(obj.notes or "") > 60 else "")
    notes_preview.short_description = "Notes"
