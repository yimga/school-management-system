"""Platform access policy — minimum security strength and exempt routes."""

from __future__ import annotations

from django.conf import settings

from apps.accounts.profile_security_evaluation import evaluate_user_profile_security
from apps.accounts.security_health import (
    get_minimum_security_score_for_role,
    is_within_grace_period,
)

# Routes users may reach while fixing security posture (must stay reachable).
MINIMUM_STRENGTH_EXEMPT_VIEW_NAMES = frozenset(
    {
        "accounts:security_posture_review",
        "accounts:user_profile",
        "accounts:profile_edit",
        "accounts:logout",
        "accounts:login",
        "accounts:mfa_verify",
        "accounts:mfa_setup",
        "accounts:password_change",
        "accounts:password_change_done",
        "accounts:sessions_page",
        "accounts:notification_preferences",
        "accounts:user_notifications",
        "accounts:operator_invite_accept",
        "accounts:tenant_staff_invite_accept",
    }
)


def platform_baseline_minimum_score() -> int:
    return max(0, min(100, int(getattr(settings, "SECURITY_PLATFORM_MINIMUM_SCORE", 40))))


def user_meets_platform_security_minimum(user, *, school=None) -> tuple[bool, str, dict]:
    """
    Return (allowed, block_reason, evaluation_dict).
    Operators on manager host are evaluated separately (caller should skip).
    """
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return True, "", {}
    if is_within_grace_period(user, school):
        return True, "", {}

    evaluation = evaluate_user_profile_security(user, school=school)
    score = int(evaluation.get("security_score") or 0)
    role_min = float(evaluation.get("minimum_score_for_role") or 0)
    baseline = float(platform_baseline_minimum_score())
    required = max(role_min, baseline)

    if score >= required:
        return True, "", evaluation

    if role_min >= baseline and role_min > 0:
        reason = "role_minimum"
    elif score < baseline:
        reason = "platform_baseline"
    else:
        reason = "below_minimum"

    return False, reason, evaluation


def evaluation_access_flags(evaluation: dict) -> dict:
    """Derived flags for templates and context processors."""
    score = int(evaluation.get("security_score") or 0)
    role_min = float(evaluation.get("minimum_score_for_role") or 0)
    baseline = float(platform_baseline_minimum_score())
    required = max(role_min, baseline)
    gap = max(0, int(required - score))
    return {
        "security_minimum_required": int(required),
        "security_minimum_gap": gap,
        "meets_platform_minimum": score >= required,
        "platform_baseline_minimum": int(baseline),
    }
