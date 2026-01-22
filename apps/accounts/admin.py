from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from unfold.admin import ModelAdmin

from .models import User, AccessRole, Permission


# Unregister Group from default admin site (we'll re-register it here)
admin.site.unregister(Group)


@admin.register(User)
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


@admin.register(AccessRole)
class RoleAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")
    filter_horizontal = ("permissions",)


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Group)
class GroupAdmin(ModelAdmin):
    """Groups admin - relocated from django.contrib.auth to Accounts section."""
    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("permissions",)
    
    class Meta:
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"
