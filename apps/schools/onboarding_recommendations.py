"""Explainable, deterministic and review-gated tenant configuration autopilot.

The output is a decision record, not an entitlement grant.  It resolves real
versioned blueprint contracts, recommends the smallest module/compliance/plan
set justified by the supplied signals, records validation repairs, and remains
safe to recompute for an existing tenant without overwriting confirmed choices.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, NotRequired, TypedDict

from apps.schools.onboarding_profile import normalize_institution_profile

MANIFEST_VERSION = 5
ENGINE_ID = "tenant-configuration-autopilot-v5"

#: Country-specific secondary-cycle blueprints, keyed by ISO-3166-1 alpha-2.
#: A registry rather than an inline per-country equality branch, so that adding a
#: country is a data edit, not a change to the resolution logic
#: (scripts/check_no_hardcoding.py). Countries absent here fall through to the
#: generic secondary/primary blueprints below, which is the pre-existing
#: behaviour for every country except CM.
COUNTRY_SECONDARY_BLUEPRINTS: dict[str, tuple[str, str]] = {
    "CM": ("cameroon-gce-school", "BP-CM-GCE-001"),
}


def _build_confidence_envelope(
    *,
    country: str,
    cycles: list[str],
    languages: list[str],
    profile: dict[str, Any],
    explicit_inputs: set[str] | list[str],
    warnings: list[Any],
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    """Return an explainable evidence score, never a fabricated probability.

    ``overall_score`` measures recommendation readiness.  It is deliberately
    decomposed so the UI cannot imply statistical accuracy from a count of
    fields.  A high-confidence label is gated by complete critical evidence,
    resolved registries, contradiction-free inputs and stable deterministic
    rules.  Statistical calibration is reported separately and remains
    ``not-applicable`` while the engine is rules-based.
    """

    explicit = set(explicit_inputs)
    critical = {
        "country": bool(country),
        "education_cycles": bool(cycles),
        "languages": bool(languages),
        "funding_type": bool(profile.get("funding_type")),
        "learner_scale": bool(profile.get("student_capacity"))
        or "learner_scale" in explicit,
        "campus_structure": "organization_scope" in explicit
        or bool(profile.get("organization_scope")),
        "connectivity": "connectivity_profile" in explicit,
        "operating_model": "operating_model" in explicit,
        "migration_scope": bool(profile.get("migration_vendor"))
        or bool(profile.get("migration_domains"))
        or profile.get("migration_complexity") == "none",
    }
    missing = [key for key, present in critical.items() if not present]
    completeness = round(100 * (len(critical) - len(missing)) / len(critical))
    registries_resolved = bool(country) and bool(
        blueprint.get("all_contracts_resolved")
    )
    registry_coverage = 100 if registries_resolved else 45 if country else 0
    contradiction_count = len(warnings)
    consistency = max(0, 100 - contradiction_count * 25)
    # Deterministic recommendations are stable for an identical normalized
    # payload.  Missing critical inputs reduce sensitivity stability because a
    # default change can legitimately alter the result.
    stability = max(0, 100 - len(missing) * 12)
    provenance = 100 if registries_resolved and blueprint.get("rule_ids") else 55
    components = {
        "input_completeness": completeness,
        "registry_coverage": registry_coverage,
        "input_consistency": consistency,
        "recommendation_stability": stability,
        "provenance_coverage": provenance,
    }
    weights = {
        "input_completeness": 30,
        "registry_coverage": 25,
        "input_consistency": 20,
        "recommendation_stability": 15,
        "provenance_coverage": 10,
    }
    overall = round(
        sum(components[key] * weights[key] for key in components) / 100
    )
    high_confidence_eligible = bool(
        overall >= 90
        and not missing
        and not contradiction_count
        and registries_resolved
    )
    if high_confidence_eligible:
        label = "high"
        status = "eligible"
    elif overall >= 70:
        label = "provisional"
        status = "needs-confirmation"
    else:
        label = "low"
        status = "insufficient-evidence"
    return {
        "schema_version": 1,
        "score_kind": "recommendation-readiness-not-prediction-probability",
        "overall_score": overall,
        "label": label,
        "status": status,
        "high_confidence_eligible": high_confidence_eligible,
        "components": components,
        "weights": weights,
        "critical_evidence": critical,
        "missing_critical_evidence": missing,
        "contradiction_count": contradiction_count,
        "registry_status": "resolved" if registries_resolved else "incomplete",
        "calibration": {
            "method": "deterministic-rules",
            "statistical_probability": False,
            "status": "not-applicable",
            "statement": "This score measures evidence readiness, not outcome probability.",
        },
    }


class RecommendationCard(TypedDict):
    key: str
    label: str
    value: Any
    display_value: str
    reason: str
    confidence: str
    confidence_score: int
    decision: str
    dependencies: list[str]
    rule_ids: list[str]
    alternatives: list[str]
    editable: bool
    recommended: bool
    requires_confirmation: bool
    binding: str
    upgrade_boundary: NotRequired[str]


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _recommendation(
    key: str,
    label: str,
    value: Any,
    *,
    reason: str,
    confidence_score: int,
    decision: str = "automatic",
    dependencies: list[str] | None = None,
    rule_ids: list[str] | None = None,
    alternatives: list[str] | None = None,
    requires_confirmation: bool = True,
    upgrade_boundary: str = "",
) -> RecommendationCard:
    score = min(100, max(0, int(confidence_score)))
    card: RecommendationCard = {
        "key": key,
        "label": label,
        "value": value,
        "display_value": ", ".join(str(item) for item in value)
        if isinstance(value, list)
        else str(value),
        "reason": reason,
        "confidence": "high" if score >= 80 else "medium" if score >= 55 else "low",
        "confidence_score": score,
        "decision": decision,
        "dependencies": dependencies or [],
        "rule_ids": rule_ids or [],
        "alternatives": alternatives or [],
        "editable": True,
        "recommended": True,
        "requires_confirmation": requires_confirmation,
        "binding": "recommendation-only",
    }
    if upgrade_boundary:
        card["upgrade_boundary"] = upgrade_boundary
    return card


def _blueprint_record(key: str) -> dict[str, Any]:
    """Resolve an actual catalog contract; return a safe unresolved record."""

    try:
        from apps.platform_runtime.blueprint_contract import get_blueprint

        contract = get_blueprint(key)
    except (ImportError, RuntimeError, ValueError):
        contract = None
    if contract is None:
        return {
            "key": key,
            "version": "unresolved",
            "status": "catalog-resolution-required",
            "tenant_safe": False,
            "requires_platform_operator": True,
            "modules": [],
        }
    return {
        "key": contract.key,
        "version": contract.version,
        "name": contract.name,
        "status": contract.status,
        "scope": contract.scope,
        "tenant_safe": contract.tenant_safe,
        "requires_platform_operator": contract.requires_platform_operator,
        "requires_confirmation": contract.requires_confirmation,
        "modules": list(contract.modules),
        "dashboard_packs": list(contract.dashboard_packs),
        "workflow_packs": list(contract.workflow_packs),
        "policy_bundles": list(contract.policy_bundles),
        "app_catalog_recommendations": list(contract.app_catalog_recommendations),
    }


def _resolve_blueprints(
    *,
    country: str,
    cycles: list[str],
    languages: list[str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    cycle_text = " ".join(cycles)
    has_secondary = any(
        token in cycle_text for token in ("secondary", "high", "sss", "tvet")
    )
    scope = profile["organization_scope"]
    assessment = profile["assessment_profile"]
    services = set(profile["operational_services"])
    connectivity = profile["connectivity_profile"]

    if scope in {"district", "network"} or profile["campus_count"] > 1:
        primary_key = "multi-campus-network"
        primary_rule = "BP-NETWORK-001"
    elif assessment in {"international", "mixed"}:
        primary_key = "international-school"
        primary_rule = "BP-INTERNATIONAL-001"
    elif has_secondary and country in COUNTRY_SECONDARY_BLUEPRINTS:
        primary_key, primary_rule = COUNTRY_SECONDARY_BLUEPRINTS[country]
    elif has_secondary:
        primary_key = "private-secondary-school"
        primary_rule = "BP-SECONDARY-001"
    else:
        primary_key = "private-primary-school"
        primary_rule = "BP-PRIMARY-001"

    overlay_keys: list[str] = []
    if "boarding" in services and primary_key != "boarding-school":
        overlay_keys.append("boarding-school")
    if connectivity in {"limited", "offline-first"} and primary_key != "low-connectivity-school":
        overlay_keys.append("low-connectivity-school")
    if len(languages) > 1 and primary_key != "bilingual-school":
        overlay_keys.append("bilingual-school")
    if assessment in {"international", "mixed"} and primary_key != "international-school":
        overlay_keys.append("international-school")

    primary = _blueprint_record(primary_key)
    overlays = [_blueprint_record(key) for key in _dedupe(overlay_keys)]
    return {
        "primary": primary,
        "overlays": overlays,
        "rule_ids": [primary_rule, *[f"BP-OVERLAY-{row['key'].upper()}" for row in overlays]],
        "requires_platform_operator": bool(
            primary.get("requires_platform_operator")
            or any(row.get("requires_platform_operator") for row in overlays)
        ),
        "all_contracts_resolved": primary.get("version") != "unresolved"
        and all(row.get("version") != "unresolved" for row in overlays),
    }


def build_onboarding_recommendations(
    *,
    country_code: str,
    education_cycles: list[str] | None = None,
    language_codes: list[str] | None = None,
    institution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    country = str(country_code or "").strip().upper()[:2]
    cycles = _dedupe(
        [str(value).strip().lower() for value in (education_cycles or []) if value]
    )
    languages = _dedupe(
        [str(value).strip().lower() for value in (language_codes or []) if value]
    )
    normalized = normalize_institution_profile(institution_profile)
    profile = dict(normalized.values)
    capacity = profile["student_capacity"]
    campus_count = profile["campus_count"]
    staff_count = profile["staff_count"]
    scope = profile["organization_scope"]
    multi_campus = scope in {"district", "network"} or campus_count > 1
    services = set(profile["operational_services"])
    connectivity = profile["connectivity_profile"]
    payment = profile["payment_profile"]
    assessment = profile["assessment_profile"]
    identity = profile["identity_profile"]
    residency = profile["data_residency_requirement"]
    accessibility = profile["accessibility_profile"]
    migration_complexity = profile["migration_complexity"]
    automation = profile["automation_preference"]
    session_pattern = profile["session_pattern"]
    curriculum_board = profile["curriculum_board"]
    governance_profile = profile["governance_profile"]
    migration_vendor = profile["migration_vendor"]
    migration_domains = profile["migration_domains"]
    from apps.schools.onboarding_strands import parse_operational_strands

    operational_strands = parse_operational_strands(
        (institution_profile or {}).get("operational_strands")
        if isinstance(institution_profile, dict)
        else None
    )
    profile["operational_strands"] = operational_strands

    blueprint = _resolve_blueprints(
        country=country,
        cycles=cycles,
        languages=languages,
        profile=profile,
    )
    modules = ["student-information", "attendance", "family-portal", "communications"]
    primary_modules = [
        str(value).strip().lower().replace(" ", "-")
        for value in blueprint["primary"].get("modules", [])
    ]
    modules.extend(primary_modules)
    if multi_campus:
        modules += ["district-governance", "cross-campus-analytics", "delegated-administration"]
    if capacity >= 1000 or staff_count >= 150:
        modules += ["bulk-operations", "advanced-analytics"]
    if capacity >= 5000 or staff_count >= 500:
        modules += ["data-warehouse", "workflow-operations-center"]
    if "boarding" in services:
        modules += ["boarding", "residence-management", "student-welfare", "duty-roster"]
    if "transport" in services:
        modules += ["transport", "fleet-operations", "route-safety"]
    if "cafeteria" in services:
        modules += ["meal-operations"]
    if "clinic" in services:
        modules += ["health-safety", "incident-care"]
    if "athletics" in services:
        modules += ["athletics", "clubs-activities"]
    if payment in {"online", "multi-channel", "complex-aid"}:
        modules += ["fees-finance", "payments", "reconciliation"]
    if payment == "complex-aid":
        modules += ["financial-aid", "scholarship-management"]
    if connectivity in {"limited", "offline-first"}:
        modules += ["offline-sync", "continuity-operations", "conflict-review"]
    if assessment in {"national", "mixed"}:
        modules += ["examinations", "regulatory-reporting"]
    if assessment in {"competency", "mixed"}:
        modules += ["competency-assessment"]
    if assessment in {"international", "mixed"}:
        modules += ["international-programmes", "transcript-portability"]
    if identity != "password":
        modules += ["identity-federation", "identity-lifecycle"]
    if residency != "country-default":
        modules += ["data-residency-controls", "retention-audit"]
    if accessibility in {"enhanced", "intensive"}:
        modules += ["accessibility-assist", "inclusive-learning"]
    if accessibility == "intensive":
        modules += ["inclusion-case-management"]
    if session_pattern in {"double", "continuous"}:
        modules += ["multi-session-timetable"]
    if curriculum_board in {"cambridge", "ib"}:
        modules += ["international-curriculum"]
    if any(
        code in {"vocational_trade", "vocational_apprenticeship", "w32_tvet"}
        for code in operational_strands
    ):
        modules += ["vocational-pathways"]
    if "special_education" in operational_strands:
        modules += ["special-education-support"]
    if governance_profile == "strict":
        modules += ["compliance-governance", "data-residency-controls"]
    if migration_complexity != "none" or migration_vendor or migration_domains:
        modules += ["guided-data-migration", "migration-reconciliation"]
    if migration_complexity in {"multi-system", "legacy-high-risk"}:
        modules += ["migration-orchestrator", "data-quality-workbench"]
    if automation == "automation-first":
        modules += ["workflow-automation", "operational-alerting"]
    modules = _dedupe(modules)

    enterprise_reasons: list[str] = []
    if multi_campus:
        enterprise_reasons.append("multiple campuses or shared governance")
    if capacity >= 2500 or staff_count >= 300:
        enterprise_reasons.append("high operating scale")
    if residency == "self-hosted":
        enterprise_reasons.append("self-hosted residency requirement")
    if migration_complexity == "legacy-high-risk":
        enterprise_reasons.append("high-risk legacy migration")
    operations_reasons: list[str] = []
    if services:
        operations_reasons.append("specialized daily operations")
    if payment not in {"basic", "cash-only"}:
        operations_reasons.append("digital or multi-channel finance")
    if connectivity in {"limited", "offline-first"}:
        operations_reasons.append("offline-first continuity")
    if capacity >= 1000 or automation == "automation-first":
        operations_reasons.append("analytics and automation scale")

    if enterprise_reasons:
        subscription_plan = "campus-enterprise"
        plan_reason = "; ".join(enterprise_reasons)
        plan_boundary = "Operator confirmation and enterprise pricing are required before activation."
    elif operations_reasons:
        subscription_plan = "school-pro-operations"
        plan_reason = "; ".join(operations_reasons)
        plan_boundary = "Operations modules remain review-gated; paid capabilities are not auto-enabled."
    else:
        subscription_plan = "school-pro"
        plan_reason = "single-school core operations with standard scale"
        plan_boundary = "Upgrade only when scale or specialized operations require it."

    compliance_profiles = _dedupe(
        [
            f"country-registry:{country or 'default'}",
            f"assessment:{assessment}",
            f"residency:{residency}",
            f"accessibility:{accessibility}",
        ]
    )
    migration_mode = (
        "not-required"
        if migration_complexity == "none" and not migration_vendor and not migration_domains
        else "operator-assisted-staged-import"
        if migration_complexity == "legacy-high-risk"
        else "multi-source-staged-import"
        if migration_complexity == "multi-system"
        else "guided-staged-import"
    )
    recommendations = {
        "blueprint": blueprint,
        "modules": modules,
        "apps": _dedupe(
            [
                "offline-capture",
                "family-portal",
                "teacher-workspace",
                *blueprint["primary"].get("app_catalog_recommendations", []),
            ]
        ),
        "institution_profile": "multi-campus" if multi_campus else "single-campus",
        "district": "district-console" if multi_campus else "not-required",
        "lms": profile["lms_preference"]
        if profile["lms_preference"] not in {"", "none"}
        else "native-learning-workspace",
        "grading": "registry-matched grading framework",
        "languages": languages or ["country-default"],
        "dashboard": "network-executive" if multi_campus else "role-based-school-operations",
        "local_first": "offline-first" if connectivity == "offline-first" else "offline-ready",
        "session_pattern": session_pattern,
        "curriculum_board": curriculum_board or "national-default",
        "operational_strands": operational_strands,
        "governance": "strict-compliance-profile" if governance_profile == "strict" else "standard-compliance-profile",
        "compliance_profiles": compliance_profiles,
        "identity": identity,
        "subscription_plan": subscription_plan,
        "migration": {
            "vendor": migration_vendor or "not-declared",
            "domains": migration_domains,
            "complexity": migration_complexity,
            "mode": migration_mode,
        },
    }

    required_signals = [
        (bool(country), "country", "Required to resolve localization and compliance registries."),
        (bool(cycles), "education cycles", "Required to resolve the academic blueprint and grading profile."),
        (bool(profile["funding_type"]), "funding model", "Improves finance and aid recommendations."),
        (bool(capacity), "expected learners", "Improves scale, analytics and plan recommendations."),
    ]
    missing_details = [
        {"field": label, "why": why, "recommended_default": "Review during guided setup"}
        for present, label, why in required_signals
        if not present
    ]
    missing_inputs = [row["field"] for row in missing_details]
    confidence_envelope = _build_confidence_envelope(
        country=country,
        cycles=cycles,
        languages=languages,
        profile=profile,
        explicit_inputs=normalized.explicit_inputs,
        warnings=normalized.warnings,
        blueprint=blueprint,
    )
    confidence_score = confidence_envelope["overall_score"]

    cards: list[RecommendationCard] = [
        _recommendation(
            "blueprint",
            "Blueprint",
            f"{blueprint['primary']['key']}@{blueprint['primary']['version']}",
            reason="Resolved from the live blueprint catalog using country, cycles, scope and operating overlays.",
            confidence_score=confidence_score,
            decision="confirm-with-operator" if blueprint["requires_platform_operator"] else "confirm",
            dependencies=["blueprint-catalog", "country-registry", "education-cycles"],
            rule_ids=blueprint["rule_ids"],
            alternatives=[row["key"] for row in blueprint["overlays"]],
        ),
        _recommendation(
            "modules",
            "Day-one modules",
            modules,
            reason="Smallest justified set after scale, services, finance, assessment, identity, accessibility and migration rules.",
            confidence_score=confidence_score,
            decision="confirm",
            rule_ids=["MOD-PROFILE-001", "MOD-MINIMUM-SET-001"],
        ),
        _recommendation(
            "compliance_profiles",
            "Compliance profiles",
            compliance_profiles,
            reason="Country, assessment, residency and accessibility requirements are kept as separate auditable profiles.",
            confidence_score=confidence_score,
            decision="confirm",
            dependencies=["country-registry", "policy-registry"],
            rule_ids=["COMPLIANCE-COMPOSE-001"],
        ),
        _recommendation(
            "dashboard",
            "Workspace",
            recommendations["dashboard"],
            reason="Matched to governance scope, scale and declared automation preference.",
            confidence_score=confidence_score,
            rule_ids=["DASHBOARD-SCOPE-001"],
        ),
        _recommendation(
            "local_first",
            "Continuity profile",
            recommendations["local_first"],
            reason="Every tenant receives offline protection; intermittent sites receive conflict and continuity workflows.",
            confidence_score=confidence_score,
            rule_ids=["OFFLINE-BASELINE-001", f"OFFLINE-{connectivity.upper()}"],
        ),
        _recommendation(
            "subscription_plan",
            "Best-fit plan",
            subscription_plan,
            reason=plan_reason,
            confidence_score=confidence_score,
            decision="confirm-with-operator",
            dependencies=["plan-catalog", "operator-confirmation"],
            rule_ids=["PLAN-MINIMUM-FIT-001"],
            alternatives=["school-pro", "school-pro-operations", "campus-enterprise"],
            upgrade_boundary=plan_boundary,
        ),
        _recommendation(
            "migration",
            "Data migration",
            recommendations["migration"],
            reason="Migration depth, source systems and data domains determine staging, reconciliation and operator review.",
            confidence_score=confidence_score,
            decision="confirm",
            dependencies=["migration-readiness", "tenant-owner-confirmation"],
            rule_ids=[f"MIGRATION-{migration_complexity.upper()}"],
        ),
    ]

    source_payload = {
        "country_code": country,
        "education_cycles": cycles,
        "language_codes": languages,
        "institution_profile": profile,
    }
    return {
        "version": MANIFEST_VERSION,
        "engine": ENGINE_ID,
        "fingerprint": _fingerprint(source_payload),
        "country_code": country,
        "profile": profile,
        "recommendations": recommendations,
        "recommendation_cards": cards,
        "recommended_flags": {card["key"]: card["value"] for card in cards},
        "reason_labels": _dedupe(
            [
                "country registry" if country else "",
                "education cycles" if cycles else "",
                "language profile" if languages else "",
                *[field.replace("_", " ") for field in normalized.explicit_inputs],
            ]
        ),
        "missing_inputs": missing_inputs,
        "missing_input_details": missing_details,
        "confidence": confidence_envelope["label"],
        "confidence_score": confidence_score,
        "confidence_envelope": confidence_envelope,
        "validation_issues": normalized.issue_payload(),
        "source": "signup-intent",
        "offline_safe": True,
        "review_state": {
            "status": "pending-confirmation",
            "confirmed": False,
            "overridden": False,
            "override_reason_required": True,
            "operator_locked": False,
        },
        "provisioning": {
            "mode": "recommendation-only",
            "safe_automatic_steps": ["localization", "language-pack", "offline-baseline"],
            "review_gated_steps": ["blueprint", "modules", "compliance", "subscription", "migration"],
            "auto_apply_paid_entitlements": False,
        },
        "subscription": {
            "recommended_slug": subscription_plan,
            "binding": "recommendation-only",
            "requires_confirmation": True,
            "auto_entitlement": False,
            "reason": plan_reason,
            "upgrade_boundary": plan_boundary,
        },
    }


def ensure_school_recommendations(school, *, save: bool = True) -> dict[str, Any]:
    """Create or refresh a manifest without overwriting confirmed tenant choices."""

    settings = dict(getattr(school, "settings", None) or {})
    intent = dict(settings.get("onboarding_intent") or {})
    cycles = list(intent.get("education_cycles") or [])
    if not cycles and getattr(school, "pk", None):
        cycles = list(school.education_system_types.values_list("code", flat=True))
    languages = list(intent.get("language_codes") or [])
    primary = str(getattr(school, "primary_language", "") or "").strip()
    if not languages and primary:
        languages = [primary]
    institution_profile = dict(intent.get("institution_profile") or {})
    migration_intent = dict(settings.get("migration_intent") or {})
    if migration_intent:
        institution_profile.setdefault("migration_vendor", migration_intent.get("vendor") or "")
        institution_profile.setdefault("migration_domains", migration_intent.get("data_domains") or [])
    manifest = build_onboarding_recommendations(
        country_code=getattr(school, "country_code", ""),
        education_cycles=cycles,
        language_codes=languages,
        institution_profile=institution_profile,
    )
    current = settings.get("recommendation_manifest")
    if isinstance(current, dict):
        current_review = current.get("review_state")
        if isinstance(current_review, dict) and (
            current_review.get("confirmed") or current_review.get("operator_locked")
        ):
            # Preserve a human/operator decision.  Surface recomputation as a
            # pending candidate instead of silently changing active intent.
            if current.get("fingerprint") != manifest["fingerprint"]:
                manifest["review_state"] = {
                    **manifest["review_state"],
                    "status": "changed-inputs-require-review",
                    "previous_fingerprint": current.get("fingerprint", ""),
                }
                settings["recommendation_candidate"] = manifest
                if save and getattr(school, "pk", None):
                    school.settings = settings
                    school.save(update_fields=["settings", "updated_at"])
            return current
        if (
            current.get("version") == MANIFEST_VERSION
            and current.get("fingerprint") == manifest["fingerprint"]
        ):
            return current
    if save and getattr(school, "pk", None):
        settings["recommendation_manifest"] = manifest
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
    return manifest


__all__ = [
    "ENGINE_ID",
    "MANIFEST_VERSION",
    "RecommendationCard",
    "build_onboarding_recommendations",
    "ensure_school_recommendations",
]
