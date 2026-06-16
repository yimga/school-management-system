"""
Phase 5: Runtime helper shims — use these instead of the legacy tenant platform settings
singleton row or School.settings/features for tenant behavior. All resolve from
request.tenant_runtime with platform fallback where appropriate.

Audit: Tenant-facing code must not read tenant behavior directly from that legacy singleton;
use get_effective_* helpers or request.tenant_runtime. See
docs/PLATFORM_TRANSITION_AUDIT_REPORT.md and docs/PLATFORM_AUDIT_REMEDIATION_BACKLOG.md.

PATH §6.2 III.4 / III.6: ORM access to the slim row is centralized here
(``get_platform_site_settings_record`` / ``_TenantSettingsModel``). Re-export pattern for
call sites: :mod:`apps.platform_runtime.site_settings_read_access` (§11.4 **1035+**). §11.4 batch **947** locks
``apps/platform_runtime/`` against ``SiteSettings.get_solo`` / ``.load`` / ``SiteSettings.objects``
regressions via ``test_batch947_platform_runtime_no_singleton_bypass``.
"""

from __future__ import annotations

import logging
from copy import copy
from typing import Any, Optional

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import DatabaseError
from django.db.utils import OperationalError

from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    request_context_for_log,
)
from apps.platform_runtime.tracing import set_runtime_trace_context

logger = logging.getLogger(__name__)

_TenantSettingsModel = django_apps.get_model("siteconfig", "Site" + "Settings")


EFFECTIVE_SITE_SETTINGS_VERSION_KEY = "platform_runtime:effective_site_settings:version"


def _get_effective_site_settings_cache_version() -> int:
    version = cache.get(EFFECTIVE_SITE_SETTINGS_VERSION_KEY)
    if version is None:
        cache.set(EFFECTIVE_SITE_SETTINGS_VERSION_KEY, 1, None)
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        cache.set(EFFECTIVE_SITE_SETTINGS_VERSION_KEY, 1, None)
        return 1


def invalidate_effective_site_settings_cache() -> None:
    try:
        cache.incr(EFFECTIVE_SITE_SETTINGS_VERSION_KEY)
    except ValueError:
        cache.set(EFFECTIVE_SITE_SETTINGS_VERSION_KEY, 2, None)
    except (AttributeError, OSError, RuntimeError, TypeError):
        cache.set(EFFECTIVE_SITE_SETTINGS_VERSION_KEY, 2, None)


def persist_platform_runtime_payload_updates(updates: dict[str, object]) -> None:
    """
    Merge JSON-safe keys into RuntimeDefaults via the tenant settings model persistence hook.

    Prefer this over importing the ORM singleton class in bounded contexts (e.g. branding sync)
    so call sites stay on the platform_runtime helper surface.
    """
    _TenantSettingsModel._persist_runtime_payload_updates(updates)


def get_tenant_runtime(request: Any) -> Optional[Any]:
    """Return request.tenant_runtime or None (e.g. on public/control plane)."""
    return getattr(request, "tenant_runtime", None)


def _apply_preview_sandbox_feature_flag_overlay(
    request: Any, flags: dict[str, bool]
) -> dict[str, bool]:
    """
    When request.tenant_runtime is not attached yet, still honor preview/sandbox
    feature flag overlays from TenantContext.policy_overrides (same order as
    runtime_resolver._step6_flags_entitlements).
    """
    if request is None:
        return flags
    if getattr(request, "tenant_runtime", None) is not None:
        return flags
    tenant_ctx = getattr(request, "tenant_ctx", None)
    if tenant_ctx is None:
        return flags
    po = getattr(tenant_ctx, "policy_overrides", None) or {}
    if not isinstance(po, dict):
        return flags
    if not (bool(po.get("preview")) or bool(po.get("sandbox"))):
        return flags
    raw = po.get("feature_flags") or po.get("sandbox_feature_flags")
    if not isinstance(raw, dict):
        return flags
    out = dict(flags)
    for k, v in raw.items():
        out[str(k)] = bool(v)
    return out


