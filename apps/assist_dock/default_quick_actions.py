"""v4.02.15 — seeded page-aware quick actions for Tools tray + assist dock."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .quick_actions import QuickAction, register_quick_action
from .registry import SURFACE_ADMIN, SURFACE_MANAGER, SURFACE_PORTAL


def register_default_quick_actions() -> None:
    """Register high-traffic shortcuts; idempotent overwrite on reload."""
    seeds: tuple[QuickAction, ...] = (
        QuickAction(
            id="tools-qa-super-home",
            label=_("Command center"),
            icon="bi-speedometer2",
            url_name="super:dashboard",
            path_prefixes=("/super/dashboard",),
            surfaces=frozenset({SURFACE_MANAGER}),
            description=_("Return to the operator dashboard"),
            order=10,
        ),
        # T9: the "Backend home" quick action rendered as a floating bottom-right
        # chip in the assist dock (rmc-assist-dock.js renderQuickActions) as well
        # as a Tools-tray page action. Removed (not hidden) per owner request —
        # the shell already carries Home in the primary nav and the sidebar.
        QuickAction(
            id="tools-qa-parent-home",
            label=_("Family home"),
            icon="bi-house-heart",
            href="/portal/parent/",
            path_prefixes=("/portal/parent",),
            surfaces=frozenset({SURFACE_PORTAL}),
            roles=frozenset({"PARENT", "*"}),  # role-string-allow: quick-action-visibility-filter-not-authz
            description=_("Parent portal home"),
            order=20,
        ),
        QuickAction(
            id="tools-qa-teacher-home",
            label=_("Teacher home"),
            icon="bi-mortarboard",
            href="/portal/teacher/",
            path_prefixes=("/portal/teacher", "/evals/teacher"),
            surfaces=frozenset({SURFACE_PORTAL}),
            roles=frozenset({"TEACHER", "*"}),  # role-string-allow: quick-action-visibility-filter-not-authz
            description=_("Teacher workspace home"),
            order=25,
        ),
        QuickAction(
            id="tools-qa-student-grades",
            label=_("My grades"),
            icon="bi-journal-check",
            href="/portal/student-portal/grades/",
            path_prefixes=("/portal/student-portal",),
            surfaces=frozenset({SURFACE_PORTAL}),
            roles=frozenset({"STUDENT", "*"}),  # role-string-allow: quick-action-visibility-filter-not-authz
            description=_("Student grades portal"),
            order=30,
        ),
        QuickAction(
            id="tools-qa-finance-hub",
            label=_("Finance workspace"),
            icon="bi-cash-stack",
            href="/finance/",
            path_prefixes=("/finance/",),
            surfaces=frozenset({SURFACE_PORTAL, SURFACE_MANAGER, SURFACE_ADMIN}),
            description=_("Finance tasks on this page"),
            order=40,
        ),
        QuickAction(
            id="tools-qa-migration-hub",
            label=_("Migration console"),
            icon="bi-cloud-arrow-up",
            href="/super/migration/",
            path_prefixes=("/super/migration/",),
            surfaces=frozenset({SURFACE_MANAGER}),
            description=_("Migration Cloud operator tools"),
            order=50,
        ),
        QuickAction(
            id="tools-qa-tenant-kb",
            label=_("Help articles"),
            icon="bi-book",
            url_name="kb:kb_home",
            path_prefixes=("/kb/", "/portal/kb"),
            surfaces=frozenset({SURFACE_PORTAL}),
            description=_("Tenant knowledge base"),
            order=60,
        ),
    )
    for action in seeds:
        register_quick_action(action)


__all__ = ["register_default_quick_actions"]
