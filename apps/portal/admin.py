from django.contrib import admin
from config.admin import admin_site

from .models import PortalFeatureItem, PendingGuardianInvite


class PortalFeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feature", "is_active", "created_by", "created_at")
    list_filter = ("feature", "is_active")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("created_by",)


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


# Register all models with custom admin site
admin_site.register(PortalFeatureItem, PortalFeatureItemAdmin)
admin_site.register(PendingGuardianInvite, PendingGuardianInviteAdmin)
