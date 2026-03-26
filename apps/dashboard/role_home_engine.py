from __future__ import annotations

"""
Role-home engine: single source of truth for role-native dashboard configuration.

Resolves which "home" configuration applies to a role (principal, teacher, finance, etc.),
prioritizes destinations and next-best actions by intent, and selects KPIs for the strip.
Used by backend dashboard, control plane, and any role-home surface.

Phase F (RUNMYCAMPUS §8): Role-home engine extracted into a dedicated service for
testability, reuse, and future role-home packs.

§10.5 / §1.8 Decision architecture: New or materially changed dashboards/pages must
satisfy the seven-question declaration in docs/DECISION_ARCHITECTURE_CHECKLIST.md
before merge. See docs/DASHBOARD_TAXONOMY_AND_REGISTRY.md for registry and when-to-use.
Edge-case and failure strategy: docs/EDGE_CASE_AND_FAILURE_STRATEGY.md (§10.5.1).
Pack versioning and compatibility: docs/PACK_VERSIONING_AND_COMPATIBILITY.md (§10.5.2).
Service/support operating layer (onboarding, maturity, support queue, incidents):
docs/SERVICE_AND_SUPPORT_OPERATING_LAYER.md (§10.5.3).
Trust product (visible security and trust): docs/TRUST_PRODUCT_SURFACES.md (§10.5.4).
Content/terminology and UX copy: docs/CONTENT_AND_TERMINOLOGY_GOVERNANCE.md (§10.5.6).
Design system (behavior, archetypes, a11y): docs/DESIGN_SYSTEM_BEHAVIOR.md (§10.5.7).
Recurring discipline (dead links, observability, exception/secret lints, docs truth):
docs/BORING_EXCELLENCE_PROGRAM.md (RUNMYCAMPUS §10.5.8).
"""

# Non-negotiable: decision architecture checklist for new/changed dashboards (RUNMYCAMPUS §1.8, §8.0)
DECISION_ARCHITECTURE_CHECKLIST_DOC = "docs/DECISION_ARCHITECTURE_CHECKLIST.md"
# Dashboard registry: new dashboards must add a row here before merge (RUNMYCAMPUS §10.5.5)
DASHBOARD_TAXONOMY_AND_REGISTRY_DOC = "docs/DASHBOARD_TAXONOMY_AND_REGISTRY.md"
# Edge-case and failure strategy: partial failures, policy collisions, rollover, etc. (RUNMYCAMPUS §10.5.1)
EDGE_CASE_AND_FAILURE_STRATEGY_DOC = "docs/EDGE_CASE_AND_FAILURE_STRATEGY.md"
# Pack versioning and compatibility: semver, upgrade/downgrade, tenant impact (RUNMYCAMPUS §10.5.2)
PACK_VERSIONING_AND_COMPATIBILITY_DOC = "docs/PACK_VERSIONING_AND_COMPATIBILITY.md"
# Service/support operating layer: dimension→surface mapping, control-plane entry points (RUNMYCAMPUS §10.5.3)
SERVICE_AND_SUPPORT_OPERATING_LAYER_DOC = "docs/SERVICE_AND_SUPPORT_OPERATING_LAYER.md"
# Trust product: visible security and trust surfaces (MFA, sessions, audit export, etc.) (RUNMYCAMPUS §10.5.4)
TRUST_PRODUCT_SURFACES_DOC = "docs/TRUST_PRODUCT_SURFACES.md"
# Content and terminology: glossary, UX writing guide, CTA/alert/empty-state (RUNMYCAMPUS §10.5.6)
CONTENT_AND_TERMINOLOGY_GOVERNANCE_DOC = "docs/CONTENT_AND_TERMINOLOGY_GOVERNANCE.md"
# Design system behavior: archetypes, drawers, wizards, a11y, command palette (RUNMYCAMPUS §10.5.7)
DESIGN_SYSTEM_BEHAVIOR_DOC = "docs/DESIGN_SYSTEM_BEHAVIOR.md"
# Recurring discipline: CI/scheduled checks (dead links, observability, lints, docs truth) (RUNMYCAMPUS §10.5.8)
BORING_EXCELLENCE_PROGRAM_DOC = "docs/BORING_EXCELLENCE_PROGRAM.md"

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Role → home key mapping (one home config per logical role)
# ---------------------------------------------------------------------------
ROLE_HOME_BY_ROLE: Dict[str, str] = {
    "ADMIN": "implementation",
    "IT_ADMIN": "implementation",
    "SUPERADMIN": "platform_ops",
    "PRINCIPAL": "principal",
    "VICE_PRINCIPAL": "principal",
    "LEADERSHIP": "district_leader",
    "PROPRIETOR": "district_leader",
    "SECRETARY": "admissions",
    "ACADEMICS_STAFF": "admissions",
    "REGISTRAR": "admissions",
    "BURSAR": "finance",
    "ACCOUNTANT": "finance",
    "FINANCE_STAFF": "finance",
    "TEACHER": "teacher",
    "PARENT": "parent",
    "STUDENT": "student",
    "COMMS_STAFF": "support",
    "EXECUTIVE_ASSISTANT": "support",
    "VIRTUAL_ASSISTANT": "support",
}

