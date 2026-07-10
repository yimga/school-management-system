"""
Resolve effective policy: platform_defaults ⊕ country_defaults ⊕ tenant_overrides.
Modules must not read School.settings / School.features directly; use get_effective_policy instead.
Optional per-tenant policy caching when POLICY_CACHE_TTL (seconds) is set in settings.
"""

import logging
from typing import Any, Dict, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

from apps.siteconfig.config_service import get_effective_site_settings
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.identifier_policy_service import default_school_code_for

logger = logging.getLogger(__name__)


def _safe_effective_site_attr(site: Any, name: str, default: Any = None) -> Any:
    """Phase B: effective site façade may omit virtual keys; use try/getattr, not defaulting getattr."""
    try:
        val = getattr(site, name)
    except AttributeError:
        return default
    return default if val is None else val


def _backfill_admissions_from_platform_site_settings(
    out: Dict[str, Any], school: Any
) -> None:
    """
    Merge admission number defaults from platform effective settings (resolver façade + RuntimeDefaults).
    Required for school=None callers (catalog preview) and when school.settings omits admissions.
    """
    if not out.get("admissions") or not isinstance(out.get("admissions"), dict):
        out["admissions"] = out.get("admissions") or {}
    if any(
        k in out["admissions"]
        for k in ("admission_number_mode", "admission_number_strategy", "school_code")
    ):
        return
    try:
        # config-resolver-allow: namespace passed whole to _safe_effective_site_attr() (Phase B virtual-key try/getattr)
        site = get_effective_site_settings(school=school)
        if site is None:
            try:
                from apps.platform_runtime.helpers import get_platform_site_settings_record

                # config-resolver-allow: raw-row fallback stored into the same site variable passed to _safe_effective_site_attr()
                site = get_platform_site_settings_record(create=False)
            except (
                AttributeError,
                ImportError,
                LookupError,
                TypeError,
                ValueError,
            ):
                site = None
        if site is None:
            raise LookupError("effective site settings unavailable")
        mode = _safe_effective_site_attr(site, "admission_number_mode", "AUTO_OR_MANUAL")
        strategy = _safe_effective_site_attr(site, "admission_number_strategy", "FULL")
        template = _safe_effective_site_attr(site, "admission_number_template", "") or ""
        pattern = _safe_effective_site_attr(site, "admission_number_pattern", "") or ""
        code = _safe_effective_site_attr(site, "school_code", None) or default_school_code_for(
            school
        )
        out["admissions"] = {
            **out["admissions"],
            "admission_number_mode": mode or "AUTO_OR_MANUAL",
            "admission_number_strategy": strategy or "FULL",
            "admission_number_template": template,
            "admission_number_pattern": pattern,
            "school_code": code or default_school_code_for(school),
        }
    except (AttributeError, LookupError, TypeError, ValueError) as e:
        logger.debug("Admissions backfill from platform effective settings failed: %s", e)
        out["admissions"].setdefault("admission_number_mode", "AUTO_OR_MANUAL")
        out["admissions"].setdefault("admission_number_strategy", "FULL")
        out["admissions"].setdefault("admission_number_template", "")
        out["admissions"].setdefault("admission_number_pattern", "")
        out["admissions"].setdefault("school_code", default_school_code_for(school))


# Typed exceptions for §2.4 broad-except replacement (allowlist 0).
_POLICY_CACHE_ERRORS = (AttributeError, TypeError, ValueError, ConnectionError, OSError)
_POLICY_MERGE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    LookupError,
    ObjectDoesNotExist,
    DatabaseError,
)
_POLICY_REGISTER_USAGE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)

# Policy section keys that may appear in tenant_compiled_config (from tenant_config.compile_effective_tenant_config).
_COMPILED_POLICY_SECTIONS = (
    "terminology",
    "grading",
    "grade_approval",
    "workflows",
    "features",
    "admissions",
    "finance",
    "attendance",
    "communication",
    "hr_staff",
    "compliance",
    "a11y",
    "ai_governance",
    "operational_identity",
    "forms",
    "portal",
    "payroll",
)
# Flat keys in compiled config that map into policy (resolver uses these).
_COMPILED_FLAT_TO_POLICY = {
    "default_language": "default_language",
    "grading_scale": ("grading", "grading_scale"),
    "currency": "currency",
    "date_format": "date_format",
    "rtl": "rtl",
}


