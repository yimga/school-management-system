"""Dual-plane theme builder storage — operator (manager) vs tenant (per school)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from django.core.exceptions import PermissionDenied

from apps.schools.control_plane import is_control_plane_request
from apps.siteconfig.theme_builder import (
    LEGACY_RUNTIME_PAYLOAD_KEY,
    OPERATOR_RUNTIME_PAYLOAD_KEY,
    TENANT_SCHOOL_SETTINGS_KEY,
    default_layout,
    normalize_layout,
)

PLANE_OPERATOR = "operator"
PLANE_TENANT = "tenant"

_OPERATOR_COLOR_MAP = {
    "primary_color": "public_brand_primary_color",
    "accent_color": "public_brand_accent_color",
}

OPERATOR_PUBLISH_LOG_KEY = "operator_theme_publish_log"
TENANT_PUBLISH_LOG_KEY = "tenant_theme_publish_log"
_MAX_PUBLISH_LOG_ENTRIES = 20


def resolve_theme_builder_plane(request: Any) -> str:
    """Return ``operator`` on manager host, else ``tenant``."""
    if is_control_plane_request(request):
        return PLANE_OPERATOR
    return PLANE_TENANT


def _require_tenant_school(request: Any) -> Any:
    school = getattr(request, "school", None)
    if school is None:
        raise PermissionDenied("School context required for tenant theme builder.")
    return school


def load_builder_layout(request: Any) -> dict[str, Any]:
    """Load layout for the active plane (operator global vs tenant school.settings)."""
    if resolve_theme_builder_plane(request) == PLANE_OPERATOR:
        return _load_operator_layout()
    school = _require_tenant_school(request)
    return _load_tenant_layout(school)


def persist_builder_layout(request: Any, layout: dict[str, Any]) -> None:
    """Persist layout only on the active plane."""
    normalized = normalize_layout(layout)
    if resolve_theme_builder_plane(request) == PLANE_OPERATOR:
        _persist_operator_layout(normalized)
        return
    school = _require_tenant_school(request)
    _persist_tenant_layout(school, normalized)


def assert_theme_colors_request_plane(request: Any) -> None:
    """Theme palette editor must run on the correct host (tenant requires school)."""
    if resolve_theme_builder_plane(request) == PLANE_TENANT and not getattr(
        request, "school", None
    ):
        raise PermissionDenied("School context required for tenant theme colors.")


def build_publish_snapshot(
    layout: dict[str, Any],
    colors: dict[str, Any] | None,
    *,
    plane: str,
) -> dict[str, Any]:
    """Full restore payload stored on each publish for one-click rollback."""
    snapshot: dict[str, Any] = {
        "layout": normalize_layout(layout),
        "colors": dict(colors or {}),
    }
    if plane == PLANE_OPERATOR and colors:
        snapshot["public_brand"] = {
            dest: colors.get(src)
            for src, dest in _OPERATOR_COLOR_MAP.items()
            if colors.get(src)
        }
    return snapshot


def list_publish_log(request: Any) -> list[dict[str, Any]]:
    """Recent publish entries for the active plane (newest last)."""
    if resolve_theme_builder_plane(request) == PLANE_OPERATOR:
        try:
            from apps.platform_runtime.models import RuntimeDefaults

            rt = RuntimeDefaults.get_singleton()
            payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
            log = payload.get(OPERATOR_PUBLISH_LOG_KEY) or []
            return list(log) if isinstance(log, list) else []
        except (ImportError, AttributeError, TypeError, ValueError):
            return []
    school = getattr(request, "school", None)
    if school is None:
        return []
    settings = dict(getattr(school, "settings", None) or {})
    log = settings.get(TENANT_PUBLISH_LOG_KEY) or []
    return list(log) if isinstance(log, list) else []


def rollback_previous_publish(request: Any) -> dict[str, Any]:
    """
    Restore layout + brand colors from the previous publish snapshot on this plane.
    Appends a rollback audit entry; does not remove history.
    """
    log = list_publish_log(request)
    restorable = [
        entry
        for entry in log
        if isinstance(entry.get("summary"), dict) and entry["summary"].get("layout")
    ]
    if len(restorable) < 2:
        return {"ok": False, "error": "No previous publish snapshot to restore."}
    target = restorable[-2]
    snapshot = target.get("summary") or {}
    layout = normalize_layout(snapshot.get("layout"))
    colors = snapshot.get("colors") if isinstance(snapshot.get("colors"), dict) else {}
    plane = resolve_theme_builder_plane(request)

    persist_builder_layout(request, layout)
    if plane == PLANE_OPERATOR:
        public_brand = snapshot.get("public_brand")
        if isinstance(public_brand, dict) and public_brand:
            from apps.siteconfig.config_service import persist_platform_runtime_payload_updates

            persist_platform_runtime_payload_updates(public_brand)
        elif colors:
            persist_operator_brand_colors(colors, request=request)
    elif colors:
        persist_tenant_brand_colors(request, colors, publish=True, effective_surface=layout.get("surface", "light"))

    record_publish_event(
        request,
        event_type="rollback_restore",
        summary={
            "restored_from": target.get("at"),
            "restored_type": target.get("type"),
            "layout": layout,
            "colors": colors,
        },
    )
    return {
        "ok": True,
        "layout": layout,
        "colors": colors,
        "restored_from": target.get("at"),
        "plane": plane,
    }


def record_publish_event(
    request: Any,
    *,
    event_type: str,
    summary: dict[str, Any] | None = None,
) -> None:
    """Append-only publish log per plane (operator payload vs school.settings)."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "user_id": getattr(getattr(request, "user", None), "pk", None),
        "summary": summary or {},
    }
    if resolve_theme_builder_plane(request) == PLANE_OPERATOR:
        _append_operator_publish_log(entry)
        return
    school = _require_tenant_school(request)
    _append_tenant_publish_log(school, entry)


