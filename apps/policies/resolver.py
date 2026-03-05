"""
Resolve effective policy: platform_defaults ⊕ country_defaults ⊕ tenant_overrides.
Modules must not read School.settings / School.features directly; use get_effective_policy instead.
"""
from typing import Any, Dict, Optional


def get_effective_policy(
    school,
    user=None,
    capability: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single entry point for "how should this tenant behave?"
    Returns merged policy: platform defaults + region/school defaults + tenant overrides.
    """
    out: Dict[str, Any] = {}
    # Platform defaults (minimal)
    out.setdefault("terminology", {})
    out.setdefault("grading", {})
    out.setdefault("workflows", {})
    out.setdefault("features", {})

    if school is None:
        return out

    # Region/school defaults from School.default_region if present
    region = getattr(school, "default_region", None)
    if region:
        if hasattr(region, "currency_code"):
            out.setdefault("currency", {}).update({"code": getattr(region, "currency_code", None)})
        if hasattr(region, "timezone"):
            out.setdefault("timezone", getattr(region, "timezone", None))

    # Tenant overrides from School.settings (JSON)
    settings = getattr(school, "settings", None)
    if isinstance(settings, dict) and settings:
        if "terminology" in settings:
            out["terminology"] = {**out["terminology"], **settings["terminology"]}
        if "grading" in settings:
            out["grading"] = {**out["grading"], **settings["grading"]}
        if "workflows" in settings:
            out["workflows"] = {**out["workflows"], **settings["workflows"]}

    # Feature flags from School.features
    features = getattr(school, "features", None)
    if isinstance(features, dict):
        out["features"] = {**out["features"], **features}

    if capability is not None:
        # Return whether this capability is enabled for this tenant
        from apps.schools.models import is_feature_enabled
        return {"enabled": is_feature_enabled(school, capability), "policy": out}
    return out


def get_tenant_blueprint(school) -> Dict[str, Any]:
    """Return normalized blueprint for the active tenant (school). Used by registry.get_tenant_blueprint(request)."""
    return get_effective_policy(school)
