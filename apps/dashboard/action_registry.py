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
    {"label": "Studio", "icon": "bi-grid-3x3-gap", "url_name": "studio_os:shell", "fallback_url_name": "siteconfig:user_preferences"},
    {"label": "Manage Staff", "icon": "bi-person-gear", "url_name": "accounts:backend_teacher_list", "fallback_url_name": "accounts:backend_dashboard"},
]

BACKEND_INTENT_PRIMARY_SPECS = {
    "executive": {
        "label": "Review school pulse",
        "icon": "bi-speedometer2",
        "url_name": "accounts:workflow_center",
        "fallback_url_name": "accounts:backend_dashboard",
        "hint": "See the decision queue, blockers, and operating health in one place.",
    },
    "operational": {
        "label": "Resolve active queues",
        "icon": "bi-diagram-3",
        "url_name": "accounts:workflow_center",
        "fallback_url_name": "accounts:backend_dashboard",
        "hint": "Work through admissions, finance, and staffing actions from one queue.",
    },
    "academic": {
        "label": "Open academic workbench",
        "icon": "bi-journal-check",
        "url_name": "reports:publish_term_results",
        "fallback_url_name": "accounts:backend_student_list",
        "hint": "Focus on grading, interventions, and classroom readiness.",
    },
    "finance": {
        "label": "Open finance console",
        "icon": "bi-cash-stack",
        "url_name": "finance:dashboard",
        "fallback_url_name": "accounts:backend_dashboard",
        "hint": "Prioritize collections, approvals, and billing health before anything else.",
    },
    "setup": {
        "label": "Open Setup Studio",
        "icon": "bi-magic",
        "url_name": "siteconfig:guided_onboarding",
        "fallback_url_name": "accounts:backend_dashboard",
        "hint": "Clear launch blockers, preview every role, and move toward launch readiness.",
    },
}

BACKEND_ACTION_CHIPS = [
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "allow_key": "always"},
    {"label": "Messages", "icon": "bi-chat-dots", "url_name": "accounts:user_messages", "allow_key": "can_use_messages"},
    {"label": "Report Card Builder", "icon": "bi-file-earmark-richtext", "url_name": "siteconfig:reportcard_builder", "allow_key": "can_manage_reports"},
    {"label": "My Preferences", "icon": "bi-sliders", "url_name": "siteconfig:user_preferences", "allow_key": "always"},
    {"label": "Configuration Engine", "icon": "bi-gear-wide-connected", "url_name": "admin:index", "allow_key": "can_manage_settings"},
]

BACKEND_WELCOME_ACTION_GRID = [
    {"label": "Studio", "icon": "bi-grid-3x3-gap", "url_name": "studio_os:shell", "item_id": "studio_os", "allow_key": "can_manage_settings"},
    {"label": "Setup Studio", "icon": "bi-magic", "url_name": "siteconfig:guided_onboarding", "item_id": "setup_studio", "allow_key": "can_manage_settings"},
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "item_id": "workflow_center", "allow_key": "always"},
    {"label": "Finance Console", "icon": "bi-cash-stack", "url_name": "finance:dashboard", "item_id": "finance_console", "allow_key": "can_manage_finance"},
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
    {"label": "Studio", "icon": "bi-grid-3x3-gap", "url_name": "studio_os:shell", "fallback_url_name": "accounts:backend_dashboard", "allow_key": "can_manage_settings"},
    {"label": "Add Student", "icon": "bi-person-plus", "url_name": "accounts:backend_student_create", "fallback_url_name": "admin:index", "allow_key": "can_manage_people"},
    {"label": "Manage Staff", "icon": "bi-people", "url_name": "accounts:backend_teacher_list", "fallback_url_name": "accounts:backend_dashboard", "allow_key": "can_manage_people"},
    {"label": "Manage Exams", "icon": "bi-journal-check", "url_name": "reports:publish_term_results", "allow_key": "can_manage_reports"},
    {"label": "Import Grades", "icon": "bi-upload", "url_name": "evals:grade_import_upload", "allow_key": "can_manage_reports"},
    {"label": "Finance Dashboard", "icon": "bi-cash-stack", "url_name": "finance:dashboard", "allow_key": "can_manage_finance"},
    {"label": "Experience", "icon": "bi-palette", "url_name": "studio_os:experience", "fallback_url_name": "studio_os:shell", "allow_key": "can_manage_settings"},
    {"label": "Workflow Center", "icon": "bi-diagram-3", "url_name": "accounts:workflow_center", "allow_key": "always"},
    # §8.0.4 Command palette example intents (UI/UX doc)
    {"label": "Open fee reminder automation", "icon": "bi-clock-history", "url_name": "studio_os:automation", "fallback_url_name": "accounts:workflow_center", "allow_key": "can_manage_settings"},
    {"label": "Configure grade reports", "icon": "bi-file-earmark-bar-graph", "url_name": "studio_os:output", "fallback_url_name": "reports:publish_term_results", "allow_key": "can_manage_reports"},
    {"label": "Go to district analytics", "icon": "bi-graph-up", "url_name": "super:analytics_overview", "fallback_url_name": "accounts:backend_dashboard", "allow_key": "can_manage_settings"},
]