# ---------------------------------------------------------------------------
# Home configurations: key, labels, purpose, focus areas, default intent, destinations
# ---------------------------------------------------------------------------
ROLE_HOME_CONFIG: Dict[str, Dict[str, Any]] = {
    "principal": {
        "key": "principal",
        "eyebrow": "Principal home",
        "title": "Lead with status and decisions",
        "purpose": "See academic, people, finance, and launch signals without reconstructing the story from separate pages.",
        "focus_areas": ["School pulse", "Decision queue", "Escalations"],
        "default_intent": "executive",
        "queue_label": "Decision queue",
        "next_label": "Recommended next",
        "recent_label": "Recent movement",
        "search_hint": "Search students, finance actions, interventions, and workflows",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "strategic",
        "jtbd": "Decide what to act on across academics, people, and operations in one glance.",
        "main_question": "What needs my decision or escalation right now?",
        "main_action": "Run the primary CTA or command palette to act without hunting menus.",
    },
    "teacher": {
        "key": "teacher",
        "eyebrow": "Teacher home",
        "title": "Stay focused on class outcomes",
        "purpose": "This role home favors grading, attendance, and classroom actions over admin navigation.",
        "focus_areas": ["Class flow", "Assessment", "Family communication"],
        "default_intent": "academic",
        "queue_label": "Academic queue",
        "next_label": "Teaching next steps",
        "recent_label": "Latest classroom movement",
        "search_hint": "Search classes, grades, attendance, and parent communication",
        "destinations": ["workflow_center", "preferences"],
        "dashboard_type": "operational",
        "jtbd": "Complete today's teaching work (grades, attendance, and family touchpoints).",
        "main_question": "What must I finish for class and parents today?",
        "main_action": "Use teaching next steps and workflow links before browsing modules.",
    },
    "admissions": {
        "key": "admissions",
        "eyebrow": "Admissions home",
        "title": "Move applicants into active enrollment",
        "purpose": "Keep enrollment, onboarding, and records flowing without bouncing across utility pages.",
        "focus_areas": ["Applicant flow", "Onboarding", "Record quality"],
        "default_intent": "operational",
        "queue_label": "Admissions queue",
        "next_label": "Enrollment next",
        "recent_label": "Recent admissions activity",
        "search_hint": "Search applicants, students, families, and enrollment tasks",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "operational",
        "jtbd": "Move applicants through enrollment with clean records and fewer handoffs.",
        "main_question": "Who is stuck in the enrollment or records funnel?",
        "main_action": "Clear the admissions queue items first, then deep links.",
    },
    "finance": {
        "key": "finance",
        "eyebrow": "Finance home",
        "title": "Collections and approvals first",
        "purpose": "Every block in this mode is tuned for payment health, approvals, and billing follow-through.",
        "focus_areas": ["Collections", "Approvals", "Reconciliation"],
        "default_intent": "finance",
        "queue_label": "Collections queue",
        "next_label": "Finance next",
        "recent_label": "Recent finance movement",
        "search_hint": "Search invoices, collections, requests, and approvals",
        "destinations": ["workflow_center", "preferences"],
        "dashboard_type": "analytical",
        "jtbd": "Protect cash flow—collections, approvals, and billing follow-through.",
        "main_question": "Where is revenue or approval risk this week?",
        "main_action": "Triage collections queue and finance console before other modules.",
    },
    "district_leader": {
        "key": "district_leader",
        "eyebrow": "District leader home",
        "title": "See school health before drilling down",
        "purpose": "Monitor cross-team movement and intervene only where the platform shows risk or friction.",
        "focus_areas": ["Portfolio pulse", "Priority risks", "Cross-school movement"],
        "default_intent": "executive",
        "queue_label": "Leadership queue",
        "next_label": "Leadership next",
        "recent_label": "Recent operating movement",
        "search_hint": "Search schools, approvals, audits, and operations",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "strategic",
        "jtbd": "See portfolio health and intervene only where risk or friction shows up.",
        "main_question": "Which school or workflow needs executive attention today?",
        "main_action": "Scan leadership queue and next steps before drilling into a school.",
    },
    "implementation": {
        "key": "implementation",
        "eyebrow": "Implementation home",
        "title": "Launch readiness is the main job",
        "purpose": "Use Setup Studio, queue health, and role previews to remove launch blockers in the right order.",
        "focus_areas": ["Blueprint", "Preview", "Launch readiness"],
        "default_intent": "setup",
        "queue_label": "Launch blockers",
        "next_label": "Launch next",
        "recent_label": "Recent setup movement",
        "search_hint": "Search setup tasks, blueprints, branding, and launch blockers",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "operational",
        "jtbd": "Ship a correct go-live: remove blockers in the right order with previews.",
        "main_question": "What is blocking launch readiness for this tenant?",
        "main_action": "Resolve launch blockers and Setup Studio steps before optional browsing.",
    },
    "support": {
        "key": "support",
        "eyebrow": "Support & communications home",
        "title": "Keep rollout and comms unblocked",
        "purpose": "Coordinate announcements, stakeholder messaging, and implementation follow-through without losing the thread.",
        "focus_areas": ["Stakeholder comms", "Launch support", "Content quality"],
        "default_intent": "operational",
        "queue_label": "Support queue",
        "next_label": "Comms next",
        "recent_label": "Recent support movement",
        "search_hint": "Search announcements, workflows, setup tasks, and documents",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "operational",
        "jtbd": "Align communications and implementation tasks so schools are not surprised.",
        "main_question": "What message or task is waiting on me?",
        "main_action": "Clear support queue items, then workflow and documents.",
    },
    "platform_ops": {
        "key": "platform_ops",
        "eyebrow": "Platform operations",
        "title": "Fleet health and control-plane velocity",
        "purpose": "See cross-tenant risk, billing, incidents, and rollout status before drilling into a single school.",
        "focus_areas": ["Fleet pulse", "Incidents & billing", "Governance"],
        "default_intent": "executive",
        "queue_label": "Platform queue",
        "next_label": "Ops next",
        "recent_label": "Recent platform movement",
        "search_hint": "Search schools, incidents, billing, and marketplace governance",
        "destinations": ["workflow_center", "documents", "preferences"],
        "dashboard_type": "strategic",
        "jtbd": "Operate the fleet—incidents, billing, and governance at a glance.",
        "main_question": "Where is cross-tenant or platform risk concentrated?",
        "main_action": "Use platform queue and super surfaces before tenant drill-down.",
    },
    "parent": {
        "key": "parent",
        "eyebrow": "Parent home",
        "title": "One place for family follow-through",
        "purpose": "Stay on top of attendance, grades, fees, and messages without chasing separate tools.",
        "focus_areas": ["Child context", "Fees", "Messages"],
        "default_intent": "operational",
        "queue_label": "Family queue",
        "next_label": "Family next",
        "recent_label": "Recent family updates",
        "search_hint": "Search children, fees, messages, and school updates",
        "destinations": ["preferences"],
        "dashboard_type": "operational",
        "jtbd": "Stay current on each child's fees, grades, attendance, and school messages.",
        "main_question": "What do I need to do for my children this week?",
        "main_action": "Use family queue and next steps before browsing the portal.",
    },
    "student": {
        "key": "student",
        "eyebrow": "Student home",
        "title": "Keep learning work obvious",
        "purpose": "Assignments, results, and resources should feel like one path instead of separate utilities.",
        "focus_areas": ["Schedule", "Deadlines", "Progress"],
        "default_intent": "academic",
        "queue_label": "Student queue",
        "next_label": "Student next",
        "recent_label": "Recent study updates",
        "search_hint": "Search assignments, grades, and school resources",
        "destinations": ["preferences"],
        "dashboard_type": "operational",
        "jtbd": "See what's due and how you're progressing without hunting modules.",
        "main_question": "What should I work on next for school?",
        "main_action": "Follow student next steps and queue before exploring extras.",
    },
}

