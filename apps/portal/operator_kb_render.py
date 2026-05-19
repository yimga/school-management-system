"""Knowledge Base on manager host — control-plane shell (not tenant portal_base)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.portal.kb_context import is_operator_help_request
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
)


def render_operator_kb_page(
    request: HttpRequest,
    *,
    body_template: str,
    context: dict[str, Any] | None = None,
    page_title: str = "",
    breadcrumb_tail: list[dict[str, Any]] | None = None,
) -> HttpResponse:
    title = page_title or _("Knowledge base")
    try:
        help_center_url = reverse("manager_help_center")
    except Exception:
        help_center_url = reverse("kb:kb_home")
    crumbs = default_operator_breadcrumbs(
        operator_cp_breadcrumb(_("Help center"), url=help_center_url),
        operator_cp_breadcrumb(title, active=not breadcrumb_tail),
        include_config_center=False,
    )
    if breadcrumb_tail:
        crumbs = crumbs[:-1] + breadcrumb_tail
        if crumbs and not crumbs[-1].get("active"):
            crumbs[-1] = {**crumbs[-1], "active": True, "url": None}

    ctx = dict(context or {})
    ctx.setdefault("is_operator_help", True)
    return render_siteconfig_operator_page(
        request,
        portal_template="portal/kb_home.html",
        body_template=body_template,
        context=ctx,
        cp_title=title,
        cp_page_archetype="operational-workbench",
        breadcrumbs=crumbs,
    )


def render_kb_if_operator(
    request: HttpRequest,
    *,
    portal_template: str,
    operator_body_template: str,
    context: dict[str, Any] | None = None,
    page_title: str = "",
    breadcrumb_tail: list[dict[str, Any]] | None = None,
) -> HttpResponse:
    """Tenant portal template vs operator control-plane body."""
    from django.shortcuts import render

    if is_operator_help_request(request):
        return render_operator_kb_page(
            request,
            body_template=operator_body_template,
            context=context,
            page_title=page_title,
            breadcrumb_tail=breadcrumb_tail,
        )
    return render(request, portal_template, context or {})