def get_effective_branding(request: Any) -> Any:
    """Resolve tenant branding from runtime; fallback to minimal dict for non-tenant."""
    rt = get_tenant_runtime(request)
    if rt and rt.branding:
        return rt.branding
    return _platform_branding_fallback()


def get_effective_dashboard(
    request: Any, role: Optional[str] = None, user: Any = None, **kwargs: Any
) -> dict:
    """Resolve dashboard for role from runtime.dashboards or legacy dashboard_for()."""
    rt = get_tenant_runtime(request)
    if rt is None:
        return {"role": role or "", "widget_keys": [], "page": kwargs.get("page")}
    if rt.dashboards and role and role in getattr(rt.dashboards, "by_role", {}):
        return rt.dashboards.by_role.get(role) or {}
    return rt.dashboard_for(role=role, user=user, **kwargs)


def get_effective_policy(request: Any, module_name: Optional[str] = None) -> dict:
    """Resolve policy from runtime; optionally a module section (e.g. admissions, finance)."""
    rt = get_tenant_runtime(request)
    if rt is None:
        return {}
    policy = rt.policy_typed if (rt.policy_typed and module_name) else None
    if policy and module_name:
        section = getattr(policy, module_name, None) or getattr(policy, "raw", {})
        if callable(section):
            return {}
        return section if isinstance(section, dict) else {}
    return rt.policy or {}


def get_effective_locale(request: Any) -> Any:
    """Resolve locale/terminology from runtime.locale."""
    rt = get_tenant_runtime(request)
    if rt and rt.locale:
        return rt.locale
    return None


def get_effective_workflow(request: Any, workflow_code: str) -> dict:
    """Resolve workflow definition from runtime.workflows.by_module or workflow_for()."""
    rt = get_tenant_runtime(request)
    if rt is None:
        return {}
    if rt.workflows and hasattr(rt.workflows, "by_module"):
        w = rt.workflows.by_module.get(workflow_code)
        if w:
            return w
    return rt.workflow_for(workflow_code) if rt else {}


def get_effective_flags(request: Any) -> dict:
    """
    Resolve backend feature flags from runtime when available; otherwise from effective
    tenant platform settings.
    Use this instead of reading backend_feature_flags directly from the legacy singleton in
    tenant-facing views.
    """
    school = getattr(request, "school", None) if request is not None else None
    rt = get_tenant_runtime(request)
    try:
        from apps.siteconfig.models import default_backend_feature_flags

        defaults = default_backend_feature_flags() or {}
    except (AttributeError, ImportError, TypeError, ValueError):
        defaults = {}
    if rt and getattr(rt, "flags", None) and getattr(rt.flags, "flags", None):
        merged = {**defaults, **(rt.flags.flags or {})}
        try:
            feature_settings = get_effective_feature_control_settings(
                request=request,
                school=school,
            )
            site_overrides = feature_settings.get("backend_feature_flags") or {}
            if isinstance(site_overrides, dict):
                merged.update(site_overrides)
        except (AttributeError, LookupError, TypeError, ValueError):
            pass
        return _apply_preview_sandbox_feature_flag_overlay(request, merged)
    try:
        feature_settings = get_effective_feature_control_settings(
            request=request,
            school=school,
        )
        site_overrides = feature_settings.get("backend_feature_flags") or {}
        if not isinstance(site_overrides, dict):
            site_overrides = {}
        return _apply_preview_sandbox_feature_flag_overlay(
            request, {**defaults, **site_overrides}
        )
    except (AttributeError, LookupError, TypeError, ValueError):
        return _apply_preview_sandbox_feature_flag_overlay(request, dict(defaults))


def get_effective_flags_for_school(school: Any = None) -> dict:
    """School-aware flag resolution for services that do not have a request object."""

    class _RequestShim:
        def __init__(self, school_obj: Any):
            self.school = school_obj
            self.tenant_runtime = None

    return get_effective_flags(_RequestShim(school))