def _merge_compiled_config_into_policy(
    out: Dict[str, Any], compiled: Dict[str, Any]
) -> None:
    """Merge tenant_compiled_config into policy out so runtime uses compiled config as source of truth."""
    for key, value in compiled.items():
        if key in _COMPILED_POLICY_SECTIONS and isinstance(value, dict):
            out[key] = {**out.get(key, {}), **value}
        elif key == "forms" and isinstance(value, dict):
            for form_name, form_schema in value.items():
                if isinstance(form_schema, dict) and "fields" in form_schema:
                    out["forms"][form_name] = form_schema
        elif key in _COMPILED_FLAT_TO_POLICY:
            target = _COMPILED_FLAT_TO_POLICY[key]
            if isinstance(target, tuple):
                section, subkey = target
                out.setdefault(section, {})
                if isinstance(out[section], dict):
                    out[section][subkey] = value
            else:
                out[key] = value


def _policy_cache_key(school) -> str:
    sid = getattr(school, "id", None)
    return f"policy:{sid}" if sid is not None else ""


def invalidate_policy_cache(school) -> None:
    """Call after updating school.settings or school.features so cache is refreshed."""
    from django.core.cache import cache

    key = _policy_cache_key(school)
    if key:
        cache.delete(key)


_POLICY_CACHE_BUST_ERRORS = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def invalidate_all_tenant_policy_caches() -> None:
    """
    Drop cached ``get_effective_policy`` entries for every school when platform defaults
    change (Phase B domain snapshots / platform defaults). No-op when POLICY_CACHE_TTL unset.
    """
    try:
        from django.conf import settings as django_settings

        ttl = getattr(django_settings, "POLICY_CACHE_TTL", None)
        if not ttl or ttl <= 0:
            return
        from django.core.cache import cache
        from apps.schools.models import School

        for pk in School.objects.values_list("pk", flat=True).iterator(chunk_size=500):
            cache.delete(f"policy:{pk}")
    except _POLICY_CACHE_BUST_ERRORS:
        logger.debug(
            "invalidate_all_tenant_policy_caches: skipped (cache or School query)"
        )


def _merge_education_registry_into_policy(out: Dict[str, Any], school) -> None:
    """Levels 4–6: expose tenant M2M education registries + matrix grading preset in policy."""
    if school is None:
        return
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog
        from apps.governance.academic_pack_bridge import resolve_academic_pack_context

        iso = GlobalGeoCatalog.alpha2_for_country(
            getattr(school, "country_code", None)
            or getattr(getattr(school, "default_region", None), "code", None)
        )
        ctx = resolve_academic_pack_context(iso)
        out.setdefault("education_structure", {})
        if isinstance(out["education_structure"], dict):
            out["education_structure"].update(
                {
                    "pack_source": ctx.get("pack_source"),
                    "education_pack_tier": ctx.get("education_pack_tier_live"),
                    "grading_preset_key": ctx.get("grading_preset_key"),
                    "supports_multi_shift": ctx.get("supports_multi_shift"),
                }
            )
        level_codes = list(
            school.education_levels.filter(is_active=True)
            .order_by("sort_order")
            .values_list("code", flat=True)
        )
        system_codes = list(
            school.education_system_types.filter(is_active=True)
            .order_by("sort_order")
            .values_list("code", flat=True)
        )
        out["education_levels"] = level_codes
        out["education_system_types"] = system_codes
        out.setdefault("grading", {})
        if isinstance(out["grading"], dict) and ctx.get("grading_preset_key"):
            out["grading"]["preset_key"] = ctx["grading_preset_key"]
            try:
                from apps.policies.grading_nuance_templates import attach_grading_nuance_to_policy

                attach_grading_nuance_to_policy(out, ctx["grading_preset_key"])
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
    except _POLICY_MERGE_ERRORS as e:
        logger.debug("Education registry policy merge skipped: %s", e)


