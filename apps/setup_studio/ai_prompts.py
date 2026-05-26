"""Wizard AI prompt template library.

Keyed by ``prompt_template_key`` (set per-step in wizard JSON's
``ai_recommend.prompt_template_key``). Every prompt produces structured
JSON via the universal envelope.

Routing: all callers go through ``apps.setup_studio.wizard_ai`` →
``services.ai_helpers.invoke_with_request``. App code MUST NOT call
``services.ai_gateway`` directly — boundary scanner enforces.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["UNIVERSAL_ENVELOPE", "PROMPT_LIBRARY", "build_prompt"]


UNIVERSAL_ENVELOPE = """\
SYSTEM:
You are the configuration assistant for RunMyCampus, a multi-tenant school
management platform. Your job is to suggest sensible defaults for setup
wizards based on the school's country, type, language, and prior answers.

CONSTRAINTS:
- Output VALID JSON matching the requested schema. No prose outside the JSON.
- Use ONLY values from the provided options list. If unsure, return an empty
  suggestion object with confidence 0.
- NEVER invent country codes, currency codes, payment vendor names, or
  regulatory body names. Only use what is given in the context.
- NEVER include personally identifiable information in rationale text.
- If you cannot determine a confident default, say so — fallback is acceptable.

USER:
{task_body}

CONTEXT:
{context_json}

OPTIONS:
{options_json}

