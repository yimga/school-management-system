"""Tenant-facing "no data to migrate / start fresh" waiver controls (2026-08-09).

The reverse path for the onboarding-waiver primitive: a school admin who chose
"we'll migrate data" but then found they have none — or a brand-new school with
nothing to import — can declare it here, clearing the relevant onboarding
pending state / launch blocker, and can reverse the decision at any time.

Gated to the tenant-admin tier for the school in request context
(``tenant_admin_required``), so a teacher / parent / student cannot flip a
launch decision, and the branded tenant 403 renders on denial.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import tenant_admin_required
from apps.schools import onboarding_waiver as ow

logger = logging.getLogger(__name__)

_TEMPLATE = "setup_studio/onboarding_data_options.html"
_REDIRECT_NAME = "setup_studio:onboarding_data_options"

_DEFAULT_REASON = {
    ow.WAIVER_MIGRATION: ow.REASON_NO_LEGACY_DATA,
    ow.WAIVER_ROSTER: ow.REASON_NO_STUDENTS_YET,
}


@tenant_admin_required
@require_http_methods(["GET", "POST"])
def onboarding_data_options(request):
    """Show and toggle the migration / roster onboarding waivers for this school."""
    school = getattr(request, "school", None)
    if school is None:
        messages.error(request, _("No school is in context for this request."))
        return redirect("accounts:backend_dashboard")

    if request.method == "POST":
        kind = (request.POST.get("kind") or "").strip()
        action = (request.POST.get("action") or "").strip()
        note = (request.POST.get("note") or "").strip()
        if kind not in ow.WAIVER_KINDS or action not in {"waive", "unwaive"}:
            messages.error(request, _("Unrecognized request."))
            return redirect(_REDIRECT_NAME)
        if action == "waive":
            ow.waive(
                school,
                kind,
                actor=request.user,
                reason=_DEFAULT_REASON.get(kind, ""),
                note=note,
            )
            if kind == ow.WAIVER_MIGRATION:
                messages.success(
                    request,
                    _("Marked as no data to migrate. You can start an import anytime."),
                )
            else:
                messages.success(
                    request,
                    _("You can launch with no students yet. Add your roster anytime."),
                )
        else:
            ow.unwaive(school, kind, actor=request.user)
            if kind == ow.WAIVER_MIGRATION:
                messages.success(request, _("Re-opened data migration for this school."))
            else:
                messages.success(request, _("A roster is required again before launch."))
        return redirect(_REDIRECT_NAME)

    context = {
        "school": school,
        "migration": ow.get_waiver(school, ow.WAIVER_MIGRATION),
        "roster": ow.get_waiver(school, ow.WAIVER_ROSTER),
        "migration_waived": ow.migration_waived(school),
        "roster_waived": ow.roster_waived(school),
    }
    return render(request, _TEMPLATE, context)
