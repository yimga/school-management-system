"""Local-first grading provisioning — the missing link in studio academic seeding.

At school provision the country pack already drives the academic year, terms, subjects,
and class structure, but the per-school ``GradingScale`` row was NEVER created — a new
school landed with the country's grading scale computed into ``school.settings`` yet no
GradingScale model row, so the dashboard read "no grading scale configured" until an
admin manually ran the grading wizard and blind-picked from a generic list.

``ensure_local_grading_scale`` closes that gap: it resolves the school's COUNTRY grading
scale (Education-DNA preset → scale type), creates a per-school default ``GradingScale``
with country-appropriate bands (from ``GRADING_SCALE_BANDS``) + a passing threshold, and
seeds a matching school-wide default ``AssessmentWeights`` so letter/GPA computation uses
the right scale from day one. Idempotent, tenant-scoped, and it NEVER overrides a scale an
admin already chose (a wizard-default or any existing default scale wins).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Education-DNA preset key (apps.governance.academic_pack_bridge.resolve_grading_preset_key)
# → GradingScale.ScaleType. Keeps the country→scale decision in one auditable place.
_PRESET_TO_SCALE_TYPE: dict[str, str] = {
    "francophone_bac": "numeric_0_20",       # France / Francophone Africa — 0–20
    "cameroon_0_20": "numeric_0_20",
    "west_african_waec": "percentage",       # WAEC raw scores are percentages
    "east_asia_competitive": "percentage",   # CN/KR/JP — 0–100
    "american": "gpa_4_0",                   # US — 4.0 GPA
    "british_igcse": "letter_a_e",           # UK/Commonwealth — letter grades
    "generic": "percentage",
}

_LOCAL_DEFAULT_CODE = "local-default"
_VALID_SCALE_TYPES = {"numeric_0_20", "letter_a_e", "gpa_4_0", "percentage"}


def _scale_type_from_cascade(school) -> str:
    """Honor an explicit ``default_grading_scale`` cascade value when it maps to a
    known scale type (operator override wins over country derivation). Else ""."""
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings

        raw = (getattr(get_effective_site_settings(school=school), "default_grading_scale", "") or "")
    except Exception:  # noqa: BLE001 — cascade is best-effort
        return ""
    val = str(raw).strip().lower().replace("-", "_")
    if val in _VALID_SCALE_TYPES:
        return val
    # Map the wizard's option keys (gpa_4 / letter / points_100 / …) too.
    try:
        from apps.evals.grading_wizard_kernel import _SCALE_TYPE_MAP

        return _SCALE_TYPE_MAP.get(val, "")
    except Exception:  # noqa: BLE001
        return ""


def resolve_local_scale_type(school) -> str:
    """The grading scale a school SHOULD use, local-first.

    Order: explicit ``default_grading_scale`` cascade → country Education-DNA preset →
    "percentage" (the most internationally neutral fallback). Always a valid ScaleType.
    """
    cascade = _scale_type_from_cascade(school)
    if cascade in _VALID_SCALE_TYPES:
        return cascade
    country_code = (getattr(school, "country_code", "") or "").strip()
    if country_code:
        try:
            from apps.governance.academic_pack_bridge import resolve_grading_preset_key

            preset = resolve_grading_preset_key(country_code)
            mapped = _PRESET_TO_SCALE_TYPE.get(preset)
            if mapped in _VALID_SCALE_TYPES:
                return mapped
        except Exception as exc:  # noqa: BLE001 — fall through to neutral default
            logger.debug("resolve_local_scale_type preset failed cc=%s err=%s", country_code, exc)
    return "percentage"


def _scale_config(scale_type: str) -> dict[str, Any]:
    """Country-appropriate band config + passing threshold for a scale type."""
    from apps.evals.models import default_bands_for_scale

    bands = default_bands_for_scale(scale_type)
    config: dict[str, Any] = {
        "score_scale": int(bands.get("score_scale", 20)),
        "pass_threshold": float(bands.get("d", 0)),  # lowest passing band (D)
        "grade_thresholds": {
            "A": float(bands.get("a", 0)),
            "B": float(bands.get("b", 0)),
            "C": float(bands.get("c", 0)),
            "D": float(bands.get("d", 0)),
            "E": float(bands.get("e", 0)),
        },
    }
    try:
        from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS

        formula = PRESET_GRADING_FORMULAS.get(scale_type)
        if formula:
            config["formula_text"] = formula
    except Exception:  # noqa: BLE001 — formula is optional decoration
        pass
    return config


def ensure_local_grading_scale(school, *, academic_year=None) -> dict[str, Any]:
    """Idempotently seed a per-school default ``GradingScale`` (+ matching default
    ``AssessmentWeights``) from the school's country, unless a default scale already exists.

    Returns a summary dict; never raises (logs + returns {"ok": False, ...} on failure).
    """
    if school is None or getattr(school, "pk", None) is None:
        return {"ok": False, "error": "missing_school"}

    try:
        from apps.evals.models import AssessmentWeights, GradingScale

        # Respect an existing choice (wizard-default or any admin-set default scale).
        if GradingScale.objects.filter(school=school, is_default=True).exists():
            return {"ok": True, "skipped": "default_scale_exists"}

        scale_type = resolve_local_scale_type(school)
        config = _scale_config(scale_type)
        country_code = (getattr(school, "country_code", "") or "").strip().upper()
        name = f"{country_code or 'Local'} grading scale".strip()

        scale, created = GradingScale.objects.get_or_create(
            school=school,
            code=_LOCAL_DEFAULT_CODE,
            defaults={
                "name": name,
                "scale_type": scale_type,
                "config": config,
                "is_default": True,
                "is_active": True,
            },
        )
        if not created:
            # Backfill an existing local-default row that predates this seeder.
            scale.scale_type = scale_type
            scale.config = config
            scale.is_default = True
            scale.is_active = True
            scale.save(update_fields=["scale_type", "config", "is_default", "is_active"])
        # Single default per school.
        GradingScale.objects.filter(school=school, is_default=True).exclude(pk=scale.pk).update(
            is_default=False
        )

        # Seed a school-wide default AssessmentWeights so grade math uses this scale
        # (the Wave-4 pre_save aligns the letter thresholds to the scale on create).
        weights_created = False
        if academic_year is not None:
            _, weights_created = AssessmentWeights.objects.get_or_create(
                school=school,
                academic_year=academic_year,
                term=None,
                classroom=None,
                defaults={"grading_scale": scale_type},
            )
        return {
            "ok": True,
            "grading_scale_id": scale.pk,
            "scale_type": scale_type,
            "created": created,
            "assessment_weights_created": weights_created,
        }
    except Exception as exc:  # noqa: BLE001 — provisioning step must never break the flow
        logger.warning(
            "ensure_local_grading_scale failed school_id=%s err=%s",
            getattr(school, "pk", None),
            exc,
        )
        return {"ok": False, "error": str(exc)}