SCHEMA (your output must match):
{schema_json}
"""


PROMPT_LIBRARY: dict[str, dict[str, Any]] = {
    "prompt.whitelabel.suggest_palette": {
        "task": (
            "Recommend the most culturally appropriate heritage palette for the school's "
            "country, region, and primary language. Heritage palettes are pre-curated; do "
            "NOT invent new colors."
        ),
        "schema": {
            "palette_key": "string (one of option values)",
            "primary_color_hex": "string (#RRGGBB)",
            "secondary_color_hex": "string (#RRGGBB)",
            "confidence": "number 0..1",
        },
    },
    "prompt.sovereignty.suggest_jurisdiction": {
        "task": "Suggest the most likely jurisdiction (country, state, residency region) for this school.",
        "schema": {
            "country_code": "string (ISO-3166-1 alpha-2)",
            "state_code": "string (ISO-3166-2) or null",
            "data_residency_region": "string (one of option values)",
            "confidence": "number 0..1",
        },
    },
    "prompt.sovereignty.suggest_vocabulary_pack": {
        "task": "Recommend the culturally-aligned vocabulary pack for the school.",
        "schema": {
            "vocabulary_pack_key": "string",
            "term_override_count": "integer",
            "confidence": "number 0..1",
        },
    },
    "prompt.grading.suggest_track": {
        "task": (
            "Recommend curriculum tracks (e.g. IB, A-Levels, AP, Local Ministry K-12) "
            "for this school based on country and school type."
        ),
        "schema": {
            "track_keys": "array of strings",
            "assessment_metric_default": "string (one of: gpa_4|gpa_5|percentage|letter|competency|points_100|points_1000)",
            "confidence": "number 0..1",
        },
    },
    "prompt.migration.classify_csv_columns": {
        "task": (
            "Map each source CSV column to a canonical RunMyCampus field. Use ONLY canonical "
            "fields from the OPTIONS list. Set confidence per mapping."
        ),
        "schema": {
            "mappings": "array of {source_column: string, canonical_field: string, confidence: number}",
            "unmapped": "array of strings",
        },
    },
    "prompt.helpcenter.tag_policy_section": {
        "task": "Suggest audience tags and applicable grade levels for this policy section.",
        "schema": {
            "audience_tags": "array of strings (option values)",
            "applicable_grades": "array of strings (option values) or empty",
            "confidence": "number 0..1",
        },
    },
    "prompt.fintech.suggest_apm": {
        "task": (
            "Recommend the most appropriate Alternative Payment Method for this country and "
            "settlement currency. Consider B2C recurring billing fit and API availability."
        ),
        "schema": {
            "recommended_apm_key": "string (option value)",
            "fallback_apm_keys": "array of up to 3 strings",
            "confidence": "number 0..1",
            "rationale_token": "string",
        },
    },
    "prompt.fintech.suggest_split_allocation": {
        "task": "Suggest typical split-ledger allocations for a K-12 school of this size.",
        "schema": {
            "allocations": "array of {purpose: string, percentage: integer}",
            "confidence": "number 0..1",
        },
    },
    "prompt.marketplace.suggest_storefront_categories": {
        "task": "Suggest typical product categories for a school storefront.",
        "schema": {
            "category_keys": "array of strings",
            "confidence": "number 0..1",
        },
    },
    "prompt.pos.suggest_terminal_layout": {
        "task": "Suggest a POS terminal layout (devices, locations) for this school.",
        "schema": {"layout_key": "string", "confidence": "number 0..1"},
    },
    "prompt.safeguarding.suggest_routing": {
        "task": "Suggest a stakeholder routing chain for this incident category in this jurisdiction.",
        "schema": {"routing_path_key": "string", "confidence": "number 0..1"},
    },
    "prompt.comms.translate_template": {
        "task": "Translate this communication template into each target locale, preserving placeholders {{like_this}}.",
        "schema": {
            "translations": "object {locale_code: translated_text}",
            "confidence": "number 0..1",
        },
    },
    "prompt.compliance.suggest_access_trigger": {
        "task": "Suggest typical JIT access triggers for an operator support context.",
        "schema": {"trigger_keys": "array of strings", "confidence": "number 0..1"},
    },
    "prompt.hr.suggest_labor_contract": {
        "task": "Suggest typical labor contract parameters for this country and school size.",
        "schema": {
            "contract_template_key": "string",
            "overtime_threshold_hours": "integer",
            "confidence": "number 0..1",
        },
    },
    "prompt.analytics.suggest_kpis": {
        "task": "Suggest the most relevant board-level KPIs for this school type and country.",
        "schema": {"kpi_keys": "array of strings", "confidence": "number 0..1"},
    },
    "prompt.observability.suggest_thresholds": {
        "task": "Suggest reasonable error-rate, latency, and uptime thresholds for a tenant.",
        "schema": {
            "error_threshold": "number",
            "latency_threshold_ms": "integer",
            "confidence": "number 0..1",
        },
    },
    "prompt.scheduling.solve_conflicts": {
        "task": "Propose a conflict-minimizing schedule given the resource constraints.",
        "schema": {
            "schedule_proposals": "array of objects",
            "conflicts_remaining": "integer",
            "confidence": "number 0..1",
        },
    },
    "prompt.fieldtrip.suggest_costs": {
        "task": "Suggest a per-student cost breakdown for this field trip.",
        "schema": {
            "cost_per_student_decimal": "string (decimal)",
            "cost_breakdown": "object {category: decimal_string}",
            "confidence": "number 0..1",
        },
    },
    "prompt.pathway.suggest_courses": {
        "task": "Suggest elective courses matching the student's target objective and schedule.",
        "schema": {
            "course_keys": "array of strings",
            "schedule_fit_score": "number 0..1",
            "confidence": "number 0..1",
        },
    },
    "prompt.universal.branch_rationale": {
        "task": "Explain in 1-2 sentences why the user's prior answer led to the current set of options.",
        "schema": {"rationale_text": "string (≤200 chars)", "confidence": "number 0..1"},
    },
    "prompt.universal.natural_language_intake": {
        "task": (
            "Parse the user's free-text description into structured fields. "
            "Return ONLY fields listed in TARGET_FIELDS. Note unresolved phrases."
        ),
        "schema": {
            "parsed_fields": "object {field_name: value}",
            "unresolved_phrases": "array of strings",
            "confidence": "number 0..1",
        },
    },
}


def build_prompt(
    prompt_key: str,
    *,
    context: dict[str, Any],
    options: list[dict[str, Any]],
) -> str:
    """Render the universal envelope for the requested prompt key.

    Raises KeyError if prompt_key not in library.
    """
    entry = PROMPT_LIBRARY[prompt_key]
    return UNIVERSAL_ENVELOPE.format(
        task_body=entry["task"],
        context_json=json.dumps(context, ensure_ascii=False, default=str, indent=2),
        options_json=json.dumps(options, ensure_ascii=False, default=str, indent=2),
        schema_json=json.dumps(entry["schema"], ensure_ascii=False, indent=2),
    )
