from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from config.admin import admin_site

from unfold.admin import ModelAdmin

from .models import User, AccessRole, Permission, UserPreference, TemporaryRoleGrant, Delegation, DelegationActionLog

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


class TemporaryRoleGrantAdmin(ModelAdmin):
    list_display = ("user", "role", "valid_from", "expires_at", "created_by", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "notes")
    raw_id_fields = ("user", "created_by")
    readonly_fields = ("created_at",)
    date_hierarchy = "expires_at"


class DelegationActionLogInline(admin.TabularInline):
    model = DelegationActionLog
    extra = 0
    readonly_fields = ("actor", "acting_for", "action_taken", "object_repr", "created_at")
    can_delete = False
    max_num = 20


class DelegationAdmin(ModelAdmin):
    list_display = ("delegator", "delegate", "start_date", "end_date", "extended_end_date", "is_active", "is_current_display", "reason")
    list_filter = ("is_active",)
    search_fields = ("delegator__username", "delegate__username", "reason")
    raw_id_fields = ("delegator", "delegate", "created_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "start_date"
    inlines = [DelegationActionLogInline]

    def is_current_display(self, obj):
        return obj.is_current if obj else False
    is_current_display.boolean = True
    is_current_display.short_description = "Current"


class DelegationActionLogAdmin(ModelAdmin):
    list_display = ("actor", "acting_for", "action_taken", "object_repr", "created_at")
    list_filter = ("action_taken",)
    search_fields = ("actor__username", "acting_for__username", "action_taken", "object_repr")
    raw_id_fields = ("actor", "acting_for", "delegation")
    readonly_fields = ("delegation", "actor", "acting_for", "action_taken", "object_repr", "object_id", "content_type", "metadata", "created_at")
    date_hierarchy = "created_at"


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
admin_site.register(TemporaryRoleGrant, TemporaryRoleGrantAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(UserPreference, UserPreferenceAdmin)
admin_site.register(Delegation, DelegationAdmin)
admin_site.register(DelegationActionLog, DelegationActionLogAdmin)