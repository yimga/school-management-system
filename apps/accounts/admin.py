from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from config.admin import register_both, register_tenant_admin

from unfold.admin import ModelAdmin

from .models import (
    User,
    AccessRole,
    Permission,
    UserPreference,
    TemporaryRoleGrant,
    TenantStaffInvite,
    Delegation,
    DelegationActionLog,
    SecurityAuditLog,
    UserPasskey,
)


class UserPreferenceAdmin(ModelAdmin):
    list_display = (
        "user",
        "show_background_logo",
        "background_logo_opacity",
        "updated_at",
    )
    search_fields = ("user__username", "user__email")


# Unregister Group from default admin site (we'll re-register it here)
admin.site.unregister(Group)


class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """Unfold-styled user admin with an additional Role field."""

    show_full_result_count = False  # Avoid expensive COUNT on large user table

    # Add role to the default Django user admin form
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Role", {"fields": ("role", "roles", "feature_permissions")}),
        ("Profile", {"fields": ("profile_photo",)}),
        (
            "Portal roles (dual-role)",
            {
                "fields": ("guardian_of_display",),
                "description": "If this user is linked as a guardian to students, they can also use the Parent portal view.",
            },
        ),
    )

    readonly_fields = DjangoUserAdmin.readonly_fields + ("guardian_of_display",)

    # Show role in the users list
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)

    def guardian_of_display(self, obj):
        if not obj or not obj.pk:
            return "—"
        # StudentGuardian lives in TENANT_APPS only, so people_studentguardian
        # does NOT exist in the public (manager-host) schema. Rendering this
        # readonly field on the platform User change page would run a query
        # against a missing relation → 500. Guardian links are a tenant concept
        # that never applies to platform operators, so skip the query entirely
        # off-tenant. Belt to PlatformUserAdmin's suspenders (which also drops
        # this field). Preserves tenant⟂operator isolation.
        from django.db import connection

        try:
            from django_tenants.utils import get_public_schema_name

            if getattr(connection, "schema_name", None) == get_public_schema_name():
                return "—"
        except ImportError:
            pass
        from apps.people.models import StudentGuardian

        links = StudentGuardian.objects.filter(guardian_user=obj).select_related(  # tenant-isolation-allow: operator admin panel listing one user's links (reviewed 2026-09-03)
            "student"
        )[:50]
        if not links:
            return "—"
        from django.utils.html import format_html

        parts = [
            f"{link.student.get_full_name() or link.student.username} (ID {link.student_id})"
            for link in links
        ]
        if len(links) >= 50:
            parts.append("…")
        return format_html("{}", ", ".join(parts))

    guardian_of_display.short_description = "Also guardian of"


