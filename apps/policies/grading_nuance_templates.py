"""JSON-Logic grading templates for PolicyBundle / get_effective_policy (global academic kernel)."""

from __future__ import annotations

from typing import Any

# Coefficient-weighted mean: caller supplies weighted_sum + coefficient_total (+ scale_max).
REPORT_CARD_AVG_WEIGHTED: dict[str, Any] = {
    "if": [
        {
            "and": [
                {">": [{"var": "coefficient_total"}, 0]},
                {">": [{"var": "scale_max"}, 0]},
            ]
        },
        {"/": [{"var": "weighted_sum"}, {"var": "coefficient_total"}]},
        {"var": "weighted_sum"},
    ]
}

# Pass-through when upstream already computed the average into ``value``.
REPORT_CARD_AVG_PRECOMPUTED: dict[str, Any] = {"var": "value"}

_PRESET_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "american": {
        "report_card_avg": {
            "logic_data": REPORT_CARD_AVG_WEIGHTED,
            "description": "Weighted mean across subjects (coefficients default to 1).",
        },
    },
    "british_igcse": {
        "report_card_avg": {
            "logic_data": REPORT_CARD_AVG_WEIGHTED,
            "description": "Weighted mean for IGCSE/A-Level style coefficient maps.",
        },
    },
    "francophone_bac": {
        "report_card_avg": {
            "logic_data": REPORT_CARD_AVG_WEIGHTED,
            "description": "Francophone coefficient-weighted term average (Baccalauréat-style).",
        },
    },
    "west_african_waec": {
        "report_card_avg": {
            "logic_data": REPORT_CARD_AVG_WEIGHTED,
            "description": "WAEC-style coefficient-weighted class average.",
        },
    },
    "east_asia_competitive": {
        "report_card_avg": {
            "logic_data": REPORT_CARD_AVG_PRECOMPUTED,
            "description": "Use pre-normalized average (T-score / rank pipelines).",
        },
    },
}

_DEFAULT_TEST_CONTEXTS: list[dict[str, Any]] = [
    {
        "weighted_sum": 42.0,
        "coefficient_total": 6.0,
        "scale_max": 20.0,
        "scores_by_subject": {},
        "coefficients": {},
    },
    {"value": 14.5, "scale_max": 20.0, "scores_by_subject": {}, "coefficients": {}},
]


def grading_nuance_templates_for_preset(preset_key: str) -> dict[str, dict[str, Any]]:
    """Return hook_point → {logic_data, description} for a grading preset."""
    key = (preset_key or "american").strip().lower()
    return dict(_PRESET_TEMPLATES.get(key) or _PRESET_TEMPLATES["american"])


def attach_grading_nuance_to_policy(policy: dict[str, Any], preset_key: str) -> None:
    """Merge verified JSON-Logic templates into policy['grading']['nuance_templates']."""
    from apps.siteconfig.nuance_engine import verify_nuance_safety

    templates = grading_nuance_templates_for_preset(preset_key)
    verified: dict[str, Any] = {}
    for hook_point, spec in templates.items():
        logic = spec.get("logic_data")
        if not isinstance(logic, dict):
            continue
        ok, _err = verify_nuance_safety(logic, _DEFAULT_TEST_CONTEXTS, reject_negative_fee=False)
        if not ok:
            continue
        verified[hook_point] = {
            "logic_data": logic,
            "description": str(spec.get("description") or ""),
            "preset_key": (preset_key or "american").strip().lower(),
        }
    policy.setdefault("grading", {})
    if isinstance(policy["grading"], dict):
        policy["grading"]["nuance_templates"] = verified
        policy["grading"].setdefault("preset_key", (preset_key or "american").strip().lower())


def sync_grading_nuance_from_policy(school) -> dict[str, Any]:
    """
    Upsert active CustomNuance rows from policy grading templates (idempotent).

    Used after provisioning or blueprint apply so report_card_avg honors bundle math.
    """
    from apps.policies.resolver import get_effective_policy
    from apps.siteconfig.models import CustomNuance
    from apps.siteconfig.nuance_engine import verify_nuance_safety

    if school is None:
        return {"synced": 0}
    policy = get_effective_policy(school)
    grading = policy.get("grading") if isinstance(policy.get("grading"), dict) else {}
    templates = grading.get("nuance_templates") if isinstance(grading.get("nuance_templates"), dict) else {}
    synced = 0
    for hook_point, spec in templates.items():
        if not isinstance(spec, dict):
            continue
        logic = spec.get("logic_data")
        if not isinstance(logic, dict):
            continue
        ok, _err = verify_nuance_safety(logic, _DEFAULT_TEST_CONTEXTS, reject_negative_fee=False)
        if not ok:
            continue
        CustomNuance.objects.update_or_create(
            school=school,
            hook_point=str(hook_point),
            defaults={
                "logic_data": logic,
                "is_active": True,
                "human_description": str(spec.get("description") or ""),
            },
        )
        synced += 1
    return {"synced": synced}
