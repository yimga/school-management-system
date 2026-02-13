"""
Dashboard action registry: single source of truth for primary / chip / grid / quick-link
and command-palette actions per dashboard. Prevents duplicate CTAs and keeps action
hierarchy (primary vs secondary vs overflow) consistent.

Each entry: label, icon, url_name, fallback_url_name (optional), item_id (optional),
allow_key (optional; key into perms dict, e.g. "can_manage_settings"). If allow_key
is missing, the action is shown for all users who see the dashboard.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Backend dashboard: primary CTAs in Overview head (no allow_key = always show)
BACKEND_PRIMARY_CTAS = [
    {"label": "Manage Staff", "icon": "bi-person-gear", "url_name": "accounts:backend_teacher_list", "fallback_url_name": "accounts:backend_dashboard"},
    {"label": "School Settings", "icon": "bi-building-gear", "url_name": "siteconfig:customizer", "fallback_url_name": "siteconfig:user_preferences"},
]

BACKEND_ACTION_CHIPS = [
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "allow_key": "always"},
    {"label": "Messages", "icon": "bi-chat-dots", "url_name": "accounts:user_messages", "allow_key": "can_use_messages"},
    {"label": "Report Card Builder", "icon": "bi-file-earmark-richtext", "url_name": "siteconfig:reportcard_builder", "allow_key": "can_manage_reports"},
    {"label": "My Preferences", "icon": "bi-sliders", "url_name": "siteconfig:user_preferences", "allow_key": "always"},
    {"label": "Configuration Engine", "icon": "bi-gear-wide-connected", "url_name": "admin:index", "allow_key": "can_manage_settings"},
]

BACKEND_WELCOME_ACTION_GRID = [
    {"label": "Add Student", "icon": "bi-person-plus", "url_name": "accounts:backend_student_create", "fallback_url_name": "admin:index", "item_id": "add_student", "allow_key": "can_manage_people"},
    {"label": "Add Teacher", "icon": "bi-person-badge", "url_name": "accounts:backend_teacher_create", "fallback_url_name": "admin:index", "item_id": "add_teacher", "allow_key": "can_manage_people"},
    {"label": "Onboard Student", "icon": "bi-mortarboard", "url_name": "portal:student_onboarding", "item_id": "onboard_student", "allow_key": "can_manage_people"},
    {"label": "Create Invoice", "icon": "bi-receipt", "url_name": "finance:dashboard", "item_id": "create_invoice", "allow_key": "can_manage_finance"},
    {"label": "Manage Exams", "icon": "bi-journal-text", "url_name": "reports:publish_term_results", "item_id": "manage_exams", "allow_key": "can_manage_reports"},
    {"label": "Announcements", "icon": "bi-megaphone", "url_name": "communication:announcement_create", "item_id": "announcements", "allow_key": "can_use_messages"},
    {"label": "Roles & Permissions", "icon": "bi-shield-lock", "url_name": "accounts:rbac", "item_id": "roles_permissions", "allow_key": "can_manage_rbac"},
    {"label": "Document Library", "icon": "bi-folder2-open", "url_name": "portal:document_library_manage", "item_id": "document_library", "allow_key": "can_manage_settings"},
]

BACKEND_QUICK_LINKS = [
    {"label": "Import Grades", "icon": "bi-upload", "url_name": "evals:grade_import_upload", "item_id": "import_grades", "allow_key": "can_manage_reports"},
    {"label": "Exams", "icon": "bi-journal-check", "url_name": "reports:publish_term_results", "item_id": "exams", "allow_key": "can_manage_reports"},
    {"label": "Certification", "icon": "bi-award", "url_name": "accounts:certification_home", "item_id": "certification", "allow_key": "can_manage_reports"},
    {"label": "Documents", "icon": "bi-folder2", "url_name": "portal:document_library_manage", "item_id": "documents", "allow_key": "can_manage_settings"},
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "item_id": "workflow_center", "allow_key": "always"},
    {"label": "Preferences", "icon": "bi-sliders", "url_name": "siteconfig:user_preferences", "item_id": "preferences", "allow_key": "always"},
]

BACKEND_COMMAND_PALETTE = [
    {"label": "Add Student", "icon": "bi-person-plus", "url_name": "accounts:backend_student_create", "fallback_url_name": "admin:index", "allow_key": "can_manage_people"},
    {"label": "Manage Staff", "icon": "bi-people", "url_name": "accounts:backend_teacher_list", "fallback_url_name": "accounts:backend_dashboard", "allow_key": "can_manage_people"},
    {"label": "Manage Exams", "icon": "bi-journal-check", "url_name": "reports:publish_term_results", "allow_key": "can_manage_reports"},
    {"label": "Import Grades", "icon": "bi-upload", "url_name": "evals:grade_import_upload", "allow_key": "can_manage_reports"},
    {"label": "Finance Dashboard", "icon": "bi-cash-stack", "url_name": "finance:dashboard", "allow_key": "can_manage_finance"},
    {"label": "School Settings", "icon": "bi-building-gear", "url_name": "siteconfig:customizer", "fallback_url_name": "siteconfig:user_preferences", "allow_key": "can_manage_settings"},
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "allow_key": "always"},
]

# Admin dashboard (obs): header actions only; single Customizer entry to avoid duplicate CTAs
ADMIN_HEADER_ACTIONS = [
    {"label": "My Preferences", "url_name": "siteconfig:user_preferences", "fallback_url_name": "admin:index", "css_class": "admin-dash__header-action", "append_next": True},
    {"label": "Backend Console", "url_name": "accounts:backend_dashboard", "fallback_url_name": "admin:index", "css_class": "admin-dash__header-action"},
    {"label": "Customizer", "url_name": "siteconfig:customizer", "fallback_url_name": "siteconfig:user_preferences", "css_class": "admin-dash__header-action admin-dash__header-action--primary"},
]


def _resolve_actions(
    specs: List[Dict[str, Any]],
    perms: Dict[str, bool],
    safe_reverse: Callable[[str, str], str],
    build_nav_item: Callable[..., Optional[Dict[str, str]]],
    dedupe: Callable[[List[Dict[str, str]]], List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for s in specs:
        allow = perms.get(s.get("allow_key", "always"), True) if s.get("allow_key") != "always" else True
        url = safe_reverse(s["url_name"], s.get("fallback_url_name", "#"))
        item = build_nav_item(
            s["label"],
            s["icon"],
            url,
            item_id=s.get("item_id", ""),
            allow=allow,
        )
        if item:
            out.append(item)
    return dedupe(out)


def get_backend_dashboard_actions(
    perms: Dict[str, bool],
    safe_reverse: Callable[[str, str], str],
    build_nav_item: Callable[..., Optional[Dict[str, str]]],
    dedupe_nav_items: Callable[[List[Dict[str, str]]], List[Dict[str, str]]],
) -> Dict[str, List[Dict[str, str]]]:
    """Resolve backend dashboard actions from the registry. perms must contain can_manage_settings, can_manage_people, can_manage_finance, can_manage_reports, can_use_messages, can_manage_rbac."""
    def safe(name: str, fallback: str = "#") -> str:
        return safe_reverse(name, fallback)

    primary_ctas = [
        {"label": s["label"], "icon": s["icon"], "url": safe(s["url_name"], s.get("fallback_url_name", "#"))}
        for s in BACKEND_PRIMARY_CTAS
    ]
    action_chips = _resolve_actions(BACKEND_ACTION_CHIPS, perms, safe_reverse, build_nav_item, dedupe_nav_items)
    welcome_action_grid = _resolve_actions(BACKEND_WELCOME_ACTION_GRID, perms, safe_reverse, build_nav_item, dedupe_nav_items)
    quick_links = _resolve_actions(BACKEND_QUICK_LINKS, perms, safe_reverse, build_nav_item, dedupe_nav_items)
    command_palette = _resolve_actions(BACKEND_COMMAND_PALETTE, perms, safe_reverse, build_nav_item, dedupe_nav_items)

    return {
        "primary_ctas": primary_ctas,
        "action_chips": action_chips,
        "welcome_action_grid": welcome_action_grid,
        "quick_links": quick_links,
        "command_palette": command_palette,
    }


def get_admin_header_actions(safe_reverse: Callable[[str, str], str]) -> List[Dict[str, Any]]:
    """Resolve admin dashboard header actions from registry (single source; no duplicate Customizer)."""
    out = []
    for s in ADMIN_HEADER_ACTIONS:
        url = safe_reverse(s["url_name"], s.get("fallback_url_name", "#"))
        if url and url != "#":
            out.append({
                "label": s["label"],
                "url": url,
                "css_class": s.get("css_class", ""),
                "append_next": s.get("append_next", False),
            })
    return out