class TenantScopedUserAdmin(UserAdmin):
    """Tenant /admin/ User changelist limited to members of request.school."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        school = getattr(request, "school", None)
        if school is None:
            return qs.none()
        from apps.accounts.tenant_identity import users_queryset_for_school

        return qs.filter(
            pk__in=users_queryset_for_school(school).values_list("pk", flat=True)
        )


class PlatformUserAdmin(UserAdmin):
    """Break-glass manager admin: User changelist scoped to platform operators only."""

    show_full_result_count = False

    # Guardian relationships are a TENANT concept: apps.people is TENANT_APPS-only,
    # so people_studentguardian does not exist in the public/manager schema. Drop
    # the "Portal roles (dual-role)" section (and the guardian_of_display readonly
    # field it renders) on the operator surface so the User change page never
    # touches off-schema data. tenant⟂operator isolation.
    fieldsets = UserAdmin.fieldsets[:-1]
    readonly_fields = DjangoUserAdmin.readonly_fields

    def get_queryset(self, request):
        from apps.platform_runtime.operator_identity import queryset_platform_operators

        base = super().get_queryset(request)
        operator_ids = queryset_platform_operators().values_list("pk", flat=True)
        return base.filter(pk__in=operator_ids)


class RoleAdmin(ModelAdmin):
    list_display = ("code", "name", "school")
    list_filter = ("school",)
    search_fields = ("code", "name")
    filter_horizontal = ("permissions",)


class PermissionAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


class TemporaryRoleGrantAdmin(ModelAdmin):
    list_display = (
        "user",
        "role",
        "valid_from",
        "expires_at",
        "created_by",
        "created_at",
    )
    list_filter = ("role",)
    search_fields = ("user__username", "notes")
    raw_id_fields = ("user", "created_by")
    readonly_fields = ("created_at",)
    date_hierarchy = "expires_at"


class TenantStaffInviteAdmin(ModelAdmin):
    list_display = (
        "email",
        "school",
        "role",
        "is_school_owner",
        "expires_at",
        "accepted_at",
        "created_at",
    )
    list_filter = ("is_school_owner", "role", "school")
    search_fields = ("email", "school__name", "school__slug")
    raw_id_fields = ("school", "invited_by")
    readonly_fields = ("token", "created_at")
    date_hierarchy = "expires_at"


class DelegationActionLogInline(admin.TabularInline):
    model = DelegationActionLog
    extra = 0
    readonly_fields = (
        "actor",
        "acting_for",
        "action_taken",
        "object_repr",
        "created_at",
    )
    can_delete = False
    max_num = 20


class DelegationAdmin(ModelAdmin):
    list_display = (
        "delegator",
        "delegate",
        "start_date",
        "end_date",
        "extended_end_date",
        "is_active",
        "is_current_display",
        "reason",
    )
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
    search_fields = (
        "actor__username",
        "acting_for__username",
        "action_taken",
        "object_repr",
    )
    raw_id_fields = ("actor", "acting_for", "delegation")
    readonly_fields = (
        "delegation",
        "actor",
        "acting_for",
        "action_taken",
        "object_repr",
        "object_id",
        "content_type",
        "metadata",
        "created_at",
    )
    date_hierarchy = "created_at"


class GroupAdmin(ModelAdmin):
    """Groups admin - relocated from django.contrib.auth to Accounts section."""

    list_display = ("name",)
    search_fields = ("name",)
    filter_horizontal = ("permissions",)

    class Meta:
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"


# Users: tenant admin + platform backoffice (manager host) so operators can set role SUPERADMIN.
register_both(User, TenantScopedUserAdmin, platform_admin_class=PlatformUserAdmin)
register_tenant_admin(AccessRole, RoleAdmin)
register_tenant_admin(Permission, PermissionAdmin)
register_tenant_admin(TemporaryRoleGrant, TemporaryRoleGrantAdmin)
register_tenant_admin(TenantStaffInvite, TenantStaffInviteAdmin)
register_tenant_admin(Group, GroupAdmin)
register_tenant_admin(UserPreference, UserPreferenceAdmin)
register_tenant_admin(Delegation, DelegationAdmin)
register_tenant_admin(DelegationActionLog, DelegationActionLogAdmin)


class SecurityAuditLogAdmin(ModelAdmin):
    list_display = ("user", "event_type", "ip_address", "is_suspicious", "created_at")
    list_filter = ("event_type", "is_suspicious")
    search_fields = ("user__username", "ip_address")
    raw_id_fields = ("user", "school")
    readonly_fields = (
        "school",
        "user",
        "event_type",
        "ip_address",
        "user_agent",
        "location_data",
        "is_suspicious",
        "initiator",
        "created_at",
        "last_seen",
    )
    date_hierarchy = "created_at"


class UserPasskeyAdmin(ModelAdmin):
    list_display = ("user", "name", "credential_id", "created_at")
    search_fields = ("user__username", "name")
    raw_id_fields = ("user",)


register_tenant_admin(SecurityAuditLog, SecurityAuditLogAdmin)
register_tenant_admin(UserPasskey, UserPasskeyAdmin)


class RelationshipTupleAdmin(ModelAdmin):
    list_display = (
        "school",
        "subject_type",
        "subject_id",
        "relation",
        "object_type",
        "object_id",
        "source",
        "updated_at",
    )
    list_filter = ("relation", "object_type", "source", "school")
    search_fields = ("subject_id", "object_id", "source_key")
    raw_id_fields = ("school",)
    readonly_fields = (
        "school",
        "subject_type",
        "subject_id",
        "relation",
        "object_type",
        "object_id",
        "source",
        "source_key",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


try:
    from apps.accounts.models_rebac import RelationshipTuple

    register_both(RelationshipTuple, RelationshipTupleAdmin)
except ImportError:
    pass