# Dashboard intents: primary CTA index (0 or 1) into BACKEND_PRIMARY_CTAS, and welcome action item_ids to prioritize.
BACKEND_INTENT_PRIMARY_INDEX = {
    "executive": 0,   # Manage Staff
    "operational": 0,
    "academic": 0,
    "finance": 1,    # School Settings
    "setup": 0,
}
BACKEND_INTENT_WELCOME_ITEM_IDS = {
    "executive": ["studio_os", "workflow_center", "setup_studio", "roles_permissions", "manage_exams", "document_library", "add_student"],
    "operational": ["workflow_center", "add_student", "add_teacher", "manage_exams", "create_invoice", "announcements"],
    "academic": ["manage_exams", "workflow_center", "add_student", "onboard_student", "add_teacher", "document_library"],
    "finance": ["finance_console", "create_invoice", "workflow_center", "document_library", "roles_permissions"],
    "setup": ["setup_studio", "studio_os", "workflow_center", "add_student", "add_teacher", "onboard_student", "document_library", "manage_exams"],
}
VALID_DASHBOARD_INTENTS = frozenset(BACKEND_INTENT_PRIMARY_INDEX.keys())

# Admin dashboard (obs): header actions only; single Customizer entry to avoid duplicate CTAs
ADMIN_HEADER_ACTIONS = [
    {"label": "My Preferences", "url_name": "siteconfig:user_preferences", "fallback_url_name": "admin:index", "css_class": "admin-dash__header-action", "append_next": True},
    {"label": "Backend Console", "url_name": "accounts:backend_dashboard", "fallback_url_name": "admin:index", "css_class": "admin-dash__header-action"},
    {"label": "Studio", "url_name": "studio_os:shell", "fallback_url_name": "siteconfig:user_preferences", "css_class": "admin-dash__header-action admin-dash__header-action--primary"},
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


def _filter_actions_by_intent(
    primary_ctas: List[Dict[str, str]],
    welcome_action_grid: List[Dict[str, str]],
    intent: Optional[str],
    max_welcome: int = 7,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """By intent: 1 primary CTA and up to max_welcome contextual actions (ordered by intent)."""
    if not intent or intent not in VALID_DASHBOARD_INTENTS:
        return primary_ctas, welcome_action_grid
    primary_one = primary_ctas[:1]
    preferred_ids = BACKEND_INTENT_WELCOME_ITEM_IDS.get(intent, [])
    # Reorder welcome_action_grid by preferred_ids, then cap
    by_id = {str(item.get("id", "")): item for item in welcome_action_grid if item.get("id")}
    ordered: List[Dict[str, str]] = []
    for pid in preferred_ids:
        if pid in by_id and by_id[pid] not in ordered:
            ordered.append(by_id[pid])
    for item in welcome_action_grid:
        if item not in ordered:
            ordered.append(item)
    return primary_one, ordered[:max_welcome]


def get_backend_dashboard_actions(
    perms: Dict[str, bool],
    safe_reverse: Callable[[str, str], str],
    build_nav_item: Callable[..., Optional[Dict[str, str]]],
    dedupe_nav_items: Callable[[List[Dict[str, str]]], List[Dict[str, str]]],
    intent: Optional[str] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """Resolve backend dashboard actions from the registry. perms must contain can_manage_settings, can_manage_people, can_manage_finance, can_manage_reports, can_use_messages, can_manage_rbac. If intent is set, primary_ctas and welcome_action_grid are filtered to 1 + 5-7 items for that intent."""
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

    if intent and intent in VALID_DASHBOARD_INTENTS:
        primary_spec = BACKEND_INTENT_PRIMARY_SPECS.get(intent)
        if primary_spec:
            primary_url = safe(primary_spec["url_name"], primary_spec.get("fallback_url_name", "#"))
            if primary_url != "#":
                primary_ctas = [{
                    "label": primary_spec["label"],
                    "icon": primary_spec["icon"],
                    "url": primary_url,
                    "hint": primary_spec.get("hint", ""),
                }]
        primary_ctas, welcome_action_grid = _filter_actions_by_intent(
            primary_ctas, welcome_action_grid, intent, max_welcome=7
        )

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


# Group names for contextual action panel (goal-based grouping)
CONTEXTUAL_GROUP_PEOPLE = "People"
CONTEXTUAL_GROUP_FINANCE = "Finance"
CONTEXTUAL_GROUP_SETUP = "Setup"
CONTEXTUAL_GROUP_REPORTS = "Reports & Exams"
CONTEXTUAL_GROUP_NAV = "Go to"

# Map item_id -> group for backend contextual panel
BACKEND_CONTEXTUAL_GROUPS: Dict[str, str] = {
    "setup_studio": CONTEXTUAL_GROUP_SETUP,
    "finance_console": CONTEXTUAL_GROUP_FINANCE,
    "add_student": CONTEXTUAL_GROUP_PEOPLE,
    "add_teacher": CONTEXTUAL_GROUP_PEOPLE,
    "onboard_student": CONTEXTUAL_GROUP_PEOPLE,
    "roles_permissions": CONTEXTUAL_GROUP_PEOPLE,
    "create_invoice": CONTEXTUAL_GROUP_FINANCE,
    "manage_exams": CONTEXTUAL_GROUP_REPORTS,
    "import_grades": CONTEXTUAL_GROUP_REPORTS,
    "exams": CONTEXTUAL_GROUP_REPORTS,
    "certification": CONTEXTUAL_GROUP_REPORTS,
    "document_library": CONTEXTUAL_GROUP_SETUP,
    "workflow_center": CONTEXTUAL_GROUP_SETUP,
    "preferences": CONTEXTUAL_GROUP_NAV,
    "announcements": CONTEXTUAL_GROUP_PEOPLE,
}

BACKEND_CONTEXTUAL_REASONS: Dict[str, str] = {
    "setup_studio": "Use one guided launch surface instead of scattering setup across utility pages.",
    "finance_console": "Open collections, approvals, and billing health from one finance-first surface.",
    "add_student": "Unblock enrollment and downstream workflows.",
    "add_teacher": "Get classrooms, reporting, and communication ready faster.",
    "onboard_student": "Move one admitted learner into an active record.",
    "roles_permissions": "Tighten access before scaling more users.",
    "create_invoice": "Convert finance actions into collection progress.",
    "manage_exams": "Keep academic reporting and interventions on schedule.",
    "import_grades": "Move marks into reports without manual re-entry.",
    "exams": "Review result publishing readiness.",
    "certification": "Track exam and certification milestones.",
    "document_library": "Give staff and families the latest approved documents.",
    "workflow_center": "Open the single queue for cross-team work.",
    "preferences": "Tune the workspace without leaving your current flow.",
    "announcements": "Push timely updates to the right audience.",
}


def get_contextual_actions(
    context_name: str,
    perms: Dict[str, bool],
    safe_reverse: Callable[[str, str], str],
    *,
    intent: Optional[str] = None,
    workflow_progress: Optional[Dict[str, Any]] = None,
    recommended_steps: Optional[List[Dict[str, Any]]] = None,
    max_items: int = 7,
) -> List[Dict[str, Any]]:
    """
    Return a flat list of actions for the contextual action panel, resolved from registry.
    Each item: {"label", "icon", "url", "id" (optional), "group"}.
    Capped at max_items, grouped by goal. Used by quick_actions.html when contextual_actions is provided.
    """
    from django.urls import NoReverseMatch

    def safe(name: str, fallback: str = "#") -> str:
        try:
            return safe_reverse(name, fallback)
        except (NoReverseMatch, Exception):
            return fallback

    if context_name == "admin_index":
        out = []
        for s in ADMIN_HEADER_ACTIONS:
            url = safe(s["url_name"], s.get("fallback_url_name", "#"))
            if url and url != "#":
                out.append({
                    "label": s["label"],
                    "icon": "bi-gear",
                    "url": url,
                    "group": CONTEXTUAL_GROUP_NAV,
                })
        return out[:max_items]

    # backend_dashboard: welcome grid resolved with perms, ranked by intent and workflow state.
    out = []
    for s in BACKEND_WELCOME_ACTION_GRID:
        allow = perms.get(s.get("allow_key", "always"), True) if s.get("allow_key") != "always" else True
        if not allow:
            continue
        url = safe(s["url_name"], s.get("fallback_url_name", "#"))
        if not url or url == "#":
            continue
        item_id = s.get("item_id", "")
        out.append({
            "label": s["label"],
            "icon": s["icon"],
            "url": url,
            "id": item_id,
            "group": BACKEND_CONTEXTUAL_GROUPS.get(item_id, CONTEXTUAL_GROUP_NAV),
            "reason": BACKEND_CONTEXTUAL_REASONS.get(item_id, "Continue the highest-value workflow for this role."),
        })
    recommended_by_id: Dict[str, Dict[str, Any]] = {}
    preferred_ids = []
    for step in recommended_steps or []:
        action_id = str(step.get("action_id", "") or "").strip()
        if not action_id:
            continue
        recommended_by_id[action_id] = step
        preferred_ids.append(action_id)

    preferred_ids.extend(BACKEND_INTENT_WELCOME_ITEM_IDS.get(intent or "", []))
    if workflow_progress:
        if workflow_progress.get("students", 0) == 0:
            preferred_ids.insert(0, "add_student")
        if workflow_progress.get("teachers", 0) == 0:
            preferred_ids.insert(0, "add_teacher")
        if workflow_progress.get("classrooms", 0) == 0 or not workflow_progress.get("has_year_setup", False):
            preferred_ids.insert(0, "workflow_center")

    by_id = {str(item.get("id", "")): item for item in out if item.get("id")}
    ordered: List[Dict[str, Any]] = []
    for item_id in preferred_ids:
        action = by_id.get(item_id)
        if action and action not in ordered:
            ordered.append(action)
    for item in out:
        if item not in ordered:
            ordered.append(item)

    sliced = ordered[:max_items]
    for index, item in enumerate(sliced):
        recommendation = recommended_by_id.get(str(item.get("id", "")))
        if recommendation:
            item["reason"] = recommendation.get("reason") or item.get("reason", "")
            item["category"] = recommendation.get("category") or item.get("group")
            item["priority"] = recommendation.get("priority") or ("now" if index == 0 else "next" if index < 3 else "later")
        else:
            item["priority"] = "now" if index == 0 else "next" if index < 3 else "later"
        item["featured"] = index == 0
    return sliced
