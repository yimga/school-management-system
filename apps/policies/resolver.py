"""
Resolve effective policy: platform_defaults ⊕ country_defaults ⊕ tenant_overrides.
Modules must not read School.settings / School.features directly; use get_effective_policy instead.
Optional per-tenant policy caching when POLICY_CACHE_TTL (seconds) is set in settings.
"""
from typing import Any, Dict, Optional


def _policy_cache_key(school) -> str:
    sid = getattr(school, "id", None)
    return f"policy:{sid}" if sid is not None else ""


def invalidate_policy_cache(school) -> None:
    """Call after updating school.settings or school.features so cache is refreshed."""
    from django.core.cache import cache
    key = _policy_cache_key(school)
    if key:
        cache.delete(key)


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

    # Per-tenant policy cache (R2): return cached policy when POLICY_CACHE_TTL is set and capability not requested
    if capability is None:
        try:
            from django.conf import settings as django_settings
            ttl = getattr(django_settings, "POLICY_CACHE_TTL", None)
            if ttl and ttl > 0:
                from django.core.cache import cache
                key = _policy_cache_key(school)
                if key:
                    cached = cache.get(key)
                    if isinstance(cached, dict) and cached:
                        return cached
        except Exception:
            pass

    # Optional v2: merge from TenantBlueprint.active_bundle when POLICY_USE_BUNDLES is set
    try:
        from django.conf import settings as django_settings
        if getattr(django_settings, "POLICY_USE_BUNDLES", False):
            from apps.policies.models import TenantBlueprint
            tb = TenantBlueprint.objects.filter(school=school).select_related("active_bundle").first()
            if tb and tb.active_bundle and tb.active_bundle.is_active:
                snapshot = getattr(tb.active_bundle, "policy_snapshot", None)
                if isinstance(snapshot, dict) and snapshot:
                    for key, value in snapshot.items():
                        if key in ("terminology", "grading", "workflows", "features") and isinstance(value, dict):
                            out[key] = {**out.get(key, {}), **value}
                        else:
                            out[key] = value
                    if capability is not None:
                        from apps.schools.models import is_feature_enabled
                        return {"enabled": is_feature_enabled(school, capability), "policy": out}
                    # Fill country_code / plan_slug for modules (no direct school.default_region/plan read)
                    region = getattr(school, "default_region", None)
                    if region and hasattr(region, "country_code"):
                        out.setdefault("country_code", (getattr(region, "country_code", None) or "")[:10])
                    plan = getattr(school, "plan", None)
                    if plan and hasattr(plan, "slug"):
                        out.setdefault("plan_slug", (getattr(plan, "slug", None) or "").strip().lower())
                    try:
                        ttl = getattr(django_settings, "POLICY_CACHE_TTL", None)
                        if ttl and ttl > 0:
                            from django.core.cache import cache
                            key = _policy_cache_key(school)
                            if key:
                                cache.set(key, out, timeout=int(ttl))
                    except Exception:
                        pass
                    return out
    except Exception:
        pass

    # Region/school defaults from School.default_region if present
    region = getattr(school, "default_region", None)
    if region:
        if hasattr(region, "currency_code"):
            out.setdefault("currency", {}).update({"code": getattr(region, "currency_code", None)})
        if hasattr(region, "timezone"):
            out.setdefault("timezone", getattr(region, "timezone", None))
        if hasattr(region, "default_language"):
            out.setdefault("default_language", getattr(region, "default_language", "en"))
        if hasattr(region, "grading_scale"):
            out["grading"] = {**out.get("grading", {}), "grading_scale": getattr(region, "grading_scale", "default")}

    # Region-level UI (e.g. RTL)
    if region and hasattr(region, "is_rtl"):
        out.setdefault("rtl", bool(getattr(region, "is_rtl", False)))
    # Region/country for modules that must not read school.default_region directly
    if region and hasattr(region, "country_code"):
        out.setdefault("country_code", (getattr(region, "country_code", None) or "")[:10])
    # Plan tier for KB/support (from school.plan FK)
    plan = getattr(school, "plan", None)
    if plan and hasattr(plan, "slug"):
        out.setdefault("plan_slug", (getattr(plan, "slug", None) or "").strip().lower())

    # Tenant overrides from School.settings (JSON)
    settings = getattr(school, "settings", None)
    if isinstance(settings, dict) and settings:
        if "terminology" in settings:
            out["terminology"] = {**out["terminology"], **settings["terminology"]}
        if "grading" in settings:
            out["grading"] = {**out["grading"], **settings["grading"]}
        if "workflows" in settings:
            out["workflows"] = {**out["workflows"], **settings["workflows"]}
        if "rtl" in settings:
            out["rtl"] = bool(settings["rtl"])
        if "default_language" in settings:
            out["default_language"] = settings["default_language"]
        if "grading_scale" in settings:
            out["grading"] = {**out.get("grading", {}), "grading_scale": settings["grading_scale"]}
        if "education_dna_preset" in settings:
            out["education_dna_preset"] = settings["education_dna_preset"]
        # Pass-through for modules that must not read school.settings directly
        for key in (
            "report_labels",
            "education_profile_code",
            "payment_gateways",
            "labels_map",
            "education_profile",
            "security_weights",
            "security_weights_override",
            "security_grace_period_days",
            "provisioning",
        ):
            if key in settings:
                out[key] = settings[key]

    # Feature flags from School.features
    features = getattr(school, "features", None)
    if isinstance(features, dict):
        out["features"] = {**out["features"], **features}

    if capability is not None:
        # Return whether this capability is enabled for this tenant
        from apps.schools.models import is_feature_enabled
        return {"enabled": is_feature_enabled(school, capability), "policy": out}
    if school is not None:
        try:
            from django.conf import settings as django_settings
            ttl = getattr(django_settings, "POLICY_CACHE_TTL", None)
            if ttl and ttl > 0:
                from django.core.cache import cache
                key = _policy_cache_key(school)
                if key:
                    cache.set(key, out, timeout=int(ttl))
        except Exception:
            pass
    return out


def get_tenant_blueprint(school) -> Dict[str, Any]:
    """Return normalized blueprint for the active tenant (school). Used by registry.get_tenant_blueprint(request)."""
    return get_effective_policy(school)
