"""Tenant role-home hero + legacy dashboard gate (Preview Shell 100x)."""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.siteconfig.models_support import filter_portal_items
from apps.siteconfig.config_service import get_effective_site_settings

# Authenticated tenant role-home landings (preview: tenant-portal-v3-100x).
TP_V3_ROLE_HOME_URL_NAMES = frozenset(
    {
        "backend_dashboard",
        "backend_dashboard_alt",
        "parent_dashboard",
        "home",
        "portal_home",
        "teacher_dashboard_alias",
        "teacher_dashboard",
        "student_portal_grades",
    }
)


def role_home_show_legacy(request: HttpRequest) -> bool:
    """Opt-in full legacy stack via ``?simple=1`` (matches parent simplified mode)."""
    raw = request.GET.get("simple", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "legacy"}


def is_tenant_role_home_landing_request(request: HttpRequest) -> bool:
    """True on any authenticated tenant role-home URL (v3 canvas or legacy stack)."""
    if getattr(request, "public_host_kind", None) == "manager":
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    match = getattr(request, "resolver_match", None)
    if match is None:
        return False
    url_name = getattr(match, "url_name", None) or ""
    return url_name in TP_V3_ROLE_HOME_URL_NAMES


def is_tp_v3_role_home_request(request: HttpRequest) -> bool:
    """True on tenant role-home landings when the v3 100x canvas should own the page."""
    if getattr(request, "public_host_kind", None) == "manager":
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    match = getattr(request, "resolver_match", None)
    if match is None:
        return False
    url_name = getattr(match, "url_name", None) or ""
    if url_name not in TP_V3_ROLE_HOME_URL_NAMES:
        return False
    return not role_home_show_legacy(request)


def is_tp_v3_tenant_shell_request(request: HttpRequest) -> bool:
    """True on authenticated tenant portal pages (preview header + canvas grammar)."""
    if getattr(request, "public_host_kind", None) == "manager":
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", None) or "" if match else ""
    if role_home_show_legacy(request) and url_name in TP_V3_ROLE_HOME_URL_NAMES:
        return False
    namespace = getattr(match, "namespace", None) or "" if match else ""
    if namespace == "studio_os":
        return False
    return True


def _tp_brand_surface_pill(role: str) -> str:
    mapping = {
        "ADMIN": _("Admin workspace"),
        "SUPERADMIN": _("Admin workspace"),
        "TEACHER": _("Teacher workspace"),
        "PARENT": _("Family portal"),
        "STUDENT": _("Student portal"),
    }
    return str(mapping.get((role or "").upper(), _("School portal")))


def _tp_brand_tagline(role: str) -> str:
    mapping = {
        "ADMIN": _("School command surface"),
        "SUPERADMIN": _("School command surface"),
        "TEACHER": _("Teaching day at a glance"),
        "PARENT": _("Your children's school life"),
        "STUDENT": _("Your learning journey"),
    }
    return str(mapping.get((role or "").upper(), _("Your school workspace")))


def tp_v3_role_home_shell_context(request: HttpRequest) -> dict[str, object]:
    """Shell flags for portal_base (dedupe chrome + preview parity)."""
    active = is_tp_v3_role_home_request(request)
    tenant_shell = is_tp_v3_tenant_shell_request(request)
    role = ""
    user = getattr(request, "user", None)
    if user is not None:
        role = str(getattr(user, "role", "") or "")
    year_label = ""
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        site = get_effective_site_settings(request=request)
        year_name = getattr(site, "active_academic_year_name", None) or getattr(
            site, "current_academic_year_label", None
        )
        if year_name:
            year_label = str(year_name)
    except (AttributeError, ImportError, TypeError, ValueError):
        year_label = ""
    return {
        "tp_v3_role_home": active,
        "tp_v3_tenant_shell": tenant_shell,
        "tenant_role_home_landing": is_tenant_role_home_landing_request(request),
        "page_provides_own_h1": active,
        "tp_brand_surface_pill": _tp_brand_surface_pill(role),
        "tp_brand_tagline": _tp_brand_tagline(role),
        "tp_brand_year_label": year_label,
    }


