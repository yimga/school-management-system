"""Operator-only console to grant / revoke PLATFORM superadmin (``is_superuser``).

This is the ONE place a user is made a true Django superuser — god-mode across the
whole platform. It is deliberately distinct from:

* the tenant RBAC console (``accounts.rbac_dashboard``), which writes only
  school-scoped AccessRole grants and must never mint platform god-mode, and
* the operator-TEAM roster (``super_views_operator_team``), which manages
  PlatformOperatorProfile tiers.

Reachable only on the control-plane surface (manager host / ``/super/``) via
``require_super_access_with_host``. The mint/revoke action ADDITIONALLY requires the
actor to already be ``is_superuser`` — only a superuser can make a superuser, so a
lower-tier control-plane operator cannot self-escalate. The change propagates in
real time (``apply_superadmin_change`` -> the User post_save access-realtime signal
pushes ``access_changed`` to the target's open session).
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.superadmin_service import apply_superadmin_change
from apps.schools.control_plane import require_super_access_with_host

logger = logging.getLogger("security.superadmin_promotion")

User = get_user_model()

_SEARCH_LIMIT = 25
_SUPERADMIN_LIST_LIMIT = 100  # magic-number-allow: operator-console-superadmin-list-display-cap


def _serialize(u) -> dict:
    return {
        "pk": u.pk,
        "username": u.get_username(),
        "email": u.email or "",
        "is_superuser": u.is_superuser,
        "is_staff": u.is_staff,
        "role": getattr(u, "role", ""),
        "is_active": u.is_active,
    }


@require_super_access_with_host
@require_http_methods(["GET", "POST"])
def super_superadmin_console(request):
    console_url = reverse("super:superadmin_console")

    if request.method == "POST":
        # Minting god-mode is superuser-only: only a superuser can make a superuser.
        if not getattr(request.user, "is_superuser", False):
            return HttpResponseForbidden(
                "Only an existing platform superuser may grant or revoke superadmin."
            )
        action = (request.POST.get("action") or "").strip()
        target_pk = (request.POST.get("user_id") or "").strip()
        # tenant-isolation-allow: control-plane-operator-manages-platform-wide-identities
        target = User.objects.filter(pk=target_pk).first() if target_pk else None
        if target is None:
            messages.error(request, "User not found.")
            return redirect(console_url)
        if action == "promote":
            changes = apply_superadmin_change(target, actor=request.user)
            messages.success(
                request,
                (
                    f"{target.get_username()} is now a platform superadmin."
                    if changes
                    else f"{target.get_username()} was already a platform superadmin."
                ),
            )
        elif action == "demote":
            if target.pk == request.user.pk:
                messages.error(
                    request, "You cannot revoke your own superadmin from here."
                )
                return redirect(console_url)
            changes = apply_superadmin_change(target, actor=request.user, demote=True)
            messages.success(
                request,
                (
                    f"Platform superadmin revoked for {target.get_username()}."
                    if changes
                    else f"{target.get_username()} was not a platform superadmin."
                ),
            )
        else:
            messages.error(request, "Unknown action.")
        return redirect(console_url)

    query = (request.GET.get("q") or "").strip()
    results = []
    if query:
        # tenant-isolation-allow: control-plane-operator-manages-platform-wide-identities
        matches = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        ).order_by("username")[:_SEARCH_LIMIT]
        results = [_serialize(u) for u in matches]
    # tenant-isolation-allow: control-plane-operator-manages-platform-wide-identities
    current = User.objects.filter(is_superuser=True).order_by("username")[
        :_SUPERADMIN_LIST_LIMIT
    ]
    ctx = {
        "dashboard_url": reverse("super:dashboard"),
        "console_url": console_url,
        "query": query,
        "results": results,
        "current_superadmins": [_serialize(u) for u in current],
        "can_mint": bool(getattr(request.user, "is_superuser", False)),
    }
    return render(request, "schools/super_superadmin_console.html", ctx)
