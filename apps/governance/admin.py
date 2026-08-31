from django.contrib import admin

from apps.governance.models import (
    GovernanceNode,
    Organization,
    OrgMembership,
    SchoolContextProfile,
)
from config.admin import register_platform_admin


# Every model here was on Django's DEFAULT admin.site -- three via a bare
# admin.site.register(Model) with no ModelAdmin at all -- and no urlconf in
# this repo mounts that site, so an operator had no way to reach any of
# them. apps.governance is in SHARED_APPS and has no model on either real
# site, so there is no in-app convention to follow.
#
# All four go to the OPERATOR. An Organization groups SCHOOLS, a
# GovernanceNode is a node in that cross-school tree, an OrgMembership
# places a user in it, and a SchoolContextProfile exists precisely to let
# one user switch BETWEEN schools. Scoping any of them to a single tenant
# would hide the relationships that are the whole point of the model.
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "legal_owner_type", "is_active", "updated_at")
    list_filter = ("legal_owner_type", "is_active")
    search_fields = ("name", "slug")
    ordering = ("name",)


class GovernanceNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "organization", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "organization__name")
    raw_id_fields = ("organization", "parent")
    ordering = ("organization__name", "name")


class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_primary", "created_at")
    list_filter = ("role", "is_primary")
    search_fields = ("user__username", "organization__name")
    raw_id_fields = ("user", "organization")
    ordering = ("organization__name", "user__username")


class SchoolContextProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "context_key", "role", "is_default")
    list_filter = ("role", "is_default")
    search_fields = ("user__username", "school__name", "context_key", "label")


register_platform_admin(Organization, OrganizationAdmin)
register_platform_admin(GovernanceNode, GovernanceNodeAdmin)
register_platform_admin(OrgMembership, OrgMembershipAdmin)
register_platform_admin(SchoolContextProfile, SchoolContextProfileAdmin)
