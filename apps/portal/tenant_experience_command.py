"""Role-aware tenant experience command strip.

This module keeps the tenant role homes focused on one question: what is ready,
what needs attention, and which tool should the user open next. It deliberately
uses defensive lookups so a partially configured school still renders a useful
tenant surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.siteconfig.tenant_country_readiness import country_readiness_context


@dataclass(frozen=True)
class ExperienceAction:
    label: str
    url: str
    icon: str
    meta: str = ""
    tone: str = "neutral"

    def as_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "url": self.url,
            "icon": self.icon,
            "meta": self.meta,
            "tone": self.tone,
        }


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except (NoReverseMatch, AttributeError, TypeError, ValueError):
        return ""


def _first_attr(*objects: Any, names: tuple[str, ...]) -> str:
    for obj in objects:
        if obj is None:
            continue
        for name in names:
            value = getattr(obj, name, None)
            if value:
                return str(value).strip()
    return ""


def _country_code(request: HttpRequest) -> str:
    school = getattr(request, "school", None)
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    code = _first_attr(
        school,
        site,
        names=("country_code", "country", "default_country", "region"),
    )
    return code[:2].upper() if code else ""


def _local_global_payload(request: HttpRequest) -> dict[str, str | bool | int]:
    ctx = country_readiness_context(request)
    code = str(ctx.get("country_code") or "")
    from apps.siteconfig.local_experience_resolver import resolve_local_experience_for_country

    deep = resolve_local_experience_for_country(code) if code else {"configured": False}
    return {
        "configured": bool(ctx.get("configured")),
        "label": str(ctx.get("label") or ""),
        "detail": str(ctx.get("detail") or ""),
        "currency": str(ctx.get("currency") or ""),
        "rail": str(ctx.get("rail") or ""),
        "country_code": code,
        "readiness_status": str(ctx.get("readiness_status") or ""),
        "auto_bonus": int(ctx.get("auto_bonus") or 0),
        "experience_depth": str(deep.get("depth") or "none"),
        "profile_key": str(deep.get("profile_key") or ""),
        "profile_count": int(deep.get("profile_count") or 0),
    }


def _profile_payload(request: HttpRequest) -> dict[str, Any]:
    user = getattr(request, "user", None)
    email = str(getattr(user, "email", "") or "").strip()
    full_name = ""
    if user is not None:
        try:
            full_name = str(user.get_full_name() or "").strip()
        except (AttributeError, TypeError, ValueError):
            full_name = ""
    has_name = bool(full_name or getattr(user, "first_name", None))
    has_email = bool(email and not email.lower().startswith("pending"))
    profile_url = _safe_reverse("accounts:user_profile")
    score = int(round(((1 if has_name else 0) + (1 if has_email else 0)) / 2 * 100))
    return {
        "score": score,
        "label": str(_("Profile ready")) if score >= 100 else str(_("Profile needs detail")),
        "detail": str(_("Name and verified email are complete."))
        if score >= 100
        else str(_("Complete your name and email so school workflows stay personal.")),
        "url": profile_url,
    }


def _school_readiness_payload(request: HttpRequest) -> dict[str, Any]:
    school = getattr(request, "school", None)
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    checks = [
        {
            "label": str(_("Identity")),
            "done": bool(_first_attr(school, site, names=("name", "site_name"))),
        },
        {
            "label": str(_("Local rails")),
            "done": bool(_local_global_payload(request)["configured"]),
        },
        {
            "label": str(_("Brand")),
            "done": bool(
                _first_attr(
                    school,
                    site,
                    names=("logo_url", "site_logo", "primary_color", "brand_primary"),
                )
            ),
        },
        {
            "label": str(_("Academic year")),
            "done": bool(
                _first_attr(
                    site,
                    names=("active_academic_year_name", "current_academic_year_label"),
                )
            ),
        },
    ]
    done = sum(1 for check in checks if check["done"])
    score = int(round((done / len(checks)) * 100)) if checks else 0
    return {
        "score": score,
        "label": str(_("School setup")),
        "detail": str(_("%(done)s of %(total)s essentials ready") % {"done": done, "total": len(checks)}),
        "checks": checks,
        "url": _safe_reverse("school_studio_readiness") or _safe_reverse("school_studio"),
    }


def _role_actions(role: str) -> list[ExperienceAction]:
    role_upper = (role or "").upper()
    school_operator_roles = {
        User.Role.ADMIN,
        User.Role.SUPERADMIN,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.DEAN,
        User.Role.CENSOR,
        User.Role.BURSAR,
        User.Role.HOD,
        User.Role.DEPT_LEAD,
        User.Role.FINANCE_STAFF,
        User.Role.ACADEMICS_STAFF,
        User.Role.COMMS_STAFF,
        User.Role.SECRETARY,
        User.Role.EXECUTIVE_ASSISTANT,
        User.Role.IT_ADMIN,
        User.Role.BOARDING_MANAGER,
        User.Role.ACCOUNTANT,
        User.Role.PROPRIETOR,
        User.Role.DISCIPLINE_MASTER,
    }
    if role_upper in school_operator_roles:
        specs = [
            ("School Studio", "school_studio", "bi-grid-1x2", "Configure the tenant", "primary"),
            ("Import setup", "school_setup_imports", "bi-cloud-arrow-up", "Move data in", "warning"),
            ("Template marketplace", "template_marketplace:browse", "bi-stars", "Upgrade the experience", "primary"),
            ("Finance setup", "finance:dashboard", "bi-wallet2", "Money and fees", "neutral"),
            ("Help center", "feedback:help_center", "bi-life-preserver", "Self-serve support", "neutral"),
        ]
    elif role_upper == User.Role.TEACHER:
        specs = [
            ("Teacher workflow", "portal:teacher_workflow", "bi-diagram-3", "Next teaching step", "primary"),
            ("Take attendance", "portal:teacher_attendance", "bi-calendar-check", "Start the day", "primary"),
            ("Enter marks", "evals:teacher_marks_entry", "bi-pencil-square", "Close grading gaps", "warning"),
            ("Syllabus", "portal:portal_syllabus", "bi-journal-text", "Share learning plan", "neutral"),
            ("Timetable", "portal:teacher_timetable", "bi-table", "Next class", "neutral"),
            ("Messages", "accounts:user_messages", "bi-chat-dots", "Parent and school threads", "neutral"),
        ]
    elif role_upper == User.Role.STUDENT:
        specs = [
            ("Student workflow", "portal:student_workflow", "bi-diagram-3", "Next learning step", "primary"),
            ("Messages", "accounts:user_messages", "bi-chat-dots", "School updates", "primary"),
            ("Syllabus", "portal:portal_syllabus", "bi-journal-text", "Learning resources", "primary"),
            ("Profile", "accounts:user_profile", "bi-person-badge", "Account readiness", "neutral"),
            ("Help", "feedback:help_center", "bi-life-preserver", "Get unstuck", "neutral"),
        ]
    else:
        specs = [
            ("Family workflow", "portal:parent_workflow", "bi-diagram-3", "Next family step", "primary"),
            ("Finance", "portal:parent_finance", "bi-wallet2", "Fees and receipts", "warning"),
            ("Results", "portal:parent_dashboard", "bi-bar-chart", "Progress snapshot", "neutral"),
            ("Contact school", "portal:parent_contact_school", "bi-chat-dots", "Ask a question", "neutral"),
            ("Link child", "portal:link_child", "bi-link-45deg", "Add a learner", "neutral"),
        ]
    return [
        ExperienceAction(label=str(_(label)), url=url, icon=icon, meta=str(_(meta)), tone=tone)
        for label, name, icon, meta, tone in specs
        if (url := _safe_reverse(name))
    ]


def build_tenant_experience_command(request: HttpRequest, role: str) -> dict[str, Any]:
    """Return the tenant command payload used by all role-home dashboards."""
    from apps.siteconfig.tenant_experience_policy import (
        compute_weighted_experience_score,
        experience_score_band,
        resolve_tenant_experience_policy,
    )

    policy = resolve_tenant_experience_policy(request, apply_role_overlay=True, role=role)
    local_global = _local_global_payload(request)
    country_ctx = country_readiness_context(request)
    profile = _profile_payload(request)
    school = _school_readiness_payload(request)
    actions = [action.as_dict() for action in _role_actions(role)]
    score = compute_weighted_experience_score(
        int(profile["score"]),
        int(school["score"]),
        policy,
        country_configured=bool(local_global.get("configured")),
        country_ctx=country_ctx,
    )
    score_band = experience_score_band(score, policy)
    score_label = (policy.get("experience_score_label") or "").strip() or str(
        _("Tenant readiness")
    )
    return {
        "enabled": bool(policy.get("show_experience_command_strip", True)),
        "role": (role or "").upper() or "TENANT",
        "score": score,
        "score_band": score_band,
        "score_ready_threshold": int(policy.get("experience_score_ready_threshold", 75)),
        "score_attention_threshold": int(
            policy.get("experience_score_attention_threshold", 50)
        ),
        "score_label": score_label,
        "experience_preset": str(
            policy.get("effective_experience_preset")
            or policy.get("experience_preset")
            or "custom"
        ),
        "experience_policy_role_bucket": str(
            policy.get("experience_policy_role_bucket") or ""
        ),
        "country_readiness_status": str(local_global.get("readiness_status") or ""),
        "country_auto_bonus": int(local_global.get("auto_bonus") or 0),
        "local_experience_depth": str(local_global.get("experience_depth") or "none"),
        "local_profile_key": str(local_global.get("profile_key") or ""),
        "mission_eyebrow": (policy.get("mission_eyebrow") or "").strip(),
        "mission_cta_label": (policy.get("mission_cta_label") or "").strip(),
        "local_global": local_global,
        "profile": profile,
        "school": school,
        "actions": actions,
        "primary_action": actions[0] if actions else {},
        "secondary_actions": actions[1:5],
    }
