"""
Phase 5: Runtime helper shims — use these instead of SiteSettings.get_solo() or School.settings/features
for tenant behavior. All resolve from request.tenant_runtime with platform fallback where appropriate.
"""
from __future__ import annotations

from typing import Any, Optional


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
    rt = get_tenant_runtime(request)
    try:
        from apps.siteconfig.models import default_backend_feature_flags
        defaults = default_backend_feature_flags() or {}
    except Exception:
        defaults = {}
    if rt and getattr(rt, "flags", None) and getattr(rt.flags, "flags", None):
        return {**defaults, **rt.flags.flags}
    try:
        from apps.siteconfig.models import SiteSettings
        site = SiteSettings.get_solo()
        overrides = getattr(site, "backend_feature_flags", None) or {}
        return {**defaults, **overrides}
    except Exception:
        return defaults


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
        except Exception:
            pass
    if rt and rt.branding and getattr(rt.branding, "tagline", None):
        return str(rt.branding.tagline)
    try:
        from apps.siteconfig.models import SiteSettings
        site = SiteSettings.get_solo()
        return getattr(site, "site_name", None) or "School System"
    except Exception:
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
