"""Tenant-facing Group Console (Phase 4A — opt-in, hidden for standalone)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.governance.services import KNOWN_INHERIT_DOMAINS
from apps.schools.group_console import (
    apply_group_upgrade,
    build_group_console_context,
    group_console_visible,
)


def _group_console_url() -> str | None:
    try:
        return reverse("siteconfig:group_console")
    except NoReverseMatch:
        return None


@login_required
@permission_required("settings.manage", raise_exception=True)
@require_http_methods(["GET"])
def group_console(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("No school context.")
    if not group_console_visible(school):
        return HttpResponseForbidden(
            "Group Console is available only for schools in organization group mode."
        )

    context = build_group_console_context(school, request.user)
    members = context.get("member_schools") or []
    page_obj = Paginator(members, 20).get_page(request.GET.get("page") or 1)
    q = request.GET.copy()
    q.pop("page", None)
    context.update(
        {
            "page_title": "Group Console",
            "school": school,
            "member_schools": list(page_obj.object_list),
            "page_obj": page_obj,
            "pagination_extra_query": q.urlencode(),
            "upgrade_wizard_url": reverse("siteconfig:group_console_upgrade"),
            "hierarchy_url": _safe_reverse("siteconfig:school_group_hierarchy"),
        }
    )
    return render(request, "schools/group_console.html", context)


@login_required
@permission_required("settings.manage", raise_exception=True)
@require_http_methods(["GET", "POST"])
def group_console_upgrade(request: HttpRequest) -> HttpResponse:
    """Join / create group upgrade wizard — links school to an Organization."""
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden("No school context.")
    if group_console_visible(school):
        return redirect("siteconfig:group_console")

    from apps.governance.models import Organization

    organizations = Organization.objects.filter(is_active=True).order_by("name")

    if request.method == "POST":
        org_id = (request.POST.get("organization_id") or "").strip()
        inherit_map = {}
        for domain in KNOWN_INHERIT_DOMAINS:
            raw = (request.POST.get(f"inherit_{domain}") or "local").strip().lower()
            if raw in {"inherit", "local", "hybrid"}:
                inherit_map[domain] = raw
        try:
            apply_group_upgrade(school, organization_id=org_id, inherit_map=inherit_map)
        except ValueError:
            messages.error(request, "Organization not found or inactive.")
        else:
            messages.success(request, "School joined the organization group.")
            return redirect("siteconfig:group_console")

    return render(
        request,
        "schools/group_console_upgrade.html",
        {
            "page_title": "Join organization group",
            "school": school,
            "organizations": organizations,
            "known_domains": sorted(KNOWN_INHERIT_DOMAINS),
        },
    )


def _safe_reverse(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def group_console_url_for_school(school) -> str | None:
    """Return Group Console URL when visible; otherwise None (standalone UX)."""
    if not group_console_visible(school):
        return None
    return _group_console_url()
