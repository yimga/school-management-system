"""AI mode switch endpoint — operator platform default + per-tenant override.

``GET``  returns the current AI-mode state (effective mode, platform default,
tenant override, and which scopes the current user may change).

``POST`` sets the mode:
  * ``scope=tenant``   — per-school override; requires ``settings.manage`` on a
    resolved school. ``mode=inherit`` (or blank) clears the override so the
    platform default shines through.
  * ``scope=platform`` — platform-wide default; requires control-plane /
    operator access. ``mode=inherit`` clears it back to ``auto``.

The switch is real: the resolved mode threads into the gateway tier filter via
``services.ai_helpers.invoke_with_request``, so ``local`` / ``cloud`` genuinely
change which provider serves each call; ``auto`` defers to the deployment profile.
"""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from services.ai_deployment_posture import (
    VALID_AI_MODES,
    normalize_ai_mode,
    resolve_effective_ai_mode,
)

_CLEAR_TOKENS = {"", "inherit", "default", "none"}


def _can_manage_tenant(request: Any) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    # Mirror the @permission_required("settings.manage") gate the tenant settings
    # views use, so the switch can never grant more than the settings page does.
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


def _platform_default_ai_mode() -> str:
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.filter(pk=1).first()
        return normalize_ai_mode(getattr(rd, "ai_mode", None)) if rd else "auto"
    except Exception:  # noqa: BLE001
        return "auto"


def _tenant_override_ai_mode(school: Any) -> str | None:
    if school is None:
        return None
    bucket = (getattr(school, "settings", None) or {}).get("runtime_defaults") or {}
    raw = bucket.get("ai_mode") if isinstance(bucket, dict) else None
    return normalize_ai_mode(raw) if raw else None


def ai_mode_state(request: Any) -> dict[str, Any]:
    school = getattr(request, "school", None)
    return {
        "effective_mode": resolve_effective_ai_mode(school),
        "platform_default": _platform_default_ai_mode(),
        "tenant_override": _tenant_override_ai_mode(school),
        "available_modes": list(VALID_AI_MODES),
        "can_set_tenant": bool(school is not None and _can_manage_tenant(request)),
        "can_set_platform": _can_manage_platform(request),
        "has_school": school is not None,
    }


def _clear_tenant_override(school: Any) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    bucket = dict(settings.get("runtime_defaults") or {})
    if "ai_mode" in bucket:
        bucket.pop("ai_mode", None)
        settings["runtime_defaults"] = bucket
        school.settings = settings
        school.save(update_fields=["settings"])


@require_http_methods(["GET", "POST"])
def ai_mode_view(request):  # rbac-allow: self-gates per scope (settings.manage for tenant, control-plane for platform); GET returns non-sensitive state
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return JsonResponse({"ok": False, "error": "authentication_required"}, status=403)

    if request.method == "GET":
        return JsonResponse({"ok": True, **ai_mode_state(request)})

    mode_raw = (request.POST.get("mode") or "").strip().lower()
    scope = (request.POST.get("scope") or "").strip().lower()
    school = getattr(request, "school", None)
    if not scope:
        scope = "tenant" if school is not None else "platform"

    clearing = mode_raw in _CLEAR_TOKENS
    if not clearing and mode_raw not in VALID_AI_MODES:
        return JsonResponse({"ok": False, "error": "invalid_mode"}, status=400)

    if scope == "platform":
        if not _can_manage_platform(request):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
        from apps.platform_runtime.models import RuntimeDefaults

        rd, _ = RuntimeDefaults.objects.get_or_create(pk=1)
        rd.ai_mode = None if clearing else mode_raw
        rd.save(update_fields=["ai_mode", "updated_at"])
    elif scope == "tenant":
        if school is None:
            return JsonResponse({"ok": False, "error": "no_school"}, status=400)
        if not _can_manage_tenant(request):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
        if clearing:
            _clear_tenant_override(school)
        else:
            from apps.platform_runtime.runtime_defaults_first_class import (
                set_runtime_default,
            )

            set_runtime_default(school=school, field="ai_mode", value=mode_raw)
    else:
        return JsonResponse({"ok": False, "error": "invalid_scope"}, status=400)

    return JsonResponse({"ok": True, "scope": scope, **ai_mode_state(request)})
