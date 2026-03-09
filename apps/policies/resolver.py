"""
Resolve effective policy: platform_defaults ⊕ country_defaults ⊕ tenant_overrides.
Modules must not read School.settings / School.features directly; use get_effective_policy instead.
Optional per-tenant policy caching when POLICY_CACHE_TTL (seconds) is set in settings.
"""
import logging
from typing import Any, Dict, Optional

from apps.siteconfig.identifier_policy_service import default_school_code_for

logger = logging.getLogger(__name__)


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
    out.setdefault("grade_approval", {})  # Phase 1: evals/gradebook — post/approval roles, deadline, auto_validate
    out.setdefault("workflows", {})
    out.setdefault("features", {})
    out.setdefault("admissions", {})
    # Section 10: Full policy-driven configurability per module
    # 10.3 Finance: invoice timing, fee templates, discounts, scholarship, late fee rules, collection flows, write-off, payment providers
    out.setdefault("finance", {
        "invoice_timing": {}, "fee_templates": [], "discounts": [], "scholarship": {},
        "late_fee_rules": [], "collection_flows": [], "write_off": {}, "payment_providers": [],
    })
    # 10.4 Attendance: statuses, lateness rules, absence escalation, homeroom/class model, who marks, parent notification timing
    out.setdefault("attendance", {
        "statuses": [], "lateness_rules": {}, "escalation": {}, "absence_escalation": {},
        "homeroom_model": "", "who_marks": [], "parent_notification_timing": {},
    })
    # 10.5 Communication: channels, fallback order, opt-in/out, digest vs instant, message approval, segmentation, school/quiet hours
    out.setdefault("communication", {
        "channel_order": [], "fallback_order": [], "opt_in_out": {}, "digest_vs_instant": {},
        "message_approval": {}, "segmentation": {}, "school_hours": {}, "quiet_hours": {},
    })
    # 10.6 HR/Staff: recruitment, onboarding, certification tracking, review cycles, leave approvals, substitute workflows
    out.setdefault("hr_staff", {"recruitment": {}, "onboarding": {}, "certification_tracking": {}, "review_cycles": {}, "leave_approvals": {}, "substitute_workflows": {}})
    # 10.7 Compliance: retention, evidence packs, inspector portal, document requirements, safeguarding, regional controls
    out.setdefault("compliance", {
        "retention": {}, "evidence_packs": [], "inspector_portal": {}, "document_requirements": [],
        "safeguarding": {}, "regional_controls": {},
    })
    # Section 25.7: a11y, low-bandwidth, offline-first
    out.setdefault("a11y", {"low_bandwidth": False, "offline_mode": False})
    # Section 29.9: AI governance — tenant-level enable, no-PII external prompt guardrails
    out.setdefault("ai_governance", {"ai_enabled": False, "no_pii_external_prompt": True, "prompt_audit_trail": True})
    # 21.4: Operational identity (workflow/dashboard/comms/fee pack defaults)
    out.setdefault("operational_identity", {"default_workflow_slug": "", "default_dashboard_slug": "", "comms_defaults": {}, "fee_pack_defaults": {}})
    # Section 23.4/24.8: Form schemas (policy-driven field visibility, required, pickers)
    from .form_policy import default_forms_platform
    out["forms"] = default_forms_platform()
    # Terminology defaults for modules (e.g. Admissions)
    if "admission_number_label" not in out["terminology"]:
        out["terminology"]["admission_number_label"] = "Admission number"

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
        except Exception as e:
            logger.debug("Policy cache read failed: %s", e)

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
                        if key in ("terminology", "grading", "grade_approval", "workflows", "features", "admissions", "finance", "attendance", "communication", "hr_staff", "operational_identity", "compliance", "a11y", "ai_governance") and isinstance(value, dict):
                            out[key] = {**out.get(key, {}), **value}
                        elif key == "forms" and isinstance(value, dict):
                            # 23.4: merge form schemas (form_name -> { fields: [...] })
                            for form_name, form_schema in value.items():
                                if isinstance(form_schema, dict) and "fields" in form_schema:
                                    out["forms"][form_name] = form_schema
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
                    except Exception as e:
                        logger.debug("Policy cache set failed: %s", e)
                    return out
    except Exception as e:
        logger.warning("Policy merge from TenantBlueprint failed: %s", e)

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
        if "grade_approval" in settings and isinstance(settings["grade_approval"], dict):
            out["grade_approval"] = {**out.get("grade_approval", {}), **settings["grade_approval"]}
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
        if "admissions" in settings and isinstance(settings["admissions"], dict):
            out["admissions"] = {**out.get("admissions", {}), **settings["admissions"]}
        if "terminology" in settings and isinstance(settings["terminology"], dict):
            if "admission_number_label" in settings["terminology"]:
                out["terminology"]["admission_number_label"] = settings["terminology"]["admission_number_label"]
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
            "provisioning",
            "contact_email",
            "term_preset",
        ):
            if key in settings:
                out[key] = settings[key]
        # Section 10 + 25.7: merge finance, attendance, communication, hr_staff, compliance, a11y from school.settings
        for key in ("finance", "attendance", "communication", "hr_staff", "compliance", "a11y", "ai_governance"):
            if key in settings and isinstance(settings[key], dict):
                out[key] = {**out.get(key, {}), **settings[key]}

    # Feature flags from School.features
    features = getattr(school, "features", None)
    if isinstance(features, dict):
        out["features"] = {**out["features"], **features}

    # Admissions: if not set from school.settings, backfill from SiteSettings (single-tenant / backward compat)
    if not out.get("admissions") or not isinstance(out.get("admissions"), dict):
        out["admissions"] = out.get("admissions") or {}
    if not any(k in out["admissions"] for k in ("admission_number_mode", "admission_number_strategy", "school_code")):
        try:
            from apps.siteconfig.models import SiteSettings
            site = SiteSettings.get_solo()
            out["admissions"] = {
                **out["admissions"],
                "admission_number_mode": getattr(site, "admission_number_mode", "AUTO_OR_MANUAL") or "AUTO_OR_MANUAL",
                "admission_number_strategy": getattr(site, "admission_number_strategy", "FULL") or "FULL",
                "admission_number_template": (getattr(site, "admission_number_template", None) or "") or "",
                "admission_number_pattern": (getattr(site, "admission_number_pattern", None) or "") or "",
                "school_code": (getattr(site, "school_code", None) or default_school_code_for(school)) or default_school_code_for(school),
            }
        except Exception as e:
            logger.debug("Admissions backfill from SiteSettings failed: %s", e)
            out["admissions"].setdefault("admission_number_mode", "AUTO_OR_MANUAL")
            out["admissions"].setdefault("admission_number_strategy", "FULL")
            out["admissions"].setdefault("school_code", default_school_code_for(school))
    # Section 22: TenantAdmissionNumberPolicy overrides when present for this school
    if school is not None:
        try:
            from apps.siteconfig.models import TenantAdmissionNumberPolicy
            policy_model = TenantAdmissionNumberPolicy.objects.filter(school=school, is_active=True).first()
            if policy_model:
                out["admissions"] = {
                    **out["admissions"],
                    "admission_number_strategy": getattr(policy_model, "strategy", "FULL") or "FULL",
                    "admission_number_template": (getattr(policy_model, "template", None) or "").strip(),
                    "admission_number_pattern": (getattr(policy_model, "pattern", None) or "").strip(),
                    "school_code": (getattr(policy_model, "school_code", None) or default_school_code_for(school)) or default_school_code_for(school),
                    "seq_width": getattr(policy_model, "seq_width", 4),
                    "reset_frequency": getattr(policy_model, "reset_frequency", "YEARLY"),
                }
        except Exception as e:
            logger.debug("TenantAdmissionNumberPolicy merge failed: %s", e)

    # Grade approval (evals): backfill from SiteSettings when not in school.settings (Phase 1)
    if not out.get("grade_approval") or not isinstance(out.get("grade_approval"), dict):
        out["grade_approval"] = out.get("grade_approval") or {}
    if not any(k in out["grade_approval"] for k in ("grade_post_roles", "grade_approval_roles")):
        try:
            from apps.siteconfig.models import SiteSettings, default_grade_approval_roles, default_grade_post_roles
            site = SiteSettings.get_solo()
            out["grade_approval"] = {
                **out["grade_approval"],
                "grade_post_roles": getattr(site, "grade_post_roles", None) or default_grade_post_roles(),
                "grade_approval_roles": getattr(site, "grade_approval_roles", None) or default_grade_approval_roles(),
                "grade_approval_deadline_days": max(1, getattr(site, "grade_approval_deadline_days", 3) or 3),
                "grade_approval_deadline_note": (getattr(site, "grade_approval_deadline_note", None) or "").strip(),
                "grade_approval_auto_validate": getattr(site, "grade_approval_auto_validate", True),
                "grade_approval_enabled": getattr(site, "grade_approval_enabled", False),
            }
        except Exception as e:
            logger.debug("Grade approval backfill from SiteSettings failed: %s", e)
            from apps.siteconfig.models import default_grade_approval_roles, default_grade_post_roles

            out["grade_approval"].setdefault("grade_post_roles", default_grade_post_roles())
            out["grade_approval"].setdefault("grade_approval_roles", default_grade_approval_roles())
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
        except Exception as e:
            logger.debug("Policy cache set (final) failed: %s", e)
    return out


def get_tenant_blueprint(school) -> Dict[str, Any]:
    """Return normalized blueprint for the active tenant (school). Used by registry.get_tenant_blueprint(request)."""
    return get_effective_policy(school)
