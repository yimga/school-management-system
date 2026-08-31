from django.contrib import admin
from django.contrib.admin import SimpleListFilter

from config.admin import tenant_admin_site
from apps.communication.models import (
    Message,
    Announcement,
    AnnouncementAuditLog,
    CommunicationTemplate,
    FeedItem,
    OutboundMessageQueue,
)


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
            return queryset.filter(
                subject__icontains="finance access request", is_read=False
            )
        return queryset


@admin.register(Message, site=tenant_admin_site)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "sender",
        "recipient",
        "is_read",
        "is_finance_request",
        "created_at",
    )
    list_filter = ("is_read", "is_archived", FinanceRequestFilter, "created_at")
    search_fields = (
        "subject",
        "body",
        "sender__username",
        "recipient__username",
        "sender__email",
        "recipient__email",
    )
    readonly_fields = ("created_at", "updated_at")

    def is_finance_request(self, obj):
        return (
            "Finance access" if "finance access request" in obj.subject.lower() else ""
        )

    is_finance_request.short_description = "Tags"


@admin.register(Announcement, site=tenant_admin_site)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "audience",
        "is_active",
        "created_by",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "audience", "is_active", "announcement_type")
    search_fields = ("title", "content")
    readonly_fields = ("created_at", "updated_at", "approved_at")
    list_editable = ("is_active",)


@admin.register(AnnouncementAuditLog, site=tenant_admin_site)
class AnnouncementAuditLogAdmin(admin.ModelAdmin):
    list_display = ("announcement_id", "action", "user", "created_at", "notes_preview")
    list_filter = ("action", "created_at")
    search_fields = ("notes", "announcement__title")
    readonly_fields = ("announcement", "user", "action", "notes", "created_at")

    def notes_preview(self, obj):
        return (obj.notes or "")[:60] + ("..." if len(obj.notes or "") > 60 else "")

    notes_preview.short_description = "Notes"


@admin.register(FeedItem, site=tenant_admin_site)
class FeedItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "item_type",
        "school",
        "student",
        "created_at",
        "created_by",
    )
    list_filter = ("item_type", "school")
    search_fields = ("title", "body")
    readonly_fields = ("created_at",)


@admin.register(OutboundMessageQueue, site=tenant_admin_site)
class OutboundMessageQueueAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_identifier",
        "channel",
        "status",
        "school",
        "created_at",
        "sent_at",
    )
    list_filter = ("channel", "status", "school")
    search_fields = ("recipient_identifier", "body")
    readonly_fields = ("created_at", "sent_at")
    actions = ["mark_retry_pending"]

    def mark_retry_pending(self, request, queryset):
        n = queryset.filter(status="failed").update(status="pending")
        self.message_user(request, f"{n} item(s) set to pending for retry.")

    mark_retry_pending.short_description = "Retry failed (set to pending)"


@admin.register(CommunicationTemplate, site=tenant_admin_site)
class CommunicationTemplateAdmin(admin.ModelAdmin):
    """Per-tenant + platform-wide notification template overrides.

    Pairs with the code-level catalog at `apps/communication/template_catalog.py`.
    Resolution order: tenant override → platform-wide override → catalog → hard fallback.
    """

    list_display = ("key", "school", "locale", "is_active", "sensitivity", "updated_at")
    list_filter = ("is_active", "sensitivity", "school")
    search_fields = ("key", "subject_template", "body_template", "notes")
    # "school" is READ-ONLY, not editable: this admin is mounted on the tenant
    # site, where AdminFormAutomationMixin.get_exclude() strips "school" from
    # every form so a tenant cannot post another school's id. The fieldset
    # below still NAMES it, and Django's fieldset renderer resolves a named
    # field with form[name] -- which raised
    #   KeyError: "Key 'school' not found in 'RmcValidatedCommunicationTemplateForm'"
    # on add AND change, for every user, every time (reproduced 2026-08-31).
    # Listing it here is the same cure used by SchoolWaiverRequestAdmin and
    # TenantApiUsageAdmin. The mixin now also does this automatically for any
    # declared-but-excluded field; the explicit entry keeps this admin
    # readable on its own.
    readonly_fields = ("school", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("school", "key", "locale", "is_active")}),
        ("Content", {"fields": ("subject_template", "body_template", "channels", "audience", "sensitivity")}),
        ("Notes & audit", {"fields": ("notes", "created_at", "updated_at")}),
    )