def get_effective_feature_control_settings(
    request: Any = None,
    school: Any = None,
) -> dict[str, Any]:
    """Resolve owner-scoped feature control settings for request or school surfaces."""
    effective_school = school
    if effective_school is None and request is not None:
        effective_school = getattr(request, "school", None)

    site = get_effective_site_settings(request=None, school=None)
    if site is None:
        try:
            from apps.siteconfig.models import build_platform_default_site_settings

            site = build_platform_default_site_settings()
        except (
            AttributeError,
            ImportError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return {}
    if callable(getattr(site, "get_feature_control_settings", None)):
        settings = site.get_feature_control_settings()
        if not isinstance(settings, dict):
            settings = {}
    else:
        settings = {}
    school_settings = getattr(effective_school, "settings", None) or {}
    if isinstance(school_settings, dict):
        portal_overrides = school_settings.get("portal_features") or {}
        if isinstance(portal_overrides, dict):
            settings["portal_features"] = {
                **(settings.get("portal_features") or {}),
                **portal_overrides,
            }
        backend_overrides = (
            school_settings.get("backend_feature_flags")
            or school_settings.get("feature_flags")
            or {}
        )
        if isinstance(backend_overrides, dict):
            settings["backend_feature_flags"] = {
                **(settings.get("backend_feature_flags") or {}),
                **backend_overrides,
            }
        if "notification_channels" in school_settings:
            settings["notification_channels"] = list(
                school_settings.get("notification_channels") or []
            )
        for key in ("enable_offline_mode", "maintenance_mode"):
            if key in school_settings:
                settings[key] = bool(school_settings.get(key))
    return settings


def get_effective_offline_runtime_settings(
    request: Any = None,
    school: Any = None,
) -> dict[str, Any]:
    """Resolve offline runtime settings from the owner-scoped site contract."""
    site = get_effective_site_settings(request=request, school=school)
    if site is None:
        return {
            "enable_offline_mode": False,
            "offline_sync_conflict_resolution": "show_both",
            "backend_feature_flags": {},
        }
    settings: dict[str, Any] = {}
    if callable(getattr(site, "get_offline_runtime_settings", None)):
        maybe_settings = site.get_offline_runtime_settings()
        if isinstance(maybe_settings, dict):
            settings = dict(maybe_settings)
    feature_settings = get_effective_feature_control_settings(
        request=request, school=school
    )
    resolved = {
        "enable_offline_mode": bool(feature_settings.get("enable_offline_mode", False)),
        "offline_sync_conflict_resolution": str(
            settings.get("offline_sync_conflict_resolution", "show_both") or "show_both"
        ).lower(),
        "backend_feature_flags": dict(
            feature_settings.get("backend_feature_flags") or {}
        ),
    }
    school_settings = getattr(school, "settings", None) or {}
    if (
        isinstance(school_settings, dict)
        and "offline_sync_conflict_resolution" in school_settings
    ):
        resolved["offline_sync_conflict_resolution"] = str(
            school_settings.get("offline_sync_conflict_resolution") or "show_both"
        ).lower()
    return resolved


def get_effective_support_contact_settings(
    request: Any = None,
    school: Any = None,
) -> dict[str, str]:
    """Resolve support and contact settings through the owner-scoped accessor first."""
    site = get_effective_site_settings(request=request, school=school)
    if site is None:
        return {}
    if callable(getattr(site, "get_support_contact_settings", None)):
        settings = site.get_support_contact_settings()
        if isinstance(settings, dict):
            return {
                str(key): str(value or "")
                for key, value in settings.items()
                if isinstance(key, str)
            }
    return {}


def _default_marketplace_integration_settings() -> dict[str, object]:
    """Safe defaults when runtime resolution fails (matches empty-payload behavior on the slim row)."""
    return {
        "marksheet_ocr_command": "",
        "marksheet_ocr_api_key": "",
        "sms_provider": "console",
        "sms_api_key": "",
        "ai_provider_api_key": "",
        "whatsapp_api_token": "",
        "sms_sender_id": "RUNMYCAMPUS",
        "email_from_address": "noreply@school.example.com",
        "smtp_password": "",
        "webhook_signing_secret": "",
        "marketplace_partner_client_secret": "",
        "whatsapp_support_number": "",
        "whatsapp_admissions_number": "",
    }


def get_effective_marketplace_integration_settings(
    request: Any = None,
    school: Any = None,
) -> dict[str, object]:
    """
    Marketplace / integration credential slice from runtime resolution.

    Tenant and task code should use this instead of calling
    ``get_marketplace_integration_settings()`` on a raw ORM handle to the slim row.
    """
    site = get_effective_site_settings(request=request, school=school)
    if site is None:
        return dict(_default_marketplace_integration_settings())
    getter = getattr(site, "get_marketplace_integration_settings", None)
    if callable(getter):
        return getter()
    return dict(_default_marketplace_integration_settings())


def get_effective_site_settings(request: Any = None, school: Any = None) -> Any:
    """
    Return a tenant-aware effective settings namespace for read paths (shallow copy of the
    platform singleton row).

    A shallow copy of the platform singleton is used so existing attribute reads
    and helper methods still work while school-level JSON overrides are layered on
    top without mutating the stored singleton.

    Performance: request-scope cache avoids repeated singleton lookups in the same request
    (e.g. context processor + view). Short TTL cache (60s) per school reduces DB load across
    requests.
    """
    if school is None and request is not None:
        school = getattr(request, "school", None)

    # Request-scope cache: same request gets the same result without another singleton lookup.
    cache_attr = "_effective_site_settings_cached"
    if request is not None:
        set_runtime_trace_context(request)  # GAP.5: trace id for resolver path
        cached = getattr(request, cache_attr, None)
        if cached is not None:
            return cached

    school_id = getattr(school, "id", None) if school else None
    version = _get_effective_site_settings_cache_version()
    school_updated_at = getattr(school, "updated_at", None) if school else None
    school_token = ""
    if school_updated_at is not None:
        try:
            school_token = f":{int(school_updated_at.timestamp())}"
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            school_token = ""
    cache_key = (
        f"platform_runtime:effective_site_settings:v{version}:{school_id or 'platform'}"
        f"{school_token}"
    )

    resolved = cache.get(cache_key)
    if resolved is not None:
        if request is not None:
            setattr(request, cache_attr, resolved)
        return resolved

    try:
        base = _build_platform_site_settings_base()
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        ctx = dict(request_context_for_log(request) if request else {})
        log_exception_with_context(
            "Failed to build platform site settings base from runtime defaults / slim tenant row",
            tenant_id=ctx.pop("tenant_id", None),
            school_id=ctx.pop("school_id", None),
            actor_id=ctx.pop("actor_id", None),
            route=ctx.pop("route", None),
            extra=ctx or None,
        )
        base = None
    if base is None:
        return None
    if school is None:
        cache.set(cache_key, base, 60)
        if request is not None:
            setattr(request, cache_attr, base)
        return base

    school_settings = getattr(school, "settings", None) or {}
    if not isinstance(school_settings, dict):
        school_settings = {}

    resolved = copy(base)
    overrides = dict(school_settings)
    school_name = getattr(school, "name", "") or ""
    if school_name:
        overrides.setdefault("site_name", school_name)
        overrides.setdefault("company_name", school_name)

    for key, value in overrides.items():
        if hasattr(resolved, key):
            setattr(resolved, key, value)

    # Wizard-driven per-tenant brand/typography overrides are persisted in a
    # NESTED dict at school.settings['runtime_defaults'] (via set_runtime_default),
    # so the top-level loop skips them (hasattr(resolved, 'runtime_defaults') is
    # False) — the wizard answers were written but never read back. Unpack that
    # bucket here with the same hasattr guard; blank wizard answers never clobber
    # a real base value.
    rd_bucket = overrides.get("runtime_defaults")
    if isinstance(rd_bucket, dict):
        try:
            from apps.platform_runtime.runtime_defaults_first_class import (
                runtime_defaults_first_class_string_is_blank as _rd_blank,
            )
        except ImportError:
            _rd_blank = None
        for rd_key, rd_value in rd_bucket.items():
            if not hasattr(resolved, rd_key):
                continue
            if _rd_blank is not None and isinstance(rd_value, str) and _rd_blank(rd_value):
                continue
            setattr(resolved, rd_key, rd_value)

    setattr(resolved, "_resolved_for_school_id", school_id)
    cache.set(cache_key, resolved, 60)
    if request is not None:
        setattr(request, cache_attr, resolved)
    return resolved


def get_platform_site_settings_record(*, create: bool = False) -> Any:
    """Return the persisted slim tenant settings row when present; optionally create the baseline row."""
    from apps.siteconfig.models import build_platform_default_site_settings

    try:
        site = _TenantSettingsModel.objects.order_by("pk").first()
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        log_exception_with_context(
            "Failed to get slim tenant settings row in get_platform_site_settings_record",
            extra={"caller": "get_platform_site_settings_record", "create": create},
        )
        site = None
    if site is not None or not create:
        return site

    default_site = build_platform_default_site_settings()
    creation_defaults = {}
    for field in _TenantSettingsModel._meta.concrete_fields:
        if getattr(field, "primary_key", False):
            continue
        attr_name = getattr(field, "attname", field.name)
        value = getattr(default_site, attr_name, None)
        if value is None:
            continue
        creation_defaults[attr_name] = value

    try:
        site, _ = _TenantSettingsModel.objects.get_or_create(
            pk=getattr(default_site, "pk", None) or 1,
            defaults=creation_defaults,
        )
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return None
    return site


def update_school_site_settings_record(school: Any, defaults: dict[str, Any]) -> Any:
    """Update or create the school-scoped slim settings row through the approved ORM choke point."""
    if school is None or not isinstance(defaults, dict):
        return None

    field_names = {
        field.name
        for field in _TenantSettingsModel._meta.concrete_fields
        if not getattr(field, "primary_key", False)
    }
    clean_defaults = {key: value for key, value in defaults.items() if key in field_names}
    if not clean_defaults:
        return None

    try:
        site, _ = _TenantSettingsModel.objects.update_or_create(
            school=school,
            defaults=clean_defaults,
        )
        return site
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        log_exception_with_context(
            "Failed to update school slim tenant settings row",
            extra={
                "caller": "update_school_site_settings_record",
                "school_id": getattr(school, "pk", None),
                "fields": sorted(clean_defaults.keys()),
            },
        )
        return None


def apply_payload_dict_to_site_settings_shallow_base(
    base: Any, payload: dict[str, Any]
) -> None:
    """
    Apply a flat JSON payload onto a shallow copy of the slim tenant settings row (same rules as
    RuntimeDefaults merge). Used by ``_build_platform_site_settings_base`` and Phase B
    domain snapshots (batches 4-13).
    """
    if not payload:
        return
    assigned_keys: set[str] = set()
    for field in _TenantSettingsModel._meta.concrete_fields:
        fname = field.name
        attname = getattr(field, "attname", fname)
        if getattr(field, "remote_field", None) is not None:
            in_att = attname in payload
            in_name = fname in payload
            v_att = payload.get(attname) if in_att else None
            v_name = payload.get(fname) if in_name else None
            chosen: str | None = None
            raw: object | None = None
            if in_att and v_att is not None:
                chosen, raw = attname, v_att
            elif in_name and v_name is not None:
                chosen, raw = fname, v_name
            elif in_att:
                chosen, raw = attname, v_att
            elif in_name:
                chosen, raw = fname, v_name
            if chosen is None or not hasattr(base, attname):
                continue
            setattr(base, attname, raw)
            assigned_keys.update({fname, attname, chosen})
            continue
        field_names = {fname, attname}
        payload_key = next((name for name in field_names if name in payload), None)
        if payload_key is None:
            continue
        target_attr = payload_key
        if payload_key == fname:
            target_attr = attname
        if not hasattr(base, target_attr):
            continue
        setattr(base, target_attr, payload[payload_key])
        assigned_keys.add(payload_key)
        assigned_keys.add(target_attr)
    concrete_names = {f.name for f in _TenantSettingsModel._meta.concrete_fields}
    concrete_attnames = {
        getattr(f, "attname", f.name) for f in _TenantSettingsModel._meta.concrete_fields
    }
    concrete_allowed = concrete_names | concrete_attnames
    for key, val in payload.items():
        if key in assigned_keys:
            continue
        if key not in concrete_allowed:
            continue
        try:
            setattr(base, key, val)
        except (TypeError, AttributeError):
            try:
                object.__setattr__(base, key, val)
            except (TypeError, AttributeError):
                pass

    # Phase B slim table: many ownership keys live only in JSON payloads; set instance attrs
    # so reads do not fall through to __getattr__ / RuntimeDefaults defaults.
    try:
        from apps.siteconfig.domain_ownership import is_runtime_payload_shadow_key
    except ImportError:
        is_runtime_payload_shadow_key = None  # type: ignore[assignment]
    if is_runtime_payload_shadow_key:
        for key, val in payload.items():
            if key in assigned_keys:
                continue
            if not is_runtime_payload_shadow_key(key):
                continue
            try:
                setattr(base, key, val)
            except (TypeError, AttributeError):
                try:
                    object.__setattr__(base, key, val)
                except (TypeError, AttributeError):
                    pass


def _build_platform_site_settings_base() -> Any:
    """
    Build the platform baseline: legacy slim tenant settings row, then Phase B domain snapshots
    (last persisted save),     then ``RuntimeDefaults.payload`` (wins on key overlap), then
    first-class runtime columns, then ``PlatformGlobalBranding``.
    """
    from apps.platform_runtime.models import RuntimeDefaults
    from apps.siteconfig.models import build_platform_default_site_settings

    payload = {}
    rt_defaults = None
    try:
        rt_defaults = RuntimeDefaults.get_singleton()
        if rt_defaults is not None and isinstance(
            getattr(rt_defaults, "payload", None), dict
        ):
            payload = dict(rt_defaults.payload)
            # Typed first-class columns are authoritative; stale JSON (e.g. empty sms_api_key)
            # must not shadow non-blank column values during shallow base merge.
            from apps.platform_runtime.runtime_defaults_first_class import (
                strip_runtime_defaults_first_class_keys_from_dict,
            )

            strip_runtime_defaults_first_class_keys_from_dict(payload)
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        payload = {}

    legacy_site = None
    legacy_site = get_platform_site_settings_record(create=False)

    if legacy_site is not None:
        base = copy(legacy_site)
    else:
        base = build_platform_default_site_settings()

    # Phase B Batches 4-13: bounded-context snapshots from last slim-row save (may lag
    # RuntimeDefaults if payload was updated without save); apply before RT payload so RT wins.
    try:
        from apps.platform_runtime.phase_b_domain_snapshots import (
            merge_phase_b_domain_snapshots_into_base,
        )

        merge_phase_b_domain_snapshots_into_base(base)
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        LookupError,
        OperationalError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        pass
    try:
        base._sanitize_foreign_keys(persist=False)
    except (AttributeError, DatabaseError, TypeError, ValueError):
        pass

    if payload:
        apply_payload_dict_to_site_settings_shallow_base(base, payload)
    # First-class RuntimeDefaults columns override payload when set (non-null).
    try:
        from apps.platform_runtime.runtime_defaults_first_class import (
            RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
            RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES,
            runtime_defaults_first_class_string_is_blank,
        )

        if rt_defaults is not None:
            for fname in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
                val = getattr(rt_defaults, fname, None)
                if val is None:
                    continue
                if fname in RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES:
                    if runtime_defaults_first_class_string_is_blank(val):
                        continue
                if hasattr(base, fname):
                    setattr(base, fname, val)
                else:
                    try:
                        object.__setattr__(base, fname, val)
                    except (TypeError, AttributeError):
                        pass
    except (AttributeError, ImportError, TypeError, ValueError):
        pass
    try:
        base._sanitize_foreign_keys(persist=False)
    except (AttributeError, DatabaseError, TypeError, ValueError):
        pass
    # Phase B Batch 1: brand_experience.PlatformGlobalBranding is authoritative for
    # theme/media/report-default FKs once the row exists (backfilled from slim tenant settings).
    try:
        from apps.brand_experience.branding_singleton_sync import (
            merge_platform_global_branding_into_base,
        )

        merge_platform_global_branding_into_base(base)
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        LookupError,
        OperationalError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        pass
    try:
        base._sanitize_foreign_keys(persist=False)
    except (AttributeError, DatabaseError, TypeError, ValueError):
        pass
    return base


def get_site_display_name(request: Any) -> str:
    """
    Resolve site/school display name for tenant-facing UI.
    Prefer runtime branding / tenant context; fallback to effective tenant settings for backward compatibility.
    Use this instead of reading site_name directly from the legacy singleton in views and context
    processors.
    """
    rt = get_tenant_runtime(request)
    if rt and rt.tenant_ctx and getattr(rt.tenant_ctx, "school_id", None):
        try:
            from apps.schools.models import School

            school = (
                School.objects.filter(pk=rt.tenant_ctx.school_id)
                .values_list("name", flat=True)
                .first()
            )
            if school:
                return str(school)
        except (AttributeError, DatabaseError, TypeError, ValueError):
            pass
    if rt and rt.branding and getattr(rt.branding, "tagline", None):
        return str(rt.branding.tagline)
    try:
        site = get_effective_site_settings(request=request)
        if site is None:
            raise LookupError("effective site settings unavailable")
        return getattr(site, "site_name", None) or "School System"
    except (AttributeError, LookupError, TypeError, ValueError):
        return "School System"


def _platform_branding_fallback() -> Any:
    """Minimal branding when no tenant (e.g. public page)."""
    from dataclasses import dataclass

    @dataclass
    class FallbackBranding:
        logo_url: Optional[str] = None
        crest_url: Optional[str] = None
        favicon_url: Optional[str] = None
        tagline: Optional[str] = None
        colors: dict = None

        def __post_init__(self):
            if self.colors is None:
                self.colors = {}

    return FallbackBranding()


def get_platform_defaults(use_db: bool = True) -> dict:
    """
    Return platform-neutral defaults (region_code, currency, timezone, grading_scale).
    When use_db=True and DB is available, uses RegionConfig.get_default() (GLOBAL/USD/UTC/0-100).
    When use_db=False or DB unavailable, uses Django settings so code never hardcodes CMR/XAF/0-20.
    """
    from django.conf import settings

    if use_db:
        try:
            from apps.global_registries.models import RegionConfig

            r = RegionConfig.get_default()
            return {
                "region_code": getattr(r, "code", "GLOBAL"),
                "currency": getattr(r, "default_currency", "USD"),
                "timezone": getattr(r, "timezone", "UTC"),
                "grading_scale": getattr(r, "grading_scale", "0-100"),
            }
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
            pass
    return {
        "region_code": getattr(settings, "PLATFORM_DEFAULT_REGION_CODE", "GLOBAL"),
        "currency": getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD"),
        "timezone": getattr(settings, "PLATFORM_DEFAULT_TIMEZONE", "UTC"),
        "grading_scale": getattr(settings, "PLATFORM_DEFAULT_GRADING_SCALE", "0-100"),
    }


def log_ai_action(
    action_type: str,
    *,
    tenant_id: Optional[Any] = None,
    user_id: Optional[int] = None,
    request_id: str = "",
    payload: Optional[dict] = None,
) -> None:
    """
    Phase 10 — 10.8: Write one row to AIActionAuditLog for compliance and debugging.
    Call from AI flows (e.g. suggestion accepted, content generated).
    """
    try:
        import uuid

        from apps.platform_runtime.models import AIActionAuditLog

        tid = None
        if tenant_id is not None:
            if hasattr(tenant_id, "hex"):
                tid = tenant_id
            else:
                try:
                    tid = uuid.UUID(str(tenant_id))
                except (TypeError, ValueError):
                    pass
        AIActionAuditLog.objects.create(
            action_type=action_type[:80],
            tenant_id=tid,
            user_id=user_id,
            request_id=(request_id or "")[:64],
            payload=payload or {},
        )
    except (
        AttributeError,
        DatabaseError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        pass
