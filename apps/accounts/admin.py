from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from config.admin import admin_site

from unfold.admin import ModelAdmin

from .models import User, AccessRole, Permission, UserPreference

class UserPreferenceAdmin(ModelAdmin):
    list_display = ("user", "show_background_logo", "background_logo_opacity", "updated_at")
    search_fields = ("user__username", "user__email")



# Unregister Group from default admin site (we'll re-register it here)
admin.site.unregister(Group)


class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """Unfold-styled user admin with an additional Role field."""

    # Add role to the default Django user admin form
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Role", {"fields": ("role", "roles", "feature_permissions")}),
        ("Profile", {"fields": ("profile_photo",)}),
    )

    # Show role in the users list
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)


class RoleAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    filter_horizontal = ("permissions",)


class PermissionAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


class GroupAdmin(ModelAdmin):
    """Groups admin - relocated from django.contrib.auth to Accounts section."""
    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("permissions",)
    
    class Meta:
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"



# Register all models with custom admin site
admin_site.register(User, UserAdmin)
admin_site.register(AccessRole, RoleAdmin)
admin_site.register(Permission, PermissionAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(UserPreference, UserPreferenceAdmin)
