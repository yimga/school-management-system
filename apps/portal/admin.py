from django.contrib import admin
from config.admin import admin_site

from .models import PortalFeatureItem, PendingGuardianInvite, Announcement


class PortalFeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feature", "is_active", "created_by", "created_at")
    list_filter = ("feature", "is_active")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("created_by",)
    change_form_template = "admin/portal/portalfeatureitem/change_form.html"


class PendingGuardianInviteAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "student",
        "invited_email",
        "invited_phone",
        "relationship",
        "preferred_contact",
        "is_claimed",
        "created_at",
    )
    list_filter = ("relationship", "preferred_contact", "claimed_at")
    search_fields = ("token", "invited_email", "invited_phone", "student__last_name", "student__admission_number")
    autocomplete_fields = ("student", "created_by", "guardian_user")
    readonly_fields = ("claimed_at",)


class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "banner_type", "is_active", "is_currently_active", "created_by", "created_at")
    list_filter = ("banner_type", "is_active", "created_at")
    search_fields = ("title", "message")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("created_by",)
    fieldsets = (
        ("Announcement Content", {
            "fields": ("title", "message", "banner_type")
        }),
        ("Display Settings", {
            "fields": ("is_active", "start_date", "end_date")
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    change_form_template = "admin/portal/announcement/change_form.html"


# Register all models with custom admin site
admin_site.register(PortalFeatureItem, PortalFeatureItemAdmin)
admin_site.register(PendingGuardianInvite, PendingGuardianInviteAdmin)
admin_site.register(Announcement, AnnouncementAdmin)
