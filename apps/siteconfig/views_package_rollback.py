"""
N20: Tenant-facing rollback for applied metadata packages (PackageEngine.rollback).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from django.contrib.auth import get_user_model

from apps.marketplace.ecosystem_links import build_phase9_ecosystem_links
from apps.packages.engine import rollback as package_rollback
from apps.packages.models import InstalledPackage, PackageChangeLog

User = get_user_model()


def _rollback_roles_ok(user) -> bool:
    from apps.siteconfig.tenant_experience_policy import (
        user_may_manage_backend_config,
    )

    return user_may_manage_backend_config(user)


@login_required
@require_http_methods(["GET", "POST"])
def tenant_installed_packages_rollback(request):
    """
    List active InstalledPackage rows for the tenant; POST rolls back one package
    after typing ROLLBACK (impact acknowledgment).
    """
    school = getattr(request, "school", None)
    if not school:
        messages.warning(
            request,
            _("Select a school context to manage package rollbacks."),
        )
        return redirect("siteconfig:user_preferences")
    if not _rollback_roles_ok(request.user):
        return HttpResponseForbidden(
            _("You do not have permission to roll back metadata packages.")
        )

    if request.method == "POST":
        iid = (request.POST.get("installed_id") or "").strip()
        ack = (request.POST.get("confirm_rollback") or "").strip()
        if ack != "ROLLBACK":
            messages.error(
                request,
                _("Type ROLLBACK in the confirmation field to acknowledge impact."),
            )
        elif iid.isdigit():
            inst = get_object_or_404(
                InstalledPackage.objects.filter(
                    school_id=school.pk, is_active=True
                ),
                pk=int(iid),
            )
            try:
                package_rollback(inst, actor_id=request.user.pk)
                messages.success(
                    request,
                    _(
                        "Rolled back %(pkg)s@%(ver)s. "
                        "Runtime may still reflect cached config until refresh."
                    )
                    % {"pkg": inst.package_id, "ver": inst.version},
                )
            except Exception as e:
                messages.error(
                    request,
                    _("Rollback failed: %(err)s") % {"err": e},
                )
        return redirect("siteconfig:installed_packages_rollback")

    active = list(
        InstalledPackage.objects.filter(school_id=school.pk, is_active=True)
        .exclude(apply_stage="rollback")
        .order_by("-applied_at")[:100]
    )
    history = list(
        PackageChangeLog.objects.filter(school_id=school.pk, action="rollback")
        .order_by("-created_at")[:30]
    )
    package_activity = list(
        PackageChangeLog.objects.filter(school_id=school.pk).order_by("-created_at")[
            :100
        ]
    )
    actor_ids = {row.actor_id for row in package_activity if row.actor_id}
    users_by_id = User.objects.in_bulk(actor_ids) if actor_ids else {}
    actor_labels = {}
    for uid in actor_ids:
        u = users_by_id.get(uid)
        actor_labels[uid] = (
            (u.get_full_name() or u.username) if u else _("User #%s") % uid
        )
    activity_display = [
        {
            "log": row,
            "actor_label": actor_labels.get(row.actor_id, "—")
            if row.actor_id
            else "—",
        }
        for row in package_activity
    ]
    try:
        package_impact_fetch_url = reverse("api:api-north-star-package-impact")
    except NoReverseMatch:
        package_impact_fetch_url = "/api/internal/north-star/package-impact/"
    return render(
        request,
        "siteconfig/installed_packages_rollback.html",
        {
            "school": school,
            "active_packages": active,
            "rollback_history": history,
            "activity_display": activity_display,
            "modules_url": reverse("siteconfig:module_market"),
            "package_impact_api_path": "/api/internal/north-star/package-impact/",
            "package_impact_fetch_url": package_impact_fetch_url,
            "phase9_links": build_phase9_ecosystem_links(),
        },
    )