def _glance_publish_meta(log: list) -> tuple[str, str]:
    """Last publish ISO timestamp + human event label from append-only log."""
    if not isinstance(log, list) or not log:
        return "", ""
    last = log[-1] if isinstance(log[-1], dict) else {}
    at = str(last.get("at") or "")
    event_type = str(last.get("type") or "publish")
    label = event_type.replace("_", " ").strip()
    return at, label


def _glance_contrast_meta(primary: str, accent: str) -> dict[str, Any]:
    from apps.siteconfig.contrast_guard import contrast_ratio

    pair_min = 1.6
    p = str(primary or "").strip()
    a = str(accent or "").strip()
    if not p or not a:
        return {
            "contrast_ratio": 0.0,
            "contrast_ok": True,
            "contrast_min_ratio": pair_min,
        }
    ratio = contrast_ratio(p, a)
    return {
        "contrast_ratio": round(ratio, 1),
        "contrast_ok": ratio >= pair_min,
        "contrast_min_ratio": pair_min,
    }


def build_hub_glance_context(request: Any) -> dict[str, Any]:
    """Glance strip for dual-plane theme hub (colors, layout surface, publish count)."""
    plane = resolve_theme_builder_plane(request)
    if plane == PLANE_OPERATOR:
        layout = _load_operator_layout()
        try:
            from apps.platform_runtime.models import RuntimeDefaults

            rt = RuntimeDefaults.get_singleton()
            primary = getattr(rt, "public_brand_primary_color", None) or ""
            accent = getattr(rt, "public_brand_accent_color", None) or ""
            payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
            log = payload.get(OPERATOR_PUBLISH_LOG_KEY) or []
        except (ImportError, AttributeError, TypeError, ValueError):
            primary, accent, log = "", "", []
        last_at, last_label = _glance_publish_meta(log if isinstance(log, list) else [])
        return {
            "plane_label": "operator",
            "primary_color": primary,
            "accent_color": accent,
            "layout_surface": layout.get("surface", "light"),
            "publish_count": len(log) if isinstance(log, list) else 0,
            "school_name": "",
            "last_publish_at": last_at,
            "last_publish_label": last_label,
            **_glance_contrast_meta(primary, accent),
        }
    school = getattr(request, "school", None)
    layout = _load_tenant_layout(school) if school else default_layout()
    settings = dict(getattr(school, "settings", None) or {}) if school else {}
    log = settings.get(TENANT_PUBLISH_LOG_KEY) or []
    from apps.platform_runtime.config_resolver import get_effective_config

    primary = (
        get_effective_config(key="primary_color", request=request) if school else ""
    )
    accent = (
        get_effective_config(key="accent_color", request=request) if school else ""
    )
    last_at, last_label = _glance_publish_meta(log if isinstance(log, list) else [])
    return {
        "plane_label": "tenant",
        "primary_color": primary or "",
        "accent_color": accent or "",
        "layout_surface": layout.get("surface", "light"),
        "publish_count": len(log) if isinstance(log, list) else 0,
        "school_name": getattr(school, "name", "") or "",
        "last_publish_at": last_at,
        "last_publish_label": last_label,
        **_glance_contrast_meta(primary, accent),
    }


def persist_operator_brand_colors(colors: dict[str, Any], *, request: Any | None = None) -> None:
    """Write manager chrome colors to RuntimeDefaults first-class public brand fields."""
    from apps.siteconfig.config_service import persist_platform_runtime_payload_updates

    updates: dict[str, object] = {}
    for src, dest in _OPERATOR_COLOR_MAP.items():
        value = colors.get(src)
        if value and str(value).strip():
            updates[dest] = str(value).strip()
    if updates:
        persist_platform_runtime_payload_updates(updates)
    if request is not None:
        record_publish_event(
            request,
            event_type="operator_brand_colors",
            summary={k: updates.get(v) for k, v in _OPERATOR_COLOR_MAP.items() if v in updates},
        )


