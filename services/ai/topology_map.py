"""
SYSTEM_TOPOLOGY_MAP — curated + reflected routes for permission-aware command bar.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import NoReverseMatch, reverse

from services.ai.reflection import DynamicSystemInspector

logger = logging.getLogger(__name__)

# Stable platform anchors (linked to AI Center + gateway console).
_CURATED: tuple[dict[str, Any], ...] = (
    {
        "id": "ai_center",
        "label": "AI Center",
        "path_label": "**Platform > AI Center**",
        "keywords": "ai assistant copilot chat domain help center",
        "url_name": "siteconfig:ai_center",
        "required_permissions": ["login_required"],
        "kind": "navigate",
    },
    {
        "id": "ai_gateway_console",
        "label": "AI Gateway Console",
        "path_label": "**Control Plane > AI Gateway Console**",
        "keywords": "ai gateway console operator metrics ollama audit",
        "url_name": "super:ai_gateway_console",
        "required_permissions": ["staff_required"],
        "kind": "navigate",
    },
    {
        "id": "help_center",
        "label": "Help Center",
        "path_label": "**Support > Help Center**",
        "keywords": "help support documentation kb faq",
        "url_name": "feedback:help_center",
        "required_permissions": ["login_required"],
        "kind": "navigate",
    },
    {
        "id": "first_line_support",
        "label": "First-line support (engine room)",
        "path_label": "**Support > AI Center > First-line support**",
        "keywords": "support assistant how to workflow steps escalate helpdesk",
        "url_name": "siteconfig:ai_center",
        "url_query": "?assistant=first_line_support",
        "required_permissions": ["login_required"],
        "kind": "documentation",
    },
    {
        "id": "admissions_enrollment",
        "label": "Admissions — new enrollment",
        "path_label": "**Admissions > Student Roster**",
        "keywords": "admissions enrollment new student roster commit records registrar",
        "url_name": "siteconfig:onboarding",
        "required_permissions": ["login_required"],
        "kind": "navigate",
    },
    {
        "id": "finance_invoices",
        "label": "Finance — invoices",
        "path_label": "**Finance > Billing > Invoices**",
        "keywords": "finance billing invoices fees tuition payments ledger",
        "required_permissions": ["login_required", "feature:finance.view"],
        "kind": "navigate",
    },
    {
        "id": "site_settings",
        "label": "Site settings & branding",
        "path_label": "**Configure > Site settings**",
        "keywords": "settings branding theme siteconfig feature flags configuration",
        "url_name": "siteconfig:onboarding",
        "required_permissions": ["login_required", "feature:settings.manage"],
        "kind": "navigate",
    },
    {
        "id": "data_import",
        "label": "Bulk data import",
        "path_label": "**Data > Imports**",
        "keywords": "import csv bulk upload validation errors spreadsheet migration",
        "required_permissions": ["login_required"],
        "kind": "navigate",
    },
    {
        "id": "studio_os",
        "label": "Studio OS",
        "path_label": "**Studio OS**",
        "keywords": "studio workflow design pages builder",
        "required_permissions": ["login_required"],
        "kind": "navigate",
    },
    {
        "id": "smart_settings_ai",
        "label": "Smart settings assistant",
        "path_label": "**AI Center > Smart settings**",
        "keywords": "settings assistant configure siteconfig runtime defaults",
        "url_name": "siteconfig:ai_center",
        "url_query": "?assistant=smart_settings",
        "required_permissions": ["login_required", "feature:settings.manage"],
        "kind": "documentation",
    },
    {
        "id": "import_resolver_ai",
        "label": "Import error resolver",
        "path_label": "**AI Center > Import error resolver**",
        "keywords": "import validation errors csv fix rows bulk",
        "url_name": "siteconfig:ai_center",
        "url_query": "?assistant=import_resolver",
        "required_permissions": ["login_required"],
        "kind": "documentation",
    },
    {
        "id": "guided_tour_ai",
        "label": "Guided tour planner",
        "path_label": "**AI Center > Guided tours**",
        "keywords": "onboarding tour walkthrough setup guided",
        "url_name": "siteconfig:ai_center",
        "url_query": "?assistant=guided_tour",
        "required_permissions": ["login_required"],
        "kind": "documentation",
    },
)


def _reverse_url(url_name: str, *, query: str = "") -> str | None:
    try:
        base = reverse(url_name)
        return (base + query) if query else base
    except NoReverseMatch:
        return None


def _assistant_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        from apps.siteconfig.ai_assistants import iter_assistants

        for assistant in iter_assistants():
            key = assistant.get("assistant_key") or ""
            label = assistant.get("label") or key
            perms = ["login_required"]
            req = assistant.get("required_permission")
            if req:
                perms.append(f"feature:{req}")
            entry_urls = []
            for url_name in assistant.get("entry_url_names") or ():
                url = _reverse_url(url_name)
                if url:
                    entry_urls.append(url)
            api_name = assistant.get("api_url_name")
            rows.append(
                {
                    "id": f"assistant:{key}",
                    "label": label,
                    "path_label": f"**AI Center > {label}**",
                    "keywords": f"{key} {label} {assistant.get('domain', '')} {assistant.get('hint', '')}",
                    "url": _reverse_url("siteconfig:ai_center", query=f"?assistant={key}"),
                    "required_permissions": perms,
                    "kind": "navigate",
                    "assistant_key": key,
                    "api_url_name": api_name,
                }
            )
    except ImportError:
        pass
    return rows


def _reflected_entries(*, limit: int = 400) -> list[dict[str, Any]]:
    inspector = DynamicSystemInspector()
    rows: list[dict[str, Any]] = []
    for route in inspector.get_route_registry()[:limit]:
        path = route.get("url_path") or ""
        if not path or "<" in path:
            continue
        name = route.get("name") or path
        perms = list(route.get("required_permissions") or [])
        if not perms:
            perms = ["login_required"]
        rows.append(
            {
                "id": f"route:{name or path}",
                "label": (name or path).replace("_", " ").title()[:80],
                "path_label": f"**Route > {path}**",
                "keywords": f"{name} {path}",
                "url": path,
                "required_permissions": perms,
                "kind": "navigate",
            }
        )
    return rows


def build_system_topology_map(*, include_reflected: bool = True) -> list[dict[str, Any]]:
    """Full topology list (not filtered by user)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: dict[str, Any]) -> None:
        eid = str(entry.get("id") or "")
        if not eid or eid in seen:
            return
        seen.add(eid)
        if entry.get("url_name") and not entry.get("url"):
            entry = dict(entry)
            entry["url"] = _reverse_url(
                entry["url_name"],
                query=str(entry.get("url_query") or ""),
            )
        out.append(entry)

    for row in _CURATED:
        add(dict(row))
    for row in _assistant_entries():
        add(row)
    if include_reflected:
        for row in _reflected_entries():
            add(row)
    return out


