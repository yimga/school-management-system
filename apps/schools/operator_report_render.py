"""Render manager operator report pages on control_plane_base (same chrome as /super/)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
)


def render_manager_report_page(
    request: HttpRequest,
    *,
    body_template: str,
    context: dict[str, Any] | None = None,
    page_title: str = "",
    page_archetype: str = "operator-report",
) -> HttpResponse:
    title = page_title or _("Operator report")
    ctx = dict(context or {})
    ctx.update(
        {
            "operator_cp_title": title,
            "operator_cp_page_archetype": page_archetype,
            "operator_cp_breadcrumbs": default_operator_breadcrumbs(
                operator_cp_breadcrumb(title, active=True),
                include_config_center=False,
            ),
            "operator_cp_body_template": body_template,
        }
    )
    return render(request, "siteconfig/operator_control_plane_page.html", ctx)
