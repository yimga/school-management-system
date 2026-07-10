"""Tenant-admin registration for the Studio OS Experience module.

Follows the repo idiom (see apps/athletics/admin.py, apps/schoolops/admin.py):
``@admin.register(Model, site=tenant_admin_site)`` with ``list_select_related``
covering the FKs in ``list_display`` so the changelist never N+1s.

``ExperienceRegionApproval`` is an auto-managed proof-before-publish trail: rows
are written by the ``experience_rollout`` service when an operator approves a
region and cleared when they reset it (or when the draft drifts). It is therefore
registered READ-ONLY -- hand-editing a ``draft_fingerprint`` would silently break
the fingerprint-drift semantics the publish gate depends on. This surface exists
to VIEW the trail (who approved which region, when, against which draft), not to
edit it -- a deliberate deviation from the editable athletics admins above.
"""

from django.contrib import admin

from config.admin import tenant_admin_site

from .models import ExperienceRegionApproval


@admin.register(ExperienceRegionApproval, site=tenant_admin_site)
class ExperienceRegionApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "region_key",
        "school",
        "draft_fingerprint",
        "approved_by",
        "approved_at",
    )
    list_filter = ("region_key", "school")
    search_fields = ("region_key", "school__name", "approved_by__username")
    list_select_related = ("school", "approved_by")
    date_hierarchy = "approved_at"
    ordering = ("-approved_at",)
    readonly_fields = (
        "school",
        "region_key",
        "draft_fingerprint",
        "approved_by",
        "approved_at",
    )

    def has_add_permission(self, request):
        # Approvals are minted by the rollout service, never hand-created here.
        return False

    def has_change_permission(self, request, obj=None):
        # View-only trail: every field is read-only; edits could desync the
        # fingerprint the publish gate checks. Changelist/detail stay reachable.
        return False