def _user_has_feature_permission(user: Any, perm: str) -> bool:
    try:
        return bool(user.has_feature_permission(perm))
    except Exception:
        return False


def user_can_access_entry(
    user: Any,
    entry: dict[str, Any],
    *,
    school: Any | None = None,
) -> tuple[bool, str | None]:
    """
    Return (allowed, missing_permission_label).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False, "login_required"

    perms = list(entry.get("required_permissions") or ["login_required"])
    if getattr(user, "is_superuser", False):
        return True, None

    try:
        from apps.schools.control_plane import user_has_control_plane_access

        if user_has_control_plane_access(user):
            return True, None
    except ImportError:
        pass

    missing: list[str] = []
    for token in perms:
        if token == "login_required":
            continue
        if token == "staff_required":
            if not getattr(user, "is_staff", False):
                missing.append("IS_STAFF")
            continue
        if token.startswith("feature:"):
            feat = token.split(":", 1)[1]
            if not _user_has_feature_permission(user, feat):
                missing.append(f"feature:{feat}")
            continue
        if token.startswith("drf:"):
            if not getattr(user, "is_staff", False):
                missing.append(token)
            continue

    if missing:
        return False, missing[0]
    return True, None


def _score_entry(entry: dict[str, Any], query: str) -> int:
    if not query:
        return 1
    q = query.lower().strip()
    hay = " ".join(
        [
            str(entry.get("label") or ""),
            str(entry.get("keywords") or ""),
            str(entry.get("path_label") or ""),
        ]
    ).lower()
    if q not in hay:
        return 0
    label = str(entry.get("label") or "").lower()
    if label.startswith(q):
        return 4
    if q in label:
        return 3
    return 2


def search_topology(
    user: Any,
    query: str,
    *,
    school: Any | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Permission-filtered search results for the command bar."""
    q = (query or "").strip()
    results: list[dict[str, Any]] = []
    for entry in build_system_topology_map():
        score = _score_entry(entry, q) if q else (1 if entry.get("id", "").startswith("ai_") else 0)
        if q and score <= 0:
            continue
        allowed, missing = user_can_access_entry(user, entry, school=school)
        url = entry.get("url")
        row = {
            "id": entry.get("id"),
            "label": entry.get("label"),
            "path_label": entry.get("path_label"),
            "kind": entry.get("kind", "navigate"),
            "url": url if allowed and url else None,
            "locked": not allowed,
            "missing_permission": missing,
            "assistant_key": entry.get("assistant_key"),
            "score": score,
        }
        results.append(row)
    results.sort(key=lambda r: (-int(r.get("score") or 0), str(r.get("label") or "")))
    return results[:limit]
