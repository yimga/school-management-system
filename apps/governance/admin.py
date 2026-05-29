from django.contrib import admin

from apps.governance.models import (
    GovernanceNode,
    Organization,
    OrgMembership,
    SchoolContextProfile,
)

admin.site.register(Organization)
admin.site.register(GovernanceNode)
admin.site.register(OrgMembership)


@admin.register(SchoolContextProfile)
class SchoolContextProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "context_key", "role", "is_default")
    list_filter = ("role", "is_default")
    search_fields = ("user__username", "school__name", "context_key", "label")
