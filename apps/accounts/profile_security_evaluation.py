"""
Platform-wide profile + security evaluation (all authenticated users).
Mirrors src/lib/profileSecurityEvaluation.ts contract for SSR and JSON APIs.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, TypedDict

from django.utils import timezone

from apps.accounts.security_health import (
    get_minimum_security_score_for_role,
    _check_identity_verified,
    _check_mfa,
    _check_passkeys,
    _check_password_strength,
    _check_recovery,
)


class CriticalVulnerability(TypedDict):
    threat: str
    exploit_vector: str
    remediation_step: str


class UxOptimization(TypedDict):
    missing_element: str
    impact: str
    fix_action: str


class ProfileSecurityEvaluation(TypedDict, total=False):
    security_score: int
    profile_completeness: int
    critical_vulnerabilities: list[CriticalVulnerability]
    ux_optimizations: list[UxOptimization]
    strength_band: str
    strength_label: str
    gauge_arc_offset: int
    security_posture_review_due: bool
    days_until_posture_review: int | None
    minimum_score_for_role: float
    security_minimum_required: int
    security_minimum_gap: int
    meets_platform_minimum: bool
    platform_baseline_minimum: int


MFA_CAP = 40
CRITICAL_EMAIL = "Unverified email address"
CRITICAL_PASSWORD = "Password reset required"
CRITICAL_WEAK_PASSWORD = "Weak account password"


def _email_verified(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "pk", None):
        return False
    try:
        from allauth.account.models import EmailAddress

        if not getattr(user, "email", None):
            return False
        return EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists()
    except (ImportError, AttributeError, TypeError):
        return bool(getattr(user, "email", None) and getattr(user, "is_active", True))


def _has_email(user) -> bool:
    return bool(getattr(user, "email", None) and str(user.email).strip())


def get_password_rotation_days(user, school=None) -> int:
    """0 disables calendar expiry. High-trust roles default to 90 days."""
    role = getattr(user, "role", None) or ""
    if get_minimum_security_score_for_role(role, school) < 80:
        return 0
    try:
        if school:
            from apps.policies.policy_registry import get_effective_policy

            policy = get_effective_policy(school)
            if "password_rotation_days" in policy:
                return max(0, int(policy["password_rotation_days"]))
        from apps.siteconfig.tenant_config import get_tenant_locale

        config = get_tenant_locale(school=school) or {}
        return max(0, int(config.get("password_rotation_days", 90)))
    except (ImportError, AttributeError, TypeError, KeyError, ValueError):
        return 90


def get_security_posture_review_interval_days(school=None) -> int:
    """Quarterly default (90 days); tenant policy may override."""
    try:
        if school:
            from apps.policies.policy_registry import get_effective_policy

            policy = get_effective_policy(school)
            if "security_posture_review_interval_days" in policy:
                return max(30, int(policy["security_posture_review_interval_days"]))
        from apps.siteconfig.tenant_config import get_tenant_locale

        config = get_tenant_locale(school=school) or {}
        return max(30, int(config.get("security_posture_review_interval_days", 90)))
    except (ImportError, AttributeError, TypeError, KeyError, ValueError):
        return 90


def is_security_posture_review_due(user, school=None) -> bool:
    if not user or not getattr(user, "pk", None):
        return False
    last = getattr(user, "last_security_posture_review_at", None)
    if not last:
        return True
    interval = get_security_posture_review_interval_days(school)
    return timezone.now() - last > timedelta(days=interval)


def days_until_security_posture_review(user, school=None) -> int | None:
    """Days remaining in current quarter window; None if already due."""
    if not user or not getattr(user, "pk", None):
        return None
    if is_security_posture_review_due(user, school):
        return 0
    last = getattr(user, "last_security_posture_review_at", None)
    if not last:
        return 0
    interval = get_security_posture_review_interval_days(school)
    due_at = last + timedelta(days=interval)
    return max(0, (due_at - timezone.now()).days)


def _password_expired(user, school=None) -> bool:
    if not user:
        return True
    if getattr(user, "requires_password_change", False):
        return True
    if not hasattr(user, "password") or not user.password or str(user.password).startswith("!"):
        return True
    rotation_days = get_password_rotation_days(user, school)
    if rotation_days <= 0:
        return False
    changed_at = getattr(user, "password_changed_at", None)
    if not changed_at:
        return False
    return timezone.now() - changed_at > timedelta(days=rotation_days)


def _phone_verified(user) -> bool:
    return bool(
        getattr(user, "phone_verified", False)
        or getattr(user, "profile_phone_verified", False)
    )


def _profile_phone_present(user) -> bool:
    return bool(getattr(user, "phone", None) and str(getattr(user, "phone", "")).strip())


def build_profile_security_input(
    user,
    *,
    school=None,
    active_sessions_count: int | None = None,
) -> dict[str, Any]:
    """Serialize User + session hints into evaluator input."""
    expired = _password_expired(user, school=school)
    return {
        "posture_review_due": is_security_posture_review_due(user, school),
        "mfa_enabled": _check_mfa(user),
        "email_verified": _email_verified(user),
        "has_email": _has_email(user),
        "password_expired": expired,
        "password_strength_ok": _check_password_strength(user) and not expired,
        "has_passkey": _check_passkeys(user),
        "has_recovery": _check_recovery(user),
        "phone_verified": _phone_verified(user),
        "session_count_high": bool(
            active_sessions_count is not None and active_sessions_count > 4
        ),
        "profile": {
            "has_photo": bool(getattr(user, "profile_photo", None)),
            "has_first_name": bool(
                getattr(user, "first_name", None) and str(user.first_name).strip()
            ),
            "has_last_name": bool(
                getattr(user, "last_name", None) and str(user.last_name).strip()
            ),
            "has_phone": _profile_phone_present(user),
        },
    }


def strength_band(score: int) -> str:
    if score < 40:
        return "weak"
    if score < 70:
        return "average"
    return "strong"


def strength_label(band: str) -> str:
    return {"weak": "At risk", "average": "Fair", "strong": "Strong"}.get(band, "Unknown")


def evaluate_profile_security(input_data: dict[str, Any]) -> ProfileSecurityEvaluation:
    """Pure evaluation — same rules as profileSecurityEvaluation.ts."""
    critical: list[CriticalVulnerability] = []
    ux: list[UxOptimization] = []

    mfa = bool(input_data.get("mfa_enabled"))
    email_verified = bool(input_data.get("email_verified"))
    has_email = bool(input_data.get("has_email"))
    password_expired = bool(input_data.get("password_expired"))
    password_ok = bool(input_data.get("password_strength_ok"))
    has_passkey = bool(input_data.get("has_passkey"))
    has_recovery = bool(input_data.get("has_recovery"))
    phone_verified = bool(input_data.get("phone_verified"))
    session_high = bool(input_data.get("session_count_high"))
    profile = input_data.get("profile") or {}

    if not has_email or not email_verified:
        critical.append(
            {
                "threat": CRITICAL_EMAIL,
                "exploit_vector": (
                    "Account takeover via password reset or social-engineering "
                    "of unverified inbox"
                ),
                "remediation_step": (
                    "Verify your email from account settings or complete the "
                    "verification link sent to your inbox"
                ),
            }
        )

    if password_expired:
        critical.append(
            {
                "threat": CRITICAL_PASSWORD,
                "exploit_vector": (
                    "Stale or administratively flagged credentials remain valid "
                    "until rotation"
                ),
                "remediation_step": "Change your password immediately from Security settings",
            }
        )
    elif not password_ok:
        critical.append(
            {
                "threat": CRITICAL_WEAK_PASSWORD,
                "exploit_vector": (
                    "Credential stuffing and offline hash cracking against weak secrets"
                ),
                "remediation_step": (
                    "Set a unique passphrase of 14+ characters with MFA enabled"
                ),
            }
        )

    if not mfa:
        critical.append(
            {
                "threat": "Multi-factor authentication disabled",
                "exploit_vector": "Single-factor compromise grants full account access",
                "remediation_step": (
                    "Enable TOTP authenticator or a passkey under MFA setup"
                ),
            }
        )

    security_score = 0
    if password_ok and not password_expired:
        security_score += 25
    if mfa:
        security_score += 30
    if email_verified and has_email:
        security_score += 20
    if has_passkey:
        security_score += 10
    if has_recovery:
        security_score += 10
    if phone_verified:
        security_score += 5

    if not mfa and security_score > MFA_CAP:
        security_score = MFA_CAP
    if critical and security_score > 55:
        security_score = 55
    security_score = max(0, min(100, int(security_score)))

    profile_completeness = 0
    if profile.get("has_first_name"):
        profile_completeness += 25
    if profile.get("has_last_name"):
        profile_completeness += 25
    if has_email:
        profile_completeness += 25
    if profile.get("has_photo"):
        profile_completeness += 15
    if profile.get("has_phone"):
        profile_completeness += 10
    profile_completeness = min(100, profile_completeness)

    if not profile.get("has_photo"):
        ux.append(
            {
                "missing_element": "Profile photo",
                "impact": (
                    "Harder for staff and families to recognize you in messages "
                    "and directories"
                ),
                "fix_action": "Upload a clear headshot on Edit profile",
            }
        )
    if not profile.get("has_first_name") or not profile.get("has_last_name"):
        ux.append(
            {
                "missing_element": "Legal display name",
                "impact": (
                    "Reports, certificates, and communications may show an "
                    "incomplete name"
                ),
                "fix_action": "Add first and last name on Edit profile",
            }
        )
    if not has_email:
        ux.append(
            {
                "missing_element": "Contact email",
                "impact": "No channel for password reset, invoices, or school alerts",
                "fix_action": "Add and verify an email address",
            }
        )
    if not profile.get("has_phone"):
        ux.append(
            {
                "missing_element": "Mobile phone",
                "impact": "SMS alerts and phone-based recovery remain unavailable",
                "fix_action": "Add a phone number when your school enables SMS",
            }
        )
    if session_high:
        ux.append(
            {
                "missing_element": "Session hygiene",
                "impact": (
                    "Multiple active devices increase exposure if one session "
                    "is abandoned"
                ),
                "fix_action": (
                    "Review active sessions and revoke devices you no longer use"
                ),
            }
        )

    if input_data.get("posture_review_due"):
        critical.append(
            {
                "threat": "Quarterly security review overdue",
                "exploit_vector": (
                    "Stale password/MFA/contact attestation increases account takeover risk"
                ),
                "remediation_step": "Complete the security posture review checklist",
            }
        )
        security_score = max(0, security_score - 12)

    band = strength_band(security_score)
    return {
        "security_score": security_score,
        "profile_completeness": profile_completeness,
        "critical_vulnerabilities": critical,
        "ux_optimizations": ux,
        "strength_band": band,
        "strength_label": strength_label(band),
        "gauge_arc_offset": 100 - security_score,
    }


def _empty_security_input() -> dict[str, Any]:
    return {
        "mfa_enabled": False,
        "email_verified": False,
        "has_email": False,
        "password_expired": True,
        "password_strength_ok": False,
        "has_passkey": False,
        "has_recovery": False,
        "phone_verified": False,
        "session_count_high": False,
        "profile": {
            "has_photo": False,
            "has_first_name": False,
            "has_last_name": False,
            "has_phone": False,
        },
    }


def evaluate_user_profile_security(
    user,
    *,
    school=None,
    active_sessions_count: int | None = None,
) -> ProfileSecurityEvaluation:
    if not user or not getattr(user, "pk", None):
        return evaluate_profile_security(_empty_security_input())
    payload = build_profile_security_input(
        user, school=school, active_sessions_count=active_sessions_count
    )
    result = evaluate_profile_security(payload)
    role = getattr(user, "role", None) or ""
    result["security_posture_review_due"] = is_security_posture_review_due(user, school)
    result["days_until_posture_review"] = days_until_security_posture_review(user, school)
    result["minimum_score_for_role"] = get_minimum_security_score_for_role(role, school)
    from apps.accounts.platform_access_policy import evaluation_access_flags

    result.update(evaluation_access_flags(result))
    return result


def record_security_posture_review(user) -> None:
    """Mark quarterly review complete for this user."""
    if not user or not getattr(user, "pk", None):
        return
    from apps.accounts.models import User

    User.objects.filter(pk=user.pk).update(
        last_security_posture_review_at=timezone.now()
    )
    user.last_security_posture_review_at = timezone.now()
