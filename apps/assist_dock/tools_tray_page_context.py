"""v4.02.15 — page- and dashboard-aware Tools edge-tray context.

Resolves the current request into a JSON payload the tray JS uses to:
  * render a page header (title, dashboard kind, workflow badge)
  * reorder / hide tool groups per surface + route
  * surface page-scoped quick actions (reuse assist_dock quick_actions)
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.platform_runtime.workflow_guidance import is_visible_for, resolve_workflow_for_route

from .context_processors import _resolve_role, _resolve_surface
from .quick_actions import actions_as_jsonable, actions_for, normalize_workspace_path

logger = logging.getLogger(__name__)

# View names that are operator or tenant *landing* dashboards (not task pages).
_LANDING_VIEW_NAMES = frozenset(
    {
        "super:dashboard",
        "super:founder_dashboard",
        "super:command_center",
        "customersuccess:super_dashboard",
        "accounts:backend_dashboard",
        "portal:teacher_dashboard_alias",
        "evals:teacher_dashboard",
        "portal:parent_dashboard",
        "portal:student_portal_grades",
        "studio_os:shell",
    }
)

_LANDING_PATH_MARKERS = (
    "/super/dashboard",
    "/manager/",
    "/authentication/backend/",
    "/portal/parent/",
    "/portal/teacher/",
    "/portal/student-portal/",
    "/evals/teacher/",
    "/studio/",
)

_VIEW_TITLE_LABELS: dict[str, Any] = {
    "super:dashboard": _("Operator command center"),
    "super:founder_dashboard": _("Founder dashboard"),
    "super:command_center": _("Command center"),
    "accounts:backend_dashboard": _("School backend"),
    "portal:parent_dashboard": _("Family home"),
    "portal:teacher_dashboard_alias": _("Teacher home"),
    "evals:teacher_dashboard": _("Teacher home"),
    "portal:student_portal_grades": _("Student home"),
    "studio_os:shell": _("Studio workspace"),
}

_PATH_SEGMENT_TITLES: tuple[tuple[str, Any], ...] = (
    ("/finance/", _("Finance")),
    ("/payroll/", _("Payroll")),
    ("/compliance/", _("Compliance")),
    ("/super/migration/", _("Migration Cloud")),
    ("/super/schoolops/", _("School operations")),
    ("/siteconfig/", _("Site configuration")),
    ("/admin/", _("Administration")),
)


def _view_name(request) -> str:
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "view_name", None) if match is not None else None
    return str(name or "").strip()


def _page_path(request, override: str = "") -> str:
    if override:
        return normalize_workspace_path(override[:256])
    return normalize_workspace_path(str(getattr(request, "path", "") or "")[:256])


def resolve_dashboard_kind(request, *, view_name: str = "", path: str = "") -> str:
    """Return ``landing`` | ``workspace`` | ``task``."""
    vn = view_name or _view_name(request)
    if vn in _LANDING_VIEW_NAMES:
        return "landing"
    p = (path or _page_path(request)).lower()
    for marker in _LANDING_PATH_MARKERS:
        normalized = marker.rstrip("/")
        if p.rstrip("/").endswith(normalized) or p.rstrip("/") == normalized:
            return "landing"
    archetype = str(getattr(request, "cp_page_archetype", "") or "").strip().lower()
    if archetype in {"decision-console", "operator-command-center"}:
        return "landing"
    if archetype in {"operational-workbench", "task-list", "record-detail"}:
        return "task"
    if "/studio/" in p and "/studio/modes/" not in p:
        return "landing"
    if "/super/" in p or "/manager/" in p or "/admin/" in p:
        return "workspace"
    return "task"


def resolve_page_archetype(request) -> str:
    explicit = str(getattr(request, "cp_page_archetype", "") or "").strip()
    if explicit:
        return explicit
    try:
        from apps.siteconfig.page_personality import resolve_page_personality

        return resolve_page_personality(request)
    except Exception:
        return "default"


def resolve_page_title(request, *, view_name: str = "", workflow_title: str = "") -> str:
    """Page title for the tray header (workflow title is shown separately as a badge)."""
    del workflow_title  # badge-only in JS — do not duplicate as the page title
    vn = view_name or _view_name(request)
    label = _VIEW_TITLE_LABELS.get(vn)
    if label:
        return str(label)
    page_title = str(getattr(request, "cp_page_title", "") or "").strip()
    if page_title:
        return page_title
    p = _page_path(request).lower()
    for prefix, segment_label in _PATH_SEGMENT_TITLES:
        if prefix in p:
            return str(segment_label)
    return _("Current page")


def resolve_group_plan(
    *,
    surface: str,
    dashboard_kind: str,
    workflow_key: str,
    is_tenant: bool,
    archetype: str = "",
    path: str = "",
) -> dict[str, Any]:
    """Return group visibility + order hints for the tray JS."""
    archetype_slug = (archetype or "").lower()
    page_path = (path or "").lower()

    if is_tenant:
        base_order = ["primary", "page", "workspace", "actions"]
        emphasize = ["primary", "page"]
        hide: list[str] = []
        if dashboard_kind == "landing":
            emphasize = ["primary", "page", "workspace"]
        elif workflow_key:
            emphasize = ["primary", "page"]
        if archetype_slug in {"tenant-admin", "django-admin"} or "/admin/" in page_path:
            emphasize = ["page", "workspace", "primary"]
        if page_path.startswith("/finance/") or "finance" in archetype_slug:
            emphasize = ["page", "primary"]
        if workflow_key and dashboard_kind != "landing":
            hide = []
        elif not workflow_key and dashboard_kind == "task":
            # Tenant workflow-progress chip lives in primary; de-emphasize when idle.
            emphasize = ["page", "workspace", "primary"]
        return {
            "order": base_order,
            "hide_groups": hide,
            "emphasize_groups": emphasize,
        }

    # Operator / manager host
    base_order = ["primary", "workflow", "page", "operator", "super", "actions"]
    hide = []
    emphasize = ["primary", "page"]
    if dashboard_kind == "landing":
        emphasize = ["workflow", "operator", "primary"]
    elif workflow_key:
        emphasize = ["workflow", "page", "primary"]
    else:
        hide = ["workflow"]
    if dashboard_kind == "task":
        emphasize = ["page", "primary"]
    if page_path.startswith("/super/migration/"):
        emphasize = ["page", "operator", "primary"]
    if page_path.startswith("/finance/"):
        emphasize = ["page", "primary"]
    return {
        "order": base_order,
        "hide_groups": hide,
        "emphasize_groups": emphasize,
    }


def build_tools_tray_page_payload(request, page_path: str = "") -> dict[str, Any]:
    """Build the page-aware Tools tray payload for SSR + polling."""
    if not getattr(request, "user", None) or not getattr(request.user, "is_authenticated", False):
        return {}

    surface = _resolve_surface(request)
    role = _resolve_role(request)
    path = _page_path(request, page_path)
    view_name = _view_name(request)
    is_tenant = surface == "portal" or getattr(request, "public_host_kind", "") == "tenant"

    workflow = resolve_workflow_for_route(request)
    workflow_key = ""
    workflow_title = ""
    if workflow is not None and is_visible_for(request, workflow):
        workflow_key = workflow.key
        workflow_title = str(workflow.title)

    dashboard_kind = resolve_dashboard_kind(request, view_name=view_name, path=path)
    archetype = resolve_page_archetype(request)
    title = resolve_page_title(request, view_name=view_name, workflow_title=workflow_title)
    groups = resolve_group_plan(
        surface=surface,
        dashboard_kind=dashboard_kind,
        workflow_key=workflow_key,
        is_tenant=is_tenant,
        archetype=archetype,
        path=path,
    )
    quick = actions_for(surface=surface, role=role, page_path=path, limit=6)

    return {
        "path": path,
        "view_name": view_name,
        "title": title,
        "archetype": archetype,
        "dashboard_kind": dashboard_kind,
        "surface": surface,
        "role": role,
        "workflow_key": workflow_key,
        "workflow_title": workflow_title,
        "groups": groups,
        "quick_actions": actions_as_jsonable(quick),
    }


__all__ = [
    "build_tools_tray_page_payload",
    "normalize_workspace_path",
    "resolve_dashboard_kind",
    "resolve_group_plan",
    "resolve_page_archetype",
    "resolve_page_title",
]