def persist_tenant_brand_colors(
    request: Any,
    colors: dict[str, Any],
    *,
    publish: bool,
    effective_surface: str = "light",
) -> dict[str, Any]:
    """
    Tenant plane: school-scoped theme experience state + optional ThemeColorsForm publish.
    Returns API payload fragment (errors key on validation failure).
    """
    from apps.siteconfig.brand_guard_runtime import guard_brand_dict
    from apps.siteconfig.config_service import get_effective_site_settings
    from apps.siteconfig.forms import ThemeColorsForm
    from apps.siteconfig.theme_builder import TOKEN_FIELD_NAMES
    from apps.siteconfig.views import build_platform_default_site_settings

    guarded, adjusted = guard_brand_dict(colors, effective_surface=effective_surface)
    if colors:
        # config-resolver-allow: object mutated via apply_theme_experience_state(save=True)
        site = get_effective_site_settings(request=request)
        if site is not None and hasattr(site, "apply_theme_experience_state"):
            updates = {k: guarded.get(k) for k in TOKEN_FIELD_NAMES if guarded.get(k)}
            if updates:
                site.apply_theme_experience_state(field_updates=updates, save=True)

    if publish and colors:
        # config-resolver-allow: namespace used as ThemeColorsForm publish instance (mutated via form.save)
        site = get_effective_site_settings(request=request)
        if site is None:
            site = build_platform_default_site_settings()
        post_data = {k: guarded.get(k) for k in TOKEN_FIELD_NAMES if guarded.get(k)}
        form = ThemeColorsForm(post_data, instance=site, request=request)
        if not form.is_valid():
            return {"ok": False, "errors": form.errors}
        form.save()
        record_publish_event(
            request,
            event_type="tenant_theme_colors",
            summary={k: guarded.get(k) for k in TOKEN_FIELD_NAMES if guarded.get(k)},
        )

    return {
        "ok": True,
        "brand_adjusted": adjusted,
        "colors": {k: guarded.get(k) for k in TOKEN_FIELD_NAMES},
    }


def forbid_cross_plane_access(request: Any, *, expected_plane: str) -> None:
    """Raise PermissionDenied when host plane does not match expected."""
    actual = resolve_theme_builder_plane(request)
    if actual != expected_plane:
        raise PermissionDenied(
            f"Theme builder action not allowed on {actual} plane (expected {expected_plane})."
        )


def _load_operator_layout() -> dict[str, Any]:
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        payload = rt.payload if rt and isinstance(rt.payload, dict) else {}
        stored = payload.get(OPERATOR_RUNTIME_PAYLOAD_KEY)
        if stored is None:
            stored = payload.get(LEGACY_RUNTIME_PAYLOAD_KEY)
        return normalize_layout(stored)
    except (ImportError, AttributeError, TypeError, ValueError):
        return default_layout()


def _persist_operator_layout(layout: dict[str, Any]) -> None:
    from apps.siteconfig.config_service import persist_platform_runtime_payload_updates

    persist_platform_runtime_payload_updates({OPERATOR_RUNTIME_PAYLOAD_KEY: layout})


def _load_tenant_layout(school: Any) -> dict[str, Any]:
    settings = dict(getattr(school, "settings", None) or {})
    return normalize_layout(settings.get(TENANT_SCHOOL_SETTINGS_KEY))


def _persist_tenant_layout(school: Any, layout: dict[str, Any]) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    settings[TENANT_SCHOOL_SETTINGS_KEY] = layout
    school.settings = settings
    school.save(update_fields=["settings", "updated_at"])


def _append_operator_publish_log(entry: dict[str, Any]) -> None:
    from apps.siteconfig.config_service import persist_platform_runtime_payload_updates

    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rt = RuntimeDefaults.get_singleton()
        payload = dict(rt.payload or {}) if rt else {}
    except (ImportError, AttributeError, TypeError, ValueError):
        payload = {}
    log = list(payload.get(OPERATOR_PUBLISH_LOG_KEY) or [])
    log.append(entry)
    payload[OPERATOR_PUBLISH_LOG_KEY] = log[-_MAX_PUBLISH_LOG_ENTRIES:]
    persist_platform_runtime_payload_updates({OPERATOR_PUBLISH_LOG_KEY: payload[OPERATOR_PUBLISH_LOG_KEY]})


def _append_tenant_publish_log(school: Any, entry: dict[str, Any]) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    log = list(settings.get(TENANT_PUBLISH_LOG_KEY) or [])
    log.append(entry)
    settings[TENANT_PUBLISH_LOG_KEY] = log[-_MAX_PUBLISH_LOG_ENTRIES:]
    school.settings = settings
    school.save(update_fields=["settings", "updated_at"])
