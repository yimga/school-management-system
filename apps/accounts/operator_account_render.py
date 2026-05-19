"""Render account surfaces on the manager control-plane shell when appropriate."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
)
from apps.schools.control_plane import use_control_plane_shell


def render_account_page(
    request: HttpRequest,
    *,
    portal_template: str,
    body_template: str,
    context: dict[str, Any] | None = None,
    page_title: str = "",
) -> HttpResponse:
    """Tenant portal shell vs manager control-plane shell."""
    ctx = dict(context or {})
    if use_control_plane_shell(request):
        title = page_title or _("Account")
        return render_siteconfig_operator_page(
            request,
            portal_template=portal_template,
            body_template=body_template,
            context=ctx,
            cp_title=title,
            cp_page_archetype="operational-workbench",
            breadcrumbs=default_operator_breadcrumbs(
                operator_cp_breadcrumb(title, active=True),
                include_config_center=False,
            ),
        )
    return render(request, portal_template, ctx)
