"""MFA enforcement-policy control — operator platform default + per-tenant override.

The platform mandates MFA for privileged roles (matching Salesforce / AWS /
GitHub). What this surface configures is *how* that mandate is rolled out:

  * ``strict``   — require MFA before access (the original hard wall).
  * ``grace``    — allow access + nudge, hard-enforce after ``grace_period_days``.
  * ``optional`` — never block; nudge only (for test / demo tenants).

``GET`` renders a small server-side form (no JS dependency). ``POST`` applies it:
  * ``scope=tenant``   — per-school override; requires ``settings.manage``.
    ``mode=inherit`` clears the override so the platform default shines through.
  * ``scope=platform`` — platform-wide default; requires control-plane access.

Reads/writes ride the same runtime-defaults cascade as ``ai_mode`` — the
resolved value is consumed by ``apps.accounts.middleware.RequireMFAMiddleware``
via ``apps.accounts.mfa_defaults.resolve_mfa_enforcement``.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.mfa_defaults import (
    DEFAULT_MFA_GRACE_PERIOD_DAYS,
    MFA_MODE_STRICT,
    VALID_MFA_ENFORCEMENT_MODES,
    normalize_mfa_mode,
)
from apps.platform_runtime.config_resolver import get_effective_config

_CLEAR_TOKENS = {"", "inherit", "default", "none"}
_MAX_GRACE_DAYS = 365  # magic-number-allow: form upper bound for grace window


def _can_manage_tenant(request: Any) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(user.has_perm("settings.manage"))


def _can_manage_platform(request: Any) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        return bool(user_has_control_plane_access(user))
    except Exception:  # noqa: BLE001 — fail closed on resolver error
        return False


def _platform_default_mode_and_days() -> tuple[str, int]:
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.filter(pk=1).first()
        mode = normalize_mfa_mode(getattr(rd, "mfa_enforcement_mode", None)) if rd else MFA_MODE_STRICT
        days = getattr(rd, "mfa_grace_period_days", None) if rd else None
    except Exception:  # noqa: BLE001
        mode, days = MFA_MODE_STRICT, None
    try:
        days_int = int(days)
    except (TypeError, ValueError):
        days_int = DEFAULT_MFA_GRACE_PERIOD_DAYS
    return mode, days_int


def _tenant_override(school: Any) -> dict[str, Any]:
    if school is None:
        return {}
    bucket = (getattr(school, "settings", None) or {}).get("runtime_defaults") or {}
    if not isinstance(bucket, dict):
        return {}
    out: dict[str, Any] = {}
    if bucket.get("mfa_enforcement_mode"):
        out["mode"] = normalize_mfa_mode(bucket.get("mfa_enforcement_mode"))
    if bucket.get("mfa_grace_period_days") is not None:
        out["grace_period_days"] = bucket.get("mfa_grace_period_days")
    return out


def mfa_policy_state(request: Any) -> dict[str, Any]:
    school = getattr(request, "school", None)
    eff_mode = normalize_mfa_mode(
        get_effective_config(key="mfa_enforcement_mode", request=request)
    )
    try:
        eff_days = int(get_effective_config(key="mfa_grace_period_days", request=request))
    except (TypeError, ValueError):
        eff_days = DEFAULT_MFA_GRACE_PERIOD_DAYS
    plat_mode, plat_days = _platform_default_mode_and_days()
    return {
        "effective_mode": eff_mode,
        "effective_grace_days": eff_days,
        "platform_default_mode": plat_mode,
        "platform_default_grace_days": plat_days,
        "tenant_override": _tenant_override(school),
        "available_modes": list(VALID_MFA_ENFORCEMENT_MODES),
        "default_grace_days": DEFAULT_MFA_GRACE_PERIOD_DAYS,
        "max_grace_days": _MAX_GRACE_DAYS,
        "can_set_tenant": bool(school is not None and _can_manage_tenant(request)),
        "can_set_platform": _can_manage_platform(request),
        "has_school": school is not None,
        "school_name": getattr(school, "name", "") if school is not None else "",
    }


def _clear_tenant_override(school: Any) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    bucket = dict(settings.get("runtime_defaults") or {})
    changed = False
    for key in ("mfa_enforcement_mode", "mfa_grace_period_days"):
        if key in bucket:
            bucket.pop(key, None)
            changed = True
    if changed:
        settings["runtime_defaults"] = bucket
        school.settings = settings
        school.save(update_fields=["settings"])


def _coerce_grace_days(raw: object) -> int:
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MFA_GRACE_PERIOD_DAYS
    if days < 0:
        return 0
    if days > _MAX_GRACE_DAYS:
        return _MAX_GRACE_DAYS
    return days


@require_http_methods(["GET", "POST"])
def mfa_policy_view(request):  # rbac-allow: self-gates per scope (settings.manage for tenant, control-plane for platform)
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return redirect("accounts:login")

    if request.method == "GET":
        return render(request, "portal/mfa_policy.html", mfa_policy_state(request))

    mode_raw = (request.POST.get("mode") or "").strip().lower()
    scope = (request.POST.get("scope") or "").strip().lower()
    school = getattr(request, "school", None)
    if not scope:
        scope = "tenant" if school is not None else "platform"

    clearing = mode_raw in _CLEAR_TOKENS
    if not clearing and mode_raw not in VALID_MFA_ENFORCEMENT_MODES:
        messages.error(request, _("Invalid MFA enforcement mode."))
        return redirect("portal:mfa_policy")

    grace_days = _coerce_grace_days(request.POST.get("grace_period_days"))

    if scope == "platform":
        if not _can_manage_platform(request):
            messages.error(request, _("You do not have permission to change the platform default."))
            return redirect("portal:mfa_policy")
        from apps.platform_runtime.models import RuntimeDefaults

        rd, _created = RuntimeDefaults.objects.get_or_create(pk=1)
        rd.mfa_enforcement_mode = None if clearing else mode_raw
        rd.mfa_grace_period_days = None if clearing else grace_days
        rd.save(update_fields=["mfa_enforcement_mode", "mfa_grace_period_days", "updated_at"])
        messages.success(request, _("Platform MFA enforcement default updated."))
    elif scope == "tenant":
        if school is None:
            messages.error(request, _("No school in context for a tenant override."))
            return redirect("portal:mfa_policy")
        if not _can_manage_tenant(request):
            messages.error(request, _("You do not have permission to change this school's policy."))
            return redirect("portal:mfa_policy")
        if clearing:
            _clear_tenant_override(school)
            messages.success(request, _("This school now inherits the platform MFA default."))
        else:
            from apps.platform_runtime.runtime_defaults_first_class import (
                set_runtime_default,
            )

            set_runtime_default(school=school, field="mfa_enforcement_mode", value=mode_raw)
            set_runtime_default(school=school, field="mfa_grace_period_days", value=grace_days)
            messages.success(request, _("This school's MFA enforcement policy updated."))
    else:
        messages.error(request, _("Invalid scope."))

    try:
        from apps.siteconfig.config_service import invalidate_effective_site_settings_cache

        invalidate_effective_site_settings_cache()
    except Exception:  # noqa: BLE001 — cache invalidation is best-effort
        pass
    return redirect("portal:mfa_policy")
