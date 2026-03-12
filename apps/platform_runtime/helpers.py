"""
Phase 5: Runtime helper shims — use these instead of SiteSettings.get_solo() or School.settings/features
for tenant behavior. All resolve from request.tenant_runtime with platform fallback where appropriate.

Audit: Tenant-facing code must not call SiteSettings.get_solo() for tenant behavior; use
get_effective_* helpers or request.tenant_runtime. See docs/PLATFORM_TRANSITION_AUDIT_REPORT.md
and docs/PLATFORM_AUDIT_REMEDIATION_BACKLOG.md.
"""
from __future__ import annotations

from copy import copy
import logging
from typing import Any, Optional

from django.core.cache import cache
from django.db import DatabaseError


logger = logging.getLogger(__name__)


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


def get_tenant_runtime(request: Any) -> Optional[Any]:
    """Return request.tenant_runtime or None (e.g. on public/control plane)."""
    return getattr(request, "tenant_runtime", None)


def get_effective_branding(request: Any) -> Any:
    """Resolve tenant branding from runtime; fallback to minimal dict for non-tenant."""
    rt = get_tenant_runtime(request)
    if rt and rt.branding:
        return rt.branding
    return _platform_branding_fallback()


def get_effective_dashboard(request: Any, role: Optional[str] = None, user: Any = None, **kwargs: Any) -> dict:
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
    Resolve backend feature flags from runtime when available; otherwise from SiteSettings.
    Use this instead of SiteSettings.get_solo().backend_feature_flags in tenant-facing views.
    """
    school = getattr(request, "school", None) if request is not None else None
    rt = get_tenant_runtime(request)
    try:
        from apps.siteconfig.models import default_backend_feature_flags
        defaults = default_backend_feature_flags() or {}
    except (AttributeError, ImportError, TypeError, ValueError):
        defaults = {}
    if rt and getattr(rt, "flags", None) and getattr(rt.flags, "flags", None):
        return {**defaults, **rt.flags.flags}
    try:
        platform_site = get_effective_site_settings(request=None, school=None)
        if platform_site is None:
            raise LookupError("effective platform site settings unavailable")
        if callable(getattr(platform_site, "get_backend_feature_flags", None)):
            site_overrides = platform_site.get_backend_feature_flags()
        else:
            site_overrides = getattr(platform_site, "backend_feature_flags", None) or {}
        school_overrides = {}
        school_settings = getattr(school, "settings", None) or {}
        if isinstance(school_settings, dict):
            maybe_flags = school_settings.get("backend_feature_flags") or school_settings.get("feature_flags") or {}
            if isinstance(maybe_flags, dict):
                school_overrides = maybe_flags
        return {**defaults, **site_overrides, **school_overrides}
    except (AttributeError, LookupError, TypeError, ValueError):
        return defaults


def get_effective_flags_for_school(school: Any = None) -> dict:
    """School-aware flag resolution for services that do not have a request object."""

    class _RequestShim:
        def __init__(self, school_obj: Any):
            self.school = school_obj
            self.tenant_runtime = None

    return get_effective_flags(_RequestShim(school))


def get_effective_site_settings(request: Any = None, school: Any = None) -> Any:
    """
    Return a tenant-aware SiteSettings instance for read paths.

    A shallow copy of the platform singleton is used so existing attribute reads
    and helper methods still work while school-level JSON overrides are layered on
    top without mutating the stored singleton.

    Performance: request-scope cache avoids repeated get_solo() in the same request
    (e.g. context processor + view). Short TTL cache (60s) per school reduces DB load
    across requests.
    """
    if school is None and request is not None:
        school = getattr(request, "school", None)

    # Request-scope cache: same request gets same result without another get_solo()
    cache_attr = "_effective_site_settings_cached"
    if request is not None:
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
    except (AttributeError, DatabaseError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        logger.exception("Failed to build platform site settings base from runtime defaults / SiteSettings")
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

    setattr(resolved, "_resolved_for_school_id", school_id)
    cache.set(cache_key, resolved, 60)
    if request is not None:
        setattr(request, cache_attr, resolved)
    return resolved


def _build_platform_site_settings_base() -> Any:
    """Build the platform baseline from RuntimeDefaults first, then legacy SiteSettings for compatibility fields."""
    from apps.platform_runtime.models import RuntimeDefaults
    from apps.siteconfig.models import SiteSettings, build_platform_default_site_settings

    payload = {}
    try:
        rt_defaults = RuntimeDefaults.get_singleton()
        if rt_defaults is not None and isinstance(getattr(rt_defaults, "payload", None), dict):
            payload = dict(rt_defaults.payload)
    except (AttributeError, DatabaseError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        payload = {}

    legacy_site = None
    try:
        legacy_site = SiteSettings.get_solo()
    except (AttributeError, DatabaseError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        legacy_site = None

    if legacy_site is not None:
        base = copy(legacy_site)
    else:
        base = build_platform_default_site_settings()

    if payload:
        for field in SiteSettings._meta.concrete_fields:
            field_names = {field.name, getattr(field, "attname", field.name)}
            payload_key = next((name for name in field_names if name in payload), None)
            if payload_key is None:
                continue
            target_attr = payload_key
            if getattr(field, "remote_field", None) is not None and payload_key == field.name:
                target_attr = getattr(field, "attname", field.name)
            if not hasattr(base, target_attr):
                continue
            setattr(base, target_attr, payload[payload_key])
        try:
            base._sanitize_foreign_keys(persist=False)
        except (AttributeError, DatabaseError, TypeError, ValueError):
            pass
    return base


def get_site_display_name(request: Any) -> str:
    """
    Resolve site/school display name for tenant-facing UI.
    Prefer runtime branding / tenant context; fallback to SiteSettings for backward compatibility.
    Use this instead of SiteSettings.get_solo().site_name in views and context processors.
    """
    rt = get_tenant_runtime(request)
    if rt and rt.tenant_ctx and getattr(rt.tenant_ctx, "school_id", None):
        try:
            from apps.schools.models import School
            school = School.objects.filter(pk=rt.tenant_ctx.school_id).values_list("name", flat=True).first()
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
    except (AttributeError, DatabaseError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
