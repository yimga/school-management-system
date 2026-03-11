"""
Security & Identity Powerhouse (plan 3.13–3.23).
SecurityTask registry and SecurityHealth service: calculate_profile_strength(user) → 0–100%.
Weights: Password 20%, MFA 30%, Identity 15%, Passkeys 20%, Recovery 15%.
Region-aware (stricter for EU); configurable weights per tenant; grace period for new users.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Default weights (plan); can be overridden per region in SecurityTaskRegistry
DEFAULT_WEIGHTS = {
    "password_strength": 20,
    "mfa_verification": 30,
    "identity_verification": 15,
    "biometric_passkeys": 20,
    "security_recovery": 15,
}

# Max points per task (normalized to 100 total)
TOTAL_POINTS = 100


@dataclass
class SecurityTask:
    """Single security task with point value and checker."""
    code: str
    points: int
    label_key: str  # i18n key for labels_map
    check: Callable[[object], bool]  # (user) -> True if satisfied


def _check_password_strength(user) -> bool:
    """
    Password strength: backend cannot read raw password (stored hashed).
    Use stored password_strength_score if set (from form when user sets password with zxcvbn);
    else consider 'has non-unusable password' as minimal pass.
    """
    if not user or not hasattr(user, "password") or not user.password:
        return False
    if user.password.startswith("!"):  # unusable
        return False
    score = getattr(user, "password_strength_score", None)
    if score is not None:
        return int(score) >= 3
    return True  # has a set password; frontend should run zxcvbn on change and store score


def _check_mfa(user) -> bool:
    """MFA: TOTP or static backup configured (django_otp)."""
    if not user or not user.is_authenticated:
        return False
    try:
        from django_otp import user_has_device
        return user_has_device(user, confirmed=True)
    except Exception:
        return False


def _check_identity_verified(user) -> bool:
    """Identity: verified email and phone (OTP). Use EmailAddress.verified and a phone_verified flag if present."""
    if not user or not user.is_authenticated:
        return False
    email_ok = False
    try:
        from allauth.account.models import EmailAddress
        email_ok = EmailAddress.objects.filter(user=user, verified=True).exists()
    except Exception:
        if getattr(user, "email", None) and getattr(user, "is_active", True):
            email_ok = True  # fallback when allauth not used
    phone_ok = getattr(user, "phone_verified", False) or getattr(user, "profile_phone_verified", False)
    return email_ok and phone_ok


def _check_passkeys(user) -> bool:
    """WebAuthn/Passkeys: at least one credential (UserPasskey or equivalent)."""
    if not user or not user.is_authenticated:
        return False
    try:
        from apps.accounts.models import UserPasskey
        return UserPasskey.objects.filter(user=user).exists()
    except Exception:
        return False


def _check_recovery(user) -> bool:
    """Recovery: backup codes or verified recovery email."""
    if not user or not user.is_authenticated:
        return False
    has_static = False
    try:
        from django_otp.plugins.otp_static.models import StaticDevice
        has_static = StaticDevice.objects.filter(user=user, confirmed=True).exists()
    except Exception:
        pass
    recovery_email_verified = getattr(user, "recovery_email_verified", False)
    return has_static or recovery_email_verified


class SecurityTaskRegistry:
    """
    Registry of security tasks with point values.
    Region/school can override weights via get_security_weights(school).
    """
    _tasks: list[SecurityTask] = [
        SecurityTask("password_strength", DEFAULT_WEIGHTS["password_strength"], "security.task.password", _check_password_strength),
        SecurityTask("mfa_verification", DEFAULT_WEIGHTS["mfa_verification"], "security.task.mfa", _check_mfa),
        SecurityTask("identity_verification", DEFAULT_WEIGHTS["identity_verification"], "security.task.identity", _check_identity_verified),
        SecurityTask("biometric_passkeys", DEFAULT_WEIGHTS["biometric_passkeys"], "security.task.passkeys", _check_passkeys),
        SecurityTask("security_recovery", DEFAULT_WEIGHTS["security_recovery"], "security.task.recovery", _check_recovery),
    ]

    @classmethod
    def get_tasks(cls):
        return list(cls._tasks)

    @classmethod
    def get_weights(cls, school=None):
        """Configurable weights per tenant/region (e.g. stricter EU)."""
        if school is None:
            return DEFAULT_WEIGHTS
        try:
            from apps.policies.policy_registry import get_effective_policy
            policy = get_effective_policy(school)
            w = policy.get("security_weights") or policy.get("security_weights_override")
            if isinstance(w, dict):
                return {**DEFAULT_WEIGHTS, **w}
            from apps.siteconfig.tenant_config import get_tenant_locale
            config = get_tenant_locale(school=school) or {}
            w = config.get("security_weights") or config.get("security_weights_override")
            if isinstance(w, dict):
                return {**DEFAULT_WEIGHTS, **w}
        except Exception:
            pass
        return DEFAULT_WEIGHTS


def calculate_profile_strength(user, school=None, use_cache=True) -> float:
    """
    Return security health score 0–100.
    Optional cache (TTL 5 min) keyed by tenant + user.pk (World Engine §8).
    """
    if not user or not user.is_authenticated:
        return 0.0
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix
        school_id = getattr(school, "id", None) or getattr(user, "school_id", None)
        prefix = f"school:{school_id}" if school_id else get_tenant_cache_prefix()
    except Exception:
        prefix = "public"
    cache_key = f"{prefix}:security_strength:{user.pk}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return float(cached)
    weights = SecurityTaskRegistry.get_weights(school)
    earned = 0.0
    for task in SecurityTaskRegistry.get_tasks():
        w = weights.get(task.code, DEFAULT_WEIGHTS.get(task.code, 0))
        if task.check(user):
            earned += w
    score = min(100.0, max(0.0, (earned / TOTAL_POINTS) * 100.0))
    if use_cache:
        cache.set(cache_key, score, timeout=300)  # 5 min
    return round(score, 1)


def get_missing_tasks(user, school=None) -> list[dict]:
    """List of tasks not yet satisfied: [{code, points, label_key}, ...]."""
    if not user or not user.is_authenticated:
        return [{"code": t.code, "points": t.points, "label_key": t.label_key} for t in SecurityTaskRegistry.get_tasks()]
    weights = SecurityTaskRegistry.get_weights(school)
    out = []
    for task in SecurityTaskRegistry.get_tasks():
        if not task.check(user):
            w = weights.get(task.code, task.points)
            out.append({"code": task.code, "points": w, "label_key": task.label_key})
    return out


def get_security_grace_period_days(school=None) -> int:
    """Days before new users are subject to wizard redirect (e.g. 7)."""
    try:
        if school:
            from apps.policies.policy_registry import get_effective_policy
            policy = get_effective_policy(school)
            if "security_grace_period_days" in policy:
                return int(policy["security_grace_period_days"])
        from apps.siteconfig.tenant_config import get_tenant_locale
        config = get_tenant_locale(school=school) or {}
        return int(config.get("security_grace_period_days", 7))
    except Exception:
        pass
    return 7


def is_within_grace_period(user, school=None) -> bool:
    """True if user is new and should not be forced to wizard yet."""
    if not user or not getattr(user, "date_joined", None):
        return True
    from datetime import timedelta
    grace_days = get_security_grace_period_days(school or getattr(user, "school", None))
    return timezone.now() - user.date_joined < timedelta(days=grace_days)


def get_minimum_security_score_for_role(role_code: str, school=None) -> float:
    """Stricter minimum for Admins and Financial staff (plan 3.21)."""
    strict_roles = ("ADMIN", "SUPERADMIN", "BURSAR", "ACCOUNTANT", "FINANCE_STAFF", "PROPRIETOR")
    if (role_code or "").upper() in strict_roles:
        return 80.0
    return 0.0
