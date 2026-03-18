"""
North-star N1, N2, N3, N6, N8, N13, N21, N27–N29: role-native recommended next steps for backend dashboard.
Feeds get_contextual_actions(recommended_steps=...).
"""

from __future__ import annotations

from typing import Any


def build_north_star_recommended_steps(
    role_code: str,
    perms: dict[str, bool],
    *,
    workflow_progress: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Return steps as {action_id, reason, category} matching BACKEND_WELCOME_ACTION_GRID / QUICK_LINKS item_ids.
    """
    rc = (role_code or "").upper()
    wp = workflow_progress or {}
    steps: list[dict[str, Any]] = []

    def add(aid: str, reason: str, cat: str = "Recommended next") -> None:
        if any(s.get("action_id") == aid for s in steps):
            return
        steps.append({"action_id": aid, "reason": reason, "category": cat})

    # N29 zero-data bootstrap
    if wp.get("students", 1) == 0 and perms.get("can_manage_people", False):
        add(
            "add_student",
            "Add your first student record to go live faster.",
            "N29 · Setup",
        )
    if wp.get("teachers", 1) == 0 and perms.get("can_manage_people", False):
        add(
            "add_teacher",
            "Invite or add staff so classes can be taught.",
            "N29 · Setup",
        )

    leaders = {
        "ADMIN",
        "PRINCIPAL",
        "PROPRIETOR",
        "LEADERSHIP",
        "IT_ADMIN",
        "REGISTRAR",
    }
    if rc in leaders:
        add(
            "setup_studio",
            "Complete Setup Studio checklist—clear blockers before launch.",
            "N1 · Guided setup",
        )
        add(
            "workflow_center",
            "See admissions, finance, and staffing queues in one place.",
            "N8 · Low-click",
        )
        if perms.get("can_manage_settings", False):
            add(
                "studio_os",
                "Open Studio for theme, automation, and outputs.",
                "N6 · Role-native",
            )
        if perms.get("can_manage_rbac", False):
            add(
                "roles_permissions",
                "Review who can access sensitive data (RBAC).",
                "N13 · Trust",
            )
        if perms.get("can_manage_settings", False):
            add(
                "document_library",
                "Centralize policies and letters in Document Library.",
                "N2 · Delight",
            )
        if perms.get("can_use_messages", False):
            add(
                "announcements",
                "Post a clear, labeled announcement for your community.",
                "N8 · Comms",
            )
        if rc == "REGISTRAR" and perms.get("can_manage_people", False):
            add(
                "onboard_student",
                "Keep admissions and enrollment records current.",
                "N1 · Registrar",
            )

    elif rc == "DEAN":
        add(
            "workflow_center",
            "Coordinate academic deadlines and handoffs in one queue.",
            "N8 · Low-click",
        )
        if perms.get("can_manage_reports", False):
            add(
                "manage_exams",
                "Review grades and at-risk signals (EWS) from the reports hub.",
                "N28 · Early warning",
            )

    elif rc == "TEACHER":
        add(
            "manage_exams",
            "Open grading and exams for your classes.",
            "N1 · First task",
        )
        add("workflow_center", "Check tasks assigned to you.", "N28 · Stay ahead")
        add(
            "import_grades",
            "Bulk-import or refresh grade data when spreadsheets change.",
            "N4 · Mobile-friendly uploads",
        )

    elif rc == "BURSAR":
        add(
            "finance_console",
            "Review collections and billing health first.",
            "N1 · Finance",
        )
        add(
            "create_invoice",
            "Issue the next fee invoice from the finance console.",
            "N8 · Low-click",
        )

    elif rc == "PARENT":
        add("onboard_student", "Complete student onboarding if invited.", "N1 · Family")
        add(
            "preferences",
            "Set your notification and language preferences.",
            "N21 · Locale",
        )

    elif rc == "STUDENT":
        add("preferences", "Update your profile and preferences.", "N1 · You")

    elif rc == "LIBRARIAN":
        add(
            "workflow_center",
            "Track resource requests and school-wide tasks.",
            "N8 · Operations",
        )
        if perms.get("can_manage_settings", False):
            add(
                "document_library",
                "Manage learning resources and shared documents.",
                "N2 · Content",
            )

    # N28 EWS for academic leads (DEAN handled above)
    if rc in {"PRINCIPAL", "ADMIN"} and perms.get("can_manage_reports", False):
        add(
            "manage_exams",
            "Review grades and at-risk signals (EWS) from the reports hub.",
            "N28 · Early warning",
        )

    if rc == "IT_ADMIN" and not any(
        s.get("action_id") == "roles_permissions" for s in steps
    ):
        add(
            "roles_permissions",
            "Audit integrations and scoped API access regularly.",
            "N13 · Security posture",
        )

    return steps[:8]
