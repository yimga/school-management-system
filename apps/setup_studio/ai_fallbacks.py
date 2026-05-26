"""Deterministic fallbacks for wizard AI prompts.

When ``services.ai_helpers.invoke_with_request`` returns ``None``
(AI disabled, timeout, invalid JSON, out-of-options value), the wizard
engine falls back to these pure functions. Each fallback returns the same
shape the AI would, with ``confidence`` ≤ 0.5 by convention.

Fallback selection: ``apps.setup_studio.wizard_ai`` looks up
``fallback_<prompt_key_underscored>`` in this module.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "fallback_prompt_whitelabel_suggest_palette",
    "fallback_prompt_sovereignty_suggest_jurisdiction",
    "fallback_prompt_sovereignty_suggest_vocabulary_pack",
    "fallback_prompt_grading_suggest_track",
    "fallback_prompt_migration_classify_csv_columns",
    "fallback_prompt_helpcenter_tag_policy_section",
    "fallback_prompt_fintech_suggest_apm",
    "fallback_prompt_fintech_suggest_split_allocation",
    "fallback_prompt_marketplace_suggest_storefront_categories",
    "fallback_prompt_pos_suggest_terminal_layout",
    "fallback_prompt_safeguarding_suggest_routing",
    "fallback_prompt_comms_translate_template",
    "fallback_prompt_compliance_suggest_access_trigger",
    "fallback_prompt_hr_suggest_labor_contract",
    "fallback_prompt_analytics_suggest_kpis",
    "fallback_prompt_observability_suggest_thresholds",
    "fallback_prompt_scheduling_solve_conflicts",
    "fallback_prompt_fieldtrip_suggest_costs",
    "fallback_prompt_pathway_suggest_courses",
    "fallback_prompt_universal_branch_rationale",
    "fallback_prompt_universal_natural_language_intake",
    "FALLBACK_REGISTRY",
]


def _first_option_value(options: list[dict[str, Any]]) -> str | None:
    if not options:
        return None
    first = options[0]
    if isinstance(first, dict):
        return first.get("value")
    return None


def fallback_prompt_whitelabel_suggest_palette(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    val = _first_option_value(options) or "neutral_indigo"
    return {
        "palette_key": val,
        "primary_color_hex": "#4F46E5",
        "secondary_color_hex": "#10B981",
        "confidence": 0.35,
    }


def fallback_prompt_sovereignty_suggest_jurisdiction(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    cc = context.get("country_code") or context.get("accept_language_country") or "US"
    return {
        "country_code": cc,
        "state_code": None,
        "data_residency_region": _first_option_value(options) or "us-east-1",
        "confidence": 0.30,
    }


def fallback_prompt_sovereignty_suggest_vocabulary_pack(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "vocabulary_pack_key": _first_option_value(options) or "default_en",
        "term_override_count": 0,
        "confidence": 0.30,
    }


def fallback_prompt_grading_suggest_track(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    cc = (context.get("country_code") or "").upper()
    track = "ib_diploma" if cc not in {"US", "GB"} else "local_k12"
    return {
        "track_keys": [track],
        "assessment_metric_default": "percentage",
        "confidence": 0.30,
    }


def fallback_prompt_migration_classify_csv_columns(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"mappings": [], "unmapped": [], "confidence": 0.0}


def fallback_prompt_helpcenter_tag_policy_section(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "audience_tags": ["all_parents"],
        "applicable_grades": [],
        "confidence": 0.30,
    }


def fallback_prompt_fintech_suggest_apm(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    cc = (context.get("country_code") or "").upper()
    apm_map = {
        "IN": "upi_rupay",
        "BR": "pix_brcode",
        "KE": "mpesa_stk",
        "TZ": "mpesa_stk",
        "UG": "mpesa_stk",
        "GH": "mobile_money_gh",
        "NG": "paystack_card",
    }
    recommended = apm_map.get(cc, "stripe_card")
    return {
        "recommended_apm_key": recommended,
        "fallback_apm_keys": ["stripe_card"],
        "confidence": 0.50,
        "rationale_token": f"wizards.fintech.rationale.fallback_{cc.lower() or 'default'}",
    }


def fallback_prompt_fintech_suggest_split_allocation(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "allocations": [
            {"purpose": "tuition", "percentage": 70},
            {"purpose": "transportation", "percentage": 10},
            {"purpose": "cafeteria", "percentage": 10},
            {"purpose": "extracurricular", "percentage": 10},
        ],
        "confidence": 0.35,
    }


def fallback_prompt_marketplace_suggest_storefront_categories(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "category_keys": ["uniforms", "textbooks", "stationery", "event_tickets"],
        "confidence": 0.40,
    }


def fallback_prompt_pos_suggest_terminal_layout(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"layout_key": "single_cafeteria_tablet", "confidence": 0.35}


def fallback_prompt_safeguarding_suggest_routing(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"routing_path_key": "counselor_principal_safeguarding_lead", "confidence": 0.40}


def fallback_prompt_comms_translate_template(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    # Cannot fake translations; return empty + confidence 0 so caller knows to fall back to source-only.
    return {"translations": {}, "confidence": 0.0}


def fallback_prompt_compliance_suggest_access_trigger(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trigger_keys": ["troubleshooting_active_bug", "customer_request"],
        "confidence": 0.40,
    }


def fallback_prompt_hr_suggest_labor_contract(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    cc = (context.get("country_code") or "").upper()
    weekly = {"FR": 35, "DE": 40, "US": 40, "IN": 48, "KE": 45}.get(cc, 40)
    return {
        "contract_template_key": "default_salaried",
        "overtime_threshold_hours": weekly,
        "confidence": 0.40,
    }


def fallback_prompt_analytics_suggest_kpis(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kpi_keys": ["enrollment_retention_pct", "tuition_collection_velocity_days", "class_passing_avg_pct"],
        "confidence": 0.40,
    }


def fallback_prompt_observability_suggest_thresholds(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"error_threshold": 0.5, "latency_threshold_ms": 1500, "confidence": 0.50}


def fallback_prompt_scheduling_solve_conflicts(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"schedule_proposals": [], "conflicts_remaining": -1, "confidence": 0.0}


def fallback_prompt_fieldtrip_suggest_costs(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"cost_per_student_decimal": "0.00", "cost_breakdown": {}, "confidence": 0.0}


def fallback_prompt_pathway_suggest_courses(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"course_keys": [], "schedule_fit_score": 0.0, "confidence": 0.0}


def fallback_prompt_universal_branch_rationale(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "rationale_text": "These options reflect typical defaults for similar schools.",
        "confidence": 0.40,
    }


def fallback_prompt_universal_natural_language_intake(
    context: dict[str, Any], options: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"parsed_fields": {}, "unresolved_phrases": [], "confidence": 0.0}


FALLBACK_REGISTRY: dict[str, Any] = {
    "prompt.whitelabel.suggest_palette": fallback_prompt_whitelabel_suggest_palette,
    "prompt.sovereignty.suggest_jurisdiction": fallback_prompt_sovereignty_suggest_jurisdiction,
    "prompt.sovereignty.suggest_vocabulary_pack": fallback_prompt_sovereignty_suggest_vocabulary_pack,
    "prompt.grading.suggest_track": fallback_prompt_grading_suggest_track,
    "prompt.migration.classify_csv_columns": fallback_prompt_migration_classify_csv_columns,
    "prompt.helpcenter.tag_policy_section": fallback_prompt_helpcenter_tag_policy_section,
    "prompt.fintech.suggest_apm": fallback_prompt_fintech_suggest_apm,
    "prompt.fintech.suggest_split_allocation": fallback_prompt_fintech_suggest_split_allocation,
    "prompt.marketplace.suggest_storefront_categories": fallback_prompt_marketplace_suggest_storefront_categories,
    "prompt.pos.suggest_terminal_layout": fallback_prompt_pos_suggest_terminal_layout,
    "prompt.safeguarding.suggest_routing": fallback_prompt_safeguarding_suggest_routing,
    "prompt.comms.translate_template": fallback_prompt_comms_translate_template,
    "prompt.compliance.suggest_access_trigger": fallback_prompt_compliance_suggest_access_trigger,
    "prompt.hr.suggest_labor_contract": fallback_prompt_hr_suggest_labor_contract,
    "prompt.analytics.suggest_kpis": fallback_prompt_analytics_suggest_kpis,
    "prompt.observability.suggest_thresholds": fallback_prompt_observability_suggest_thresholds,
    "prompt.scheduling.solve_conflicts": fallback_prompt_scheduling_solve_conflicts,
    "prompt.fieldtrip.suggest_costs": fallback_prompt_fieldtrip_suggest_costs,
    "prompt.pathway.suggest_courses": fallback_prompt_pathway_suggest_courses,
    "prompt.universal.branch_rationale": fallback_prompt_universal_branch_rationale,
    "prompt.universal.natural_language_intake": fallback_prompt_universal_natural_language_intake,
}
