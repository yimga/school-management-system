"""
Manager-host operator pages: portal shell on tenant, control_plane_base on manager.

See docs/PLATFORM_ADMIN_TO_SUPER_SYSTEM_CONFIG.md and console_domains_hub pattern.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.schools.control_plane import use_control_plane_shell


def operator_cp_breadcrumb(
    label: str,
    *,
    url: str | None = None,
    active: bool = False,
) -> dict[str, Any]:
    return {"label": label, "url": url, "active": active}


def default_operator_breadcrumbs(
    *tail: dict[str, Any],
    include_config_center: bool = True,
) -> list[dict[str, Any]]:
    from django.urls import reverse

    crumbs: list[dict[str, Any]] = []
    if include_config_center:
        try:
            crumbs.append(
                operator_cp_breadcrumb(
                    "Config center",
                    url=reverse("siteconfig:console_domains_hub"),
                )
            )
        except Exception:
            pass
    crumbs.extend(tail)
    if crumbs and not crumbs[-1].get("active"):
        crumbs[-1] = {**crumbs[-1], "active": True, "url": None}
    return crumbs


def render_siteconfig_stem(
    request: HttpRequest,
    stem: str,
    context: dict[str, Any] | None = None,
    *,
    cp_title: str = "",
    cp_meta_description: str = "",
    cp_page_archetype: str = "decision-console",
    breadcrumbs: list[dict[str, Any]] | None = None,
    manager_body_template: str | None = None,
) -> HttpResponse:
    """``stem`` → ``siteconfig/{stem}.html`` + ``siteconfig/partials/{stem}_body.html``."""
    return render_siteconfig_operator_page(
        request,
        portal_template=f"siteconfig/{stem}.html",
        body_template=f"siteconfig/partials/{stem}_body.html",
        context=context,
        cp_title=cp_title,
        cp_meta_description=cp_meta_description,
        cp_page_archetype=cp_page_archetype,
        breadcrumbs=breadcrumbs,
        manager_body_template=manager_body_template,
    )


def render_siteconfig_operator_page(
    request: HttpRequest,
    *,
    portal_template: str,
    body_template: str,
    context: dict[str, Any] | None = None,
    cp_title: str = "",
    cp_meta_description: str = "",
    cp_page_archetype: str = "decision-console",
    breadcrumbs: list[dict[str, Any]] | None = None,
    manager_body_template: str | None = None,
) -> HttpResponse:
    """
    Tenant: ``portal_template`` (must ``{% include body_template %}`` in content block).
    Manager: ``siteconfig/operator_control_plane_page.html`` + body partial
    (``manager_body_template`` when manager layout differs from tenant).
    """
    ctx = dict(context or {})
    if use_control_plane_shell(request):
        meta = (cp_meta_description or "").strip() or (
            f"RunMyCampus manager — {cp_title}" if cp_title else ""
        )
        ctx.update(
            {
                "operator_cp_title": cp_title,
                "operator_cp_meta_description": meta,
                "operator_cp_page_archetype": cp_page_archetype,
                "operator_cp_breadcrumbs": breadcrumbs or [],
                "operator_cp_body_template": manager_body_template or body_template,
                "ai_center_shell": "control-plane",
                "og_title": f"{cp_title} — RunMyCampus Manager" if cp_title else None,
                "seo_description": meta,
            }
        )
        return render(request, "siteconfig/operator_control_plane_page.html", ctx)
    return render(request, portal_template, ctx)