# ---------------------------------------------------------------------------
# Intent → KPI strip priority (which 3 KPIs to show first per intent)
# ---------------------------------------------------------------------------
INTENT_KPI_PRIORITY: Dict[str, List[str]] = {
    "executive": ["top_performing", "attendance_today", "recent_admissions"],
    "operational": ["attendance_today", "recent_admissions", "weekly_presence"],
    "academic": ["top_performing", "attendance_today", "recent_admissions"],
    "finance": ["recent_admissions", "attendance_today", "weekly_presence"],
    "setup": ["recent_admissions", "attendance_today", "weekly_presence"],
}

VALID_DASHBOARD_INTENTS = frozenset(INTENT_KPI_PRIORITY.keys())


def _dedupe_nav_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep order while removing duplicate nav actions (by id, label, url)."""
    seen: set[Tuple[str, str, str]] = set()
    unique: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "") or "").strip().lower()
        label = str(item.get("label", "") or "").strip().lower()
        url = str(item.get("url", "") or "").strip().lower()
        key = (item_id, label, url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolve_role_home(role_code: str, intent: Optional[str]) -> Dict[str, Any]:
    """
    Resolve the role-home configuration for the given role and optional intent.

    Returns a copy of the home config with active_intent set. If intent is not
    in VALID_DASHBOARD_INTENTS, default_intent from the home config is used.
    """
    home_key = ROLE_HOME_BY_ROLE.get(
        (role_code or "").strip().upper(),
        "implementation" if intent == "setup" else "principal",
    )
    role_home = dict(ROLE_HOME_CONFIG.get(home_key, ROLE_HOME_CONFIG["principal"]))
    if intent and intent in VALID_DASHBOARD_INTENTS:
        role_home["active_intent"] = intent
    else:
        role_home["active_intent"] = role_home.get("default_intent", "executive")
    return role_home


def prioritize_destinations(
    role_home: Dict[str, Any],
    action_chips: List[Dict[str, Any]],
    quick_links: List[Dict[str, Any]],
    contextual_actions: List[Dict[str, Any]],
    *,
    max_items: int = 5,
) -> List[Dict[str, Any]]:
    """
    Merge and prioritize destination links for the role home.

    Combines action_chips, quick_links, and contextual_actions; dedupes; then
    reorders by role_home["destinations"] preferred IDs, then by combined order.
    """
    combined = _dedupe_nav_items(
        list(action_chips or [])
        + list(quick_links or [])
        + list(contextual_actions or [])
    )
    preferred_ids = list(role_home.get("destinations") or [])
    by_id = {str(item.get("id", "")): item for item in combined if item.get("id")}
    prioritized: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    def remember(item: Dict[str, Any]) -> bool:
        key = (
            str(item.get("label", "") or "").strip().lower(),
            str(item.get("url", "") or "").strip().lower(),
        )
        if key in seen:
            return False
        seen.add(key)
        return True

    for item_id in preferred_ids:
        item = by_id.get(item_id)
        if item and item not in prioritized and remember(item):
            prioritized.append(item)
    for item in combined:
        if item not in prioritized and remember(item):
            prioritized.append(item)
    return prioritized[:max_items]


def select_role_home_actions(
    dashboard_next_best_actions: List[Dict[str, Any]],
    primary_ctas: List[Dict[str, Any]],
    role_home_destinations: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Choose one primary action and up to three supporting actions for the role home.

    Combined order: dashboard next-best (recommendation service), then primary CTAs,
    then role-home destinations. Primary = first; supporting = next 3 unique.
    """
    combined = _dedupe_nav_items(
        list(dashboard_next_best_actions or [])
        + list(primary_ctas or [])
        + list(role_home_destinations or [])
    )
    primary_action = combined[0] if combined else None
    supporting_actions: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    if primary_action:
        seen.add(
            (
                str(primary_action.get("label", "") or "").strip().lower(),
                str(primary_action.get("url", "") or "").strip().lower(),
            )
        )
    for item in combined[1:]:
        key = (
            str(item.get("label", "") or "").strip().lower(),
            str(item.get("url", "") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        supporting_actions.append(item)
        if len(supporting_actions) >= 3:
            break
    return primary_action, supporting_actions


def select_kpis_for_intent(
    kpis: List[Dict[str, Any]], intent: str
) -> List[Dict[str, Any]]:
    """
    Reorder KPI strip cards by intent priority; return up to 3.

    Uses INTENT_KPI_PRIORITY to order; KPIs not in the priority list follow after.
    """
    desired_ids = INTENT_KPI_PRIORITY.get(intent, [])
    by_id = {str(item.get("id", "")): item for item in kpis}
    ordered: List[Dict[str, Any]] = []
    for item_id in desired_ids:
        item = by_id.get(item_id)
        if item and item not in ordered:
            ordered.append(item)
    for item in kpis:
        if item not in ordered:
            ordered.append(item)
    return ordered[:3]