def _merge_sector_defaults_into_policy(out: Dict[str, Any], school) -> None:
    """Wedge 14–22: Apply sector-driven policy defaults. Tenant overrides still win (merged later)."""
    sector = (getattr(school, "primary_sector", None) or "").strip().upper()
    if not sector:
        return
    if sector in ("PUBLIC", "GOVERNMENT_MINISTRY"):
        out.setdefault("compliance", {})
        if (
            isinstance(out["compliance"], dict)
            and "statutory_enabled" not in out["compliance"]
        ):
            out["compliance"]["statutory_enabled"] = True
        if "statutory_report_pack_recommended" not in out:
            out["statutory_report_pack_recommended"] = True
    elif sector == "NGO":
        out.setdefault("features", {})
        if (
            isinstance(out["features"], dict)
            and "advancement_default" not in out["features"]
        ):
            out["features"]["advancement_default"] = True
    elif sector == "INTERNATIONAL":
        out.setdefault("features", {})
        if (
            isinstance(out["features"], dict)
            and "multi_language_default" not in out["features"]
        ):
            out["features"]["multi_language_default"] = True


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
    out.setdefault(
        "grade_approval", {}
    )  # Phase 1: evals/gradebook — post/approval roles, deadline, auto_validate
    out.setdefault("workflows", {})
    out.setdefault("features", {})
    out.setdefault("admissions", {})
    # Section 10: Full policy-driven configurability per module
    # 10.3 Finance: invoice timing, fee templates, discounts, scholarship, late fee rules, collection flows, write-off, payment providers
    out.setdefault(
        "finance",
        {
            "invoice_timing": {},
            "fee_templates": [],
            "discounts": [],
            "scholarship": {},
            "late_fee_rules": [],
            "collection_flows": [],
            "write_off": {},
            "payment_providers": [],
        },
    )
    # 10.4 Attendance: statuses, lateness rules, absence escalation, homeroom/class model, who marks, parent notification timing
    out.setdefault(
        "attendance",
        {
            "statuses": [],
            "lateness_rules": {},
            "escalation": {},
            "absence_escalation": {},
            "homeroom_model": "",
            "who_marks": [],
            "parent_notification_timing": {},
        },
    )
    # 10.5 Communication: channels, fallback order, opt-in/out, digest vs instant, message approval, segmentation, school/quiet hours
    out.setdefault(
        "communication",
        {
            "channel_order": [],
            "fallback_order": [],
            "opt_in_out": {},
            "digest_vs_instant": {},
            "message_approval": {},
            "segmentation": {},
            "school_hours": {},
            "quiet_hours": {},
        },
    )
    # 10.6 HR/Staff: recruitment, onboarding, certification tracking, review cycles, leave approvals, substitute workflows
    out.setdefault(
        "hr_staff",
        {
            "recruitment": {},
            "onboarding": {},
            "certification_tracking": {},
            "review_cycles": {},
            "leave_approvals": {},
            "substitute_workflows": {},
        },
    )
    # 10.7 Compliance: retention, evidence packs, inspector portal, document requirements, safeguarding, regional controls
    out.setdefault(
        "compliance",
        {
            "retention": {},
            "evidence_packs": [],
            "inspector_portal": {},
            "document_requirements": [],
            "safeguarding": {},
            "regional_controls": {},
        },
    )
    # Section 25.7: a11y, low-bandwidth, offline-first
    out.setdefault("a11y", {"low_bandwidth": False, "offline_mode": False})
    # Section 29.9: AI governance — tenant-level enable, no-PII external prompt guardrails
    out.setdefault(
        "ai_governance",
        {
            "ai_enabled": False,
            "no_pii_external_prompt": True,
            "prompt_audit_trail": True,
        },
    )
    # 21.4: Operational identity (workflow/dashboard/comms/fee pack defaults)
    out.setdefault(
        "operational_identity",
        {
            "default_workflow_slug": "",
            "default_dashboard_slug": "",
            "comms_defaults": {},
            "fee_pack_defaults": {},
        },
    )
    # Section 23.4/24.8: Form schemas (policy-driven field visibility, required, pickers)
    from .form_policy import default_forms_platform

    out["forms"] = default_forms_platform()
    # Terminology defaults for modules (e.g. Admissions)
    if "admission_number_label" not in out["terminology"]:
        out["terminology"]["admission_number_label"] = "Admission number"

    if school is None:
        _backfill_admissions_from_platform_site_settings(out, school=None)
        return out

    # Prefer compiled tenant config when present (decouple from uncached platform row reads; single source from tenant_config).
    settings = getattr(school, "settings", None)
    if isinstance(settings, dict):
        compiled = settings.get("tenant_compiled_config")
        if isinstance(compiled, dict) and compiled:
            _merge_compiled_config_into_policy(out, compiled)

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
        except _POLICY_CACHE_ERRORS as e:
            logger.debug("Policy cache read failed: %s", e)

    # Optional v2: merge from TenantBlueprint.active_bundle when POLICY_USE_BUNDLES is set
    try:
        from django.conf import settings as django_settings

        if getattr(django_settings, "POLICY_USE_BUNDLES", False):
            from apps.policies.models import TenantBlueprint

            tb = (
                TenantBlueprint.objects.filter(school=school)
                .select_related("active_bundle")
                .first()
            )
            if tb and tb.active_bundle and tb.active_bundle.is_active:
                snapshot = getattr(tb.active_bundle, "policy_snapshot", None)
                if isinstance(snapshot, dict) and snapshot:
                    for key, value in snapshot.items():
                        if key in (
                            "terminology",
                            "grading",
                            "nuance_hooks",
                            "grade_approval",
                            "workflows",
                            "features",
                            "admissions",
                            "finance",
                            "attendance",
                            "communication",
                            "hr_staff",
                            "operational_identity",
                            "compliance",
                            "a11y",
                            "ai_governance",
                        ) and isinstance(value, dict):
                            out[key] = {**out.get(key, {}), **value}
                        elif key == "forms" and isinstance(value, dict):
                            # 23.4: merge form schemas (form_name -> { fields: [...] })
                            for form_name, form_schema in value.items():
                                if (
                                    isinstance(form_schema, dict)
                                    and "fields" in form_schema
                                ):
                                    out["forms"][form_name] = form_schema
                        else:
                            out[key] = value
                    if capability is not None:
                        from apps.schools.models import is_feature_enabled

                        return {
                            "enabled": is_feature_enabled(school, capability),
                            "policy": out,
                        }
                    # Fill country_code / plan_slug for modules (no direct school.default_region/plan read)
                    region = getattr(school, "default_region", None)
                    if region and hasattr(region, "country_code"):
                        out.setdefault(
                            "country_code",
                            (getattr(region, "country_code", None) or "")[:10],
                        )
                    plan = getattr(school, "plan", None)
                    if plan and hasattr(plan, "slug"):
                        out.setdefault(
                            "plan_slug",
                            (getattr(plan, "slug", None) or "").strip().lower(),
                        )
                    try:
                        ttl = getattr(django_settings, "POLICY_CACHE_TTL", None)
                        if ttl and ttl > 0:
                            from django.core.cache import cache

                            key = _policy_cache_key(school)
                            if key:
                                cache.set(key, out, timeout=int(ttl))
                    except _POLICY_CACHE_ERRORS as e:
                        logger.debug("Policy cache set failed: %s", e)
                    return out
    except _POLICY_MERGE_ERRORS as e:
        log_exception_with_context(
            "policies.resolver: Policy merge from TenantBlueprint failed",
            school_id=str(getattr(school, "id", None)) if school else None,
            extra={"error": str(e)},
        )
        logger.warning("Policy merge from TenantBlueprint failed: %s", e)

    # Region/school defaults from School.default_region if present
    region = getattr(school, "default_region", None)
    if region:
        if hasattr(region, "currency_code"):
            out.setdefault("currency", {}).update(
                {"code": getattr(region, "currency_code", None)}
            )
        if hasattr(region, "timezone"):
            out.setdefault("timezone", getattr(region, "timezone", None))
        if hasattr(region, "default_language"):
            out.setdefault(
                "default_language", getattr(region, "default_language", "en")
            )
        if hasattr(region, "grading_scale"):
            out["grading"] = {
                **out.get("grading", {}),
                "grading_scale": getattr(region, "grading_scale", "default"),
            }

    # Region-level UI (e.g. RTL)
    if region and hasattr(region, "is_rtl"):
        out.setdefault("rtl", bool(getattr(region, "is_rtl", False)))
    # Region/country for modules that must not read school.default_region directly
    if region and hasattr(region, "country_code"):
        out.setdefault(
            "country_code", (getattr(region, "country_code", None) or "")[:10]
        )
    # Plan tier for KB/support (from school.plan FK)
    plan = getattr(school, "plan", None)
    if plan and hasattr(plan, "slug"):
        out.setdefault("plan_slug", (getattr(plan, "slug", None) or "").strip().lower())

    # Wedge 14–22: sector-driven policy defaults (before tenant overrides so tenant can override)
    _merge_sector_defaults_into_policy(out, school)

    _merge_education_registry_into_policy(out, school)

    # Tenant overrides from School.settings (JSON)
    settings = getattr(school, "settings", None)
    if isinstance(settings, dict) and settings:
        if "terminology" in settings:
            out["terminology"] = {**out["terminology"], **settings["terminology"]}
        if "grading" in settings:
            out["grading"] = {**out["grading"], **settings["grading"]}
        if "grade_approval" in settings and isinstance(
            settings["grade_approval"], dict
        ):
            out["grade_approval"] = {
                **out.get("grade_approval", {}),
                **settings["grade_approval"],
            }
        if "workflows" in settings:
            out["workflows"] = {**out["workflows"], **settings["workflows"]}
        if "rtl" in settings:
            out["rtl"] = bool(settings["rtl"])
        if "default_language" in settings:
            out["default_language"] = settings["default_language"]
        if "grading_scale" in settings:
            out["grading"] = {
                **out.get("grading", {}),
                "grading_scale": settings["grading_scale"],
            }
        if "education_dna_preset" in settings:
            out["education_dna_preset"] = settings["education_dna_preset"]
        if "admissions" in settings and isinstance(settings["admissions"], dict):
            out["admissions"] = {**out.get("admissions", {}), **settings["admissions"]}
        if "terminology" in settings and isinstance(settings["terminology"], dict):
            if "admission_number_label" in settings["terminology"]:
                out["terminology"]["admission_number_label"] = settings["terminology"][
                    "admission_number_label"
                ]
        # Pass-through for modules that must not read school.settings directly
        if "forms" in settings and isinstance(settings["forms"], dict):
            for form_name, form_schema in settings["forms"].items():
                if isinstance(form_schema, dict) and "fields" in form_schema:
                    out["forms"][form_name] = form_schema
        for key in (
            "report_labels",
            "education_profile_code",
            "payment_gateways",
            "labels_map",
            "education_profile",
            "security_weights",
            "security_weights_override",
            "security_grace_period_days",
            "security_posture_review_interval_days",
            "password_rotation_days",
            "provisioning",
            "contact_email",
            "term_preset",
        ):
            if key in settings:
                out[key] = settings[key]
        # Section 10 + 25.7: merge finance, attendance, communication, hr_staff, compliance, a11y from school.settings
        for key in (
            "finance",
            "attendance",
            "communication",
            "hr_staff",
            "compliance",
            "a11y",
            "ai_governance",
        ):
            if key in settings and isinstance(settings[key], dict):
                out[key] = {**out.get(key, {}), **settings[key]}

    # Feature flags from School.features
    features = getattr(school, "features", None)
    if isinstance(features, dict):
        out["features"] = {**out["features"], **features}

    # Register effective-policy field usage in the metadata catalog.
    try:
        from apps.metadata.usage_registry import register_usage

        register_usage("policy", "policy:effective", "grade", "grade_value")
        register_usage("policy", "policy:effective", "application", "admission_number")
        register_usage("policy", "policy:effective", "invoice", "amount")
    except _POLICY_REGISTER_USAGE_ERRORS:
        log_exception_with_context(
            "get_effective_policy: register_usage failed (optional metadata catalog)",
            school_id=getattr(school, "id", None),
            extra={"section": "policy:effective"},
        )

    # Admissions: if not set from school.settings, backfill from platform effective settings (single-tenant / backward compat)
    _backfill_admissions_from_platform_site_settings(out, school)
    # Section 22: TenantAdmissionNumberPolicy overrides when present for this school
    if school is not None:
        try:
            from apps.siteconfig.models import TenantAdmissionNumberPolicy

            policy_model = TenantAdmissionNumberPolicy.objects.filter(
                school=school, is_active=True
            ).first()
            if policy_model:
                out["admissions"] = {
                    **out["admissions"],
                    "admission_number_strategy": getattr(
                        policy_model, "strategy", "FULL"
                    )
                    or "FULL",
                    "admission_number_template": (
                        getattr(policy_model, "template", None) or ""
                    ).strip(),
                    "admission_number_pattern": (
                        getattr(policy_model, "pattern", None) or ""
                    ).strip(),
                    "school_code": (
                        getattr(policy_model, "school_code", None)
                        or default_school_code_for(school)
                    )
                    or default_school_code_for(school),
                    "seq_width": getattr(policy_model, "seq_width", 4),
                    "reset_frequency": getattr(
                        policy_model, "reset_frequency", "YEARLY"
                    ),
                }
        except _POLICY_MERGE_ERRORS as e:
            logger.debug("TenantAdmissionNumberPolicy merge failed: %s", e)

    # Grade approval (evals): backfill from get_effective_site_settings when not in school.settings (Phase 1)
    if not out.get("grade_approval") or not isinstance(out.get("grade_approval"), dict):
        out["grade_approval"] = out.get("grade_approval") or {}
    if not any(
        k in out["grade_approval"] for k in ("grade_post_roles", "grade_approval_roles")
    ):
        try:
            from apps.siteconfig.models import (
                default_grade_approval_roles,
                default_grade_post_roles,
            )

            # config-resolver-allow: 6 distinct grade_approval attrs read off one resolve + None-guard raises into fallback
            site = get_effective_site_settings(school=school)
            if site is None:
                raise LookupError("effective site settings unavailable")
            out["grade_approval"] = {
                **out["grade_approval"],
                "grade_post_roles": getattr(site, "grade_post_roles", None)
                or default_grade_post_roles(),
                "grade_approval_roles": getattr(site, "grade_approval_roles", None)
                or default_grade_approval_roles(),
                "grade_approval_deadline_days": max(
                    1, getattr(site, "grade_approval_deadline_days", 3) or 3
                ),
                "grade_approval_deadline_note": (
                    getattr(site, "grade_approval_deadline_note", None) or ""
                ).strip(),
                "grade_approval_auto_validate": getattr(
                    site, "grade_approval_auto_validate", True
                ),
                "grade_approval_enabled": getattr(
                    site, "grade_approval_enabled", False
                ),
            }
        except (AttributeError, ImportError, LookupError, TypeError, ValueError) as e:
            logger.debug("Grade approval backfill from effective site settings failed: %s", e)
            from apps.siteconfig.models import (
                default_grade_approval_roles,
                default_grade_post_roles,
            )

            out["grade_approval"].setdefault(
                "grade_post_roles", default_grade_post_roles()
            )
            out["grade_approval"].setdefault(
                "grade_approval_roles", default_grade_approval_roles()
            )
            out["grade_approval"].setdefault("grade_approval_deadline_days", 3)
            out["grade_approval"].setdefault("grade_approval_deadline_note", "")
            out["grade_approval"].setdefault("grade_approval_auto_validate", True)
            out["grade_approval"].setdefault("grade_approval_enabled", False)

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
        except _POLICY_CACHE_ERRORS as e:
            logger.debug("Policy cache set (final) failed: %s", e)
    return out


def get_tenant_blueprint(school) -> Dict[str, Any]:
    """Return normalized blueprint for the active tenant (school). Used by registry.get_tenant_blueprint(request)."""
    return get_effective_policy(school)
