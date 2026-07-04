"""Universal Command Bar action registry (v3.53.0, 2026-05-21).

Server-side source of truth for the cmd+k / ctrl+k command bar
overlay shared across all 4 dashboard shells. Actions are typed,
role-scoped, and tenant-aware; the JSON endpoint at
``/api/command-bar/actions/`` filters per-request so no caller
ever sees URLs they cannot reach.

Design notes:

  * `CommandAction.scope` is a coarse audience gate:
      - "staff": only request.user.is_staff sees it.
      - "tenant_admin": staff OR tenant admin / proprietor.
      - "tenant_user": any authenticated user inside a tenant.
  * `role_required` is an OPTIONAL extra gate against
    ``User.Role`` text choices (defensive — actual URL access
    control still lives behind the view's own permission
    decorators; we only gate VISIBILITY here).
  * Tenant scoping: actions whose URLs depend on a school
    context are dropped when ``school`` is None (e.g. manager
    host without a tenant selected) — never leak cross-tenant
    URLs into the palette.

Adding actions: append to ``_PLATFORM_ACTIONS``. New actions
should reach for the smallest scope and reuse Django URL names
via ``reverse``; if a URL is unresolvable in the current
environment we silently drop the entry (URL-reverse failures
never break the palette).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views import View
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator


Scope = Literal["staff", "tenant_admin", "tenant_user"]


@dataclass(frozen=True)
class CommandAction:
    """One entry in the command bar palette.

    All fields are display-stable (no per-request mutation) so the
    registry can be safely cached at module level.
    """

    kind: str  # e.g. "navigate", "settings", "deploy", "health"
    label: str
    icon: str
    url: str
    scope: Scope
    role_required: Optional[str] = None
    confirm: bool = False  # v4.01.06 — palette renders a confirm step before navigating
    destructive: bool = False  # v4.01.06 — paint the entry in a danger tone; implies confirm

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "icon": self.icon,
            "url": self.url,
            "scope": self.scope,
            "role_required": self.role_required,
            "confirm": self.confirm or self.destructive,
            "destructive": self.destructive,
        }


def _safe_reverse(viewname: str) -> str:
    """Reverse a URL name without crashing the registry on missing routes."""
    try:
        return reverse(viewname)
    except NoReverseMatch:
        return ""


# ---------------------------------------------------------------------------
# Platform action catalog
# ---------------------------------------------------------------------------
# Each entry references a Django URL name so the literal path can shift
# without touching the registry. URL-reverse failures are filtered out at
# materialization time (see ``all_registered``), so the catalog can carry
# entries pointing to optional features without breaking the gate.

# v4.01.06: tuples accept an optional 7th `confirm` and 8th `destructive` field.
# `all_registered()` normalizes both shapes so legacy 6-tuples keep working.
_PLATFORM_ACTION_DEFS: tuple[tuple, ...] = (
    # ---- Navigation: studio + dashboards ----
    ("navigate", "Open Studio overview", "🏠", "studio_os:shell", "tenant_user", None),
    ("navigate", "Studio · Experience", "🎨", "studio_os:experience", "tenant_user", None),
    ("navigate", "Studio · Automation", "⚙", "studio_os:automation", "tenant_user", None),
    ("navigate", "Studio · Outputs", "📤", "studio_os:output", "tenant_user", None),
    ("navigate", "Studio · Launch", "🚀", "studio_os:launch", "tenant_user", None),
    ("navigate", "Studio · Control", "🛡", "studio_os:control", "tenant_user", None),
    ("navigate", "Back to dashboard", "↩", "accounts:backend_dashboard", "tenant_user", None),
    # ---- Operator surfaces ----
    ("navigate", "Workflow center", "🧩", "studio_os:workflow_center", "tenant_admin", None),
    ("navigate", "Approval hub", "✅", "studio_os:approval_hub", "tenant_admin", None),
    ("navigate", "Import hub", "📥", "studio_os:import_hub", "tenant_admin", None),
    # ---- Settings / theme ----
    ("settings", "Theme & colors", "🎨", "siteconfig:theme_colors", "tenant_admin", None),
    ("settings", "Template gallery", "🗂", "siteconfig:template_gallery", "tenant_admin", None),
    ("settings", "Brand import from URL", "🌐", "siteconfig:brand_import_from_url", "tenant_admin", None),
    ("settings", "Grading settings", "📊", "siteconfig:grading_settings", "tenant_admin", None),
    ("settings", "Module market", "🧱", "siteconfig:module_market", "tenant_admin", None),
    ("settings", "Command palette settings", "⌘", "siteconfig:command_palette_settings", "tenant_admin", None),
    ("settings", "Sidebar settings", "🧭", "siteconfig:sidebar_settings", "tenant_admin", None),
    ("settings", "Table settings", "🧮", "siteconfig:table_settings", "tenant_admin", None),
    ("settings", "Dashboard settings", "🧩", "siteconfig:dashboard_settings", "tenant_admin", None),
    ("settings", "Form settings", "📝", "siteconfig:form_settings", "tenant_admin", None),
    ("settings", "Empty-state settings", "📭", "siteconfig:empty_settings", "tenant_admin", None),
    ("settings", "Loading settings", "⏳", "siteconfig:loading_settings", "tenant_admin", None),
    ("settings", "Notification settings", "🔔", "siteconfig:notification_settings", "tenant_admin", None),
    ("settings", "Dialog settings", "🪟", "siteconfig:modal_settings", "tenant_admin", None),
    ("settings", "Detail-view settings", "🪪", "siteconfig:detail_settings", "tenant_admin", None),
    # ---- Studio palette generators ----
    ("palette", "Generate palette", "🎨", "studio_os:experience_recommendations", "tenant_admin", None),
    ("palette", "Compare themes", "🔁", "studio_os:experience_compare", "tenant_admin", None),
    ("install", "Install experience pack", "📦", "studio_os:experience_packs", "tenant_admin", None),
    ("deploy", "Publish (Studio)", "📡", "studio_os:experience", "tenant_admin", None),
    # ---- Health + ops (staff) ----
    ("health", "Check Studio version history", "🩺", "studio_os:experience", "staff", None),
    ("health", "Feature control", "🛂", "siteconfig:feature_control_panel", "staff", None),
    ("health", "AI governance", "🤖", "siteconfig:ai_governance", "staff", None),
    ("health", "AI center", "✨", "siteconfig:ai_center", "staff", None),
    # ---- Control plane navigation (staff-only context) ----
    ("navigate", "Sync center", "🔄", "siteconfig:sync_center", "staff", None),
    ("navigate", "Compliance exports", "📑", "siteconfig:compliance_exports", "staff", None),
    ("navigate", "Region validation", "🌍", "siteconfig:region_validation", "staff", None),
    ("navigate", "Region comparison", "🗺", "siteconfig:region_comparison", "staff", None),
    # ---- Tenant-user friendly nav ----
    ("navigate", "User preferences", "👤", "siteconfig:user_preferences", "tenant_user", None),
    ("navigate", "Bulk letters", "✉", "siteconfig:bulk_letters", "tenant_admin", None),
    ("navigate", "Report card builder", "📝", "siteconfig:reportcard_builder", "tenant_admin", None),
    ("navigate", "Scheduled reports", "🕒", "siteconfig:scheduled_reports_delivery_hub", "tenant_admin", None),
    ("navigate", "Draft parent message", "✉", "accounts:direct_compose", "tenant_user", "TEACHER"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Teacher workflow", "🧭", "portal:teacher_workflow", "tenant_user", "TEACHER"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Enter marks", "📊", "evals:teacher_marks_entry", "tenant_user", "TEACHER"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Family workflow", "🧭", "portal:parent_workflow", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Student workflow", "🧭", "portal:student_workflow", "tenant_user", "STUDENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Help center (AI)", "✨", "feedback:help_center", "tenant_user", None),
    ("navigate", "Search help center", "🔍", "feedback:help_center", "tenant_user", None),
    ("navigate", "RunMyCampus Guide", "🧭", "portal:runmycampus_guide", "tenant_user", None),
    # ---- CEZGP batch 1520 — ease layer (student_csv_import in labels for matrix P3) ----
    ("navigate", "Import students (CSV)", "📥", "studio_os:import_hub", "tenant_admin", None),
    ("navigate", "Invite parents", "✉", "siteconfig:guided_onboarding", "tenant_admin", None),
    ("navigate", "Post fees", "💰", "finance:generate_fees", "tenant_admin", None),
    ("navigate", "Launch Studio", "🚀", "studio_os:shell", "tenant_user", None),
    ("navigate", "Link child", "👪", "portal:link_child", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Claim invite", "🎫", "portal:claim_invite", "tenant_user", "PARENT"),
    ("navigate", "Parent finances", "🧾", "portal:parent_finance", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Pay all open balances", "💳", "portal:parent_finance_pay_all", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Contact school", "📞", "portal:parent_contact_school", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Export attendance (CSV)", "📊", "portal:teacher_attendance_export", "tenant_user", "TEACHER"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Teacher education pack", "📚", "portal:education_pack_teacher", "tenant_user", "TEACHER"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Family learning pack", "👪", "portal:education_pack_parent", "tenant_user", "PARENT"),  # role-string-allow: command-palette-role-required-field
    ("navigate", "Partner doc assistant", "🔗", "portal:partner_documentation_assistant", "tenant_admin", None),
    # ---- System / blueprints ----
    ("settings", "Get blueprints", "📐", "siteconfig:get_blueprints", "tenant_admin", None),
    ("settings", "Theme experience hub", "✨", "siteconfig:theme_experience_hub", "tenant_admin", None),
    # ---- v4.01.06: missing top-level destinations (per command-palette audit) ----
    ("navigate", "Messages", "💬", "accounts:user_messages", "tenant_user", None),
    ("navigate", "Notifications", "🔔", "accounts:user_notifications", "tenant_user", None),
    ("navigate", "My profile", "👤", "accounts:user_profile", "tenant_user", None),
    ("settings", "MFA setup", "🔐", "accounts:mfa_setup", "tenant_user", None),
    ("navigate", "Knowledge base", "📚", "kb:kb_home", "tenant_user", None),
    ("health", "Compliance dashboard", "🛂", "compliance:dashboard", "staff", None),
    ("navigate", "Command center", "🎯", "super:command_center", "staff", None),
    ("navigate", "Super dashboard", "🏛", "super:dashboard", "staff", None),
    ("settings", "Console domains hub", "🌐", "siteconfig:console_domains_hub", "staff", None),
    ("settings", "Toggle preview mode", "👁", "siteconfig:toggle_preview_mode", "staff", None),
    # ---- v4.01.06: destructive actions with confirm step ----
    ("settings", "Clear preview state", "🧹", "siteconfig:clear_preview", "staff", None, True, False),
    ("settings", "Sign out", "🚪", "accounts:logout", "tenant_user", None, True, True),
)


def all_registered() -> list[CommandAction]:
    """Materialize the full catalog, dropping entries with unresolvable URLs.

    Accepts 6-tuple legacy entries and 8-tuple v4.01.06 entries that carry the
    additional `confirm` and `destructive` flags.
    """
    out: list[CommandAction] = []
    for entry in _PLATFORM_ACTION_DEFS:
        kind, label, icon, viewname, scope, role_required = entry[:6]
        confirm = entry[6] if len(entry) > 6 else False
        destructive = entry[7] if len(entry) > 7 else False
        url = _safe_reverse(viewname)
        if not url:
            # Missing URL = action not available in this environment; skip.
            continue
        out.append(
            CommandAction(
                kind=kind,
                label=label,
                icon=icon,
                url=url,
                scope=scope,
                role_required=role_required,
                confirm=confirm,
                destructive=destructive,
            )
        )
    return out


def _user_is_authenticated(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False))


def _user_scope_rank(user) -> int:
    """Map user -> max visible scope rank.

    0 = anonymous (nothing visible)
    1 = tenant_user
    2 = tenant_admin (admin / proprietor role)
    3 = staff (sees everything regardless of tenant context)
    """
    if not _user_is_authenticated(user):
        return 0
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return 3
    role = (getattr(user, "role", "") or "").upper()
    if role in {"ADMIN", "PROPRIETOR"}:  # role-string-allow: rbac-role-comparison
        return 2
    return 1


_SCOPE_RANK: dict[str, int] = {
    "tenant_user": 1,
    "tenant_admin": 2,
    "staff": 3,
}


def _is_manager_request(request, school) -> bool:
    if request is None:
        return True
    kind = getattr(request, "public_host_kind", None)
    urlconf = getattr(request, "urlconf", None)
    return (
        (kind == "manager" or urlconf == "config.manager_urls")
        and school is None
    )


def _is_operator_action(action: CommandAction) -> bool:
    return action.url.startswith(("/super/", "/admin/"))


def get_actions_for_user(user, school, request=None) -> list[CommandAction]:
    """Filter the catalog by user scope + tenant context.

    * Anonymous users always get an empty list.
    * Actions whose scope rank exceeds the user's rank are dropped.
    * Optional ``role_required`` narrows further.
    * When ``school`` is None we still allow staff to see staff-scoped
      actions (manager host context) but DO NOT widen tenant-user
      visibility — they need a school to act inside a tenant.
    """
    if not _user_is_authenticated(user):
        return []
    rank = _user_scope_rank(user)
    role = (getattr(user, "role", "") or "").upper()
    out: list[CommandAction] = []
    for action in all_registered():
        if _is_operator_action(action) and not _is_manager_request(request, school):
            continue
        needed = _SCOPE_RANK.get(action.scope, 99)
        if needed > rank:
            continue
        if action.role_required and role != action.role_required.upper():
            continue
        # Tenant context discipline: tenant-scoped actions require a school
        # context unless the user is staff (manager host can pre-select).
        if action.scope != "staff" and school is None and rank < 3:
            # Tenant user / admin with no resolvable school — drop tenant
            # actions that depend on a school to make sense.
            continue
        out.append(action)
    return out


def serialize_actions(actions: Iterable[CommandAction]) -> list[dict]:
    return [a.to_dict() for a in actions]


@method_decorator(never_cache, name="dispatch")
class CommandBarActionsView(LoginRequiredMixin, View):
    """JSON endpoint that serves role + tenant-filtered command bar actions.

    Wired in apps/siteconfig/urls.py as ``command_bar_actions`` and reachable
    at ``/api/command-bar/actions/`` via config/urls.py.
    """

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        school = getattr(request, "school", None)
        actions = get_actions_for_user(request.user, school, request=request)
        payload = {
            "actions": serialize_actions(actions),
            "count": len(actions),
        }
        return JsonResponse(payload)


__all__ = (
    "CommandAction",
    "CommandBarActionsView",
    "all_registered",
    "get_actions_for_user",
    "serialize_actions",
)