def tp_hero_ai_tier_line() -> str:
    """PII-safe one-line assist tier summary (deployment profile chain, no secrets)."""
    from services.ai_deployment_posture import default_tier_chain_for_profile

    label_map = {
        "litellm": str(_("Cloud")),
        "ollama": str(_("Local")),
        "rules": str(_("Guided")),
    }
    chain = default_tier_chain_for_profile()
    parts = [label_map.get(tier, tier) for tier in chain]
    return str(_("Assist tier: %(tiers)s") % {"tiers": " → ".join(parts)})


def _unread_messages_count(request: HttpRequest) -> int:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    school = getattr(request, "school", None)
    if school is None:
        return 0
    try:
        from apps.communication.models import Message

        return Message.objects.filter(
            school=school,
            recipient=user,
            is_read=False,
            is_archived=False,
        ).count()
    except Exception:
        return 0


def build_tp_hero_contextual_line(
    *,
    role: str,
    has_fees_due: bool = False,
    pending_signatures: int = 0,
    unread_messages: int = 0,
    attendance_pct: int | None = None,
    pending_evaluations: int = 0,
    pending_access_requests: int = 0,
    completion_pct: int | None = None,
) -> str:
    """PII-safe one-line attention summary for the role-home hero."""
    hints: list[str] = []
    role_upper = (role or "").upper()
    if has_fees_due:
        hints.append(str(_("Fees need attention")))
    if pending_signatures > 0:
        hints.append(
            str(_("%(n)s signature(s) pending") % {"n": pending_signatures})
        )
    if unread_messages > 0 and role_upper != User.Role.PARENT:
        hints.append(str(_("%(n)s unread message(s)") % {"n": unread_messages}))
    if attendance_pct is not None and attendance_pct < 85:
        hints.append(str(_("Attendance below 85%")))
    if role_upper == User.Role.TEACHER:
        if pending_evaluations > 0:
            hints.append(
                str(_("%(n)s mark(s) pending") % {"n": pending_evaluations})
            )
        if completion_pct is not None and completion_pct < 75:
            hints.append(str(_("Grading completion below 75%")))
    if role_upper in {User.Role.ADMIN, User.Role.SUPERADMIN}:
        if pending_access_requests > 0:
            hints.append(
                str(_("%(n)s access request(s) pending") % {"n": pending_access_requests})
            )
    if not hints:
        return str(_("You're caught up for now."))
    return " · ".join(hints)


def build_tp_hero_context(
    request: HttpRequest,
    *,
    role: str,
    children_names: str = "",
    has_fees_due: bool = False,
    pending_signatures: int = 0,
    unread_messages: int | None = None,
    attendance_pct: int | None = None,
    pending_evaluations: int = 0,
    pending_access_requests: int = 0,
    completion_pct: int | None = None,
) -> dict[str, object]:
    site = get_effective_site_settings(request=request)
    portal_quick_actions = filter_portal_items(
        getattr(site, "portal_quick_actions", None) or [], role
    )
    if unread_messages is None:
        unread_messages = _unread_messages_count(request)
    return {
        "tp_greeting_role": role,
        "tp_greeting_children_names": children_names,
        "portal_quick_actions": portal_quick_actions,
        "has_fees_due": has_fees_due,
        "tp_hero_ai_tier_line": tp_hero_ai_tier_line(),
        "tp_hero_contextual_line": build_tp_hero_contextual_line(
            role=role,
            has_fees_due=has_fees_due,
            pending_signatures=pending_signatures,
            unread_messages=unread_messages,
            attendance_pct=attendance_pct,
            pending_evaluations=pending_evaluations,
            pending_access_requests=pending_access_requests,
            completion_pct=completion_pct,
        ),
        "tenant_experience_command": _tenant_experience_command_safe(request, role),
    }


def _tenant_experience_command_safe(
    request: HttpRequest, role: str
) -> dict[str, object]:
    try:
        from apps.portal.tenant_experience_command import (
            build_tenant_experience_command,
        )

        return build_tenant_experience_command(request, role)
    except Exception:
        return {"enabled": False, "actions": []}
