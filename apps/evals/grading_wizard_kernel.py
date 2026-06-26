"""Polymorphic grading wizard → GradingScale + tenant grading policy."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _grading_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    return dict((getattr(school, "settings", None) or {}).get("grading") or {})


def _save_grading(school: Any | None, blob: dict[str, Any]) -> None:
    if school is None:
        return
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["grading"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def _normalize_multi(payload: dict[str, Any]) -> list[Any]:
    raw = payload.get("value") or payload.get("values") or payload.get("tracks") or []
    if isinstance(raw, list):
        return raw
    return [raw] if raw else []


_SCALE_TYPE_MAP = {
    "gpa_4": "gpa_4_0",
    "gpa_5": "gpa_4_0",
    "percentage": "percentage",
    "letter": "letter_a_e",
    "competency": "letter_a_e",
    "points_100": "percentage",
    "points_1000": "percentage",
    "numeric_0_20": "numeric_0_20",
    "numeric_1_5": "numeric_1_5",
    # Both the raw wizard token ("1-5") and the hyphen-normalized form ("1_5") that
    # _normalize_scale_type produces (it does .replace("-", "_")) must resolve.
    "1-5": "numeric_1_5",
    "1_5": "numeric_1_5",
    "post_soviet": "numeric_1_5",
    "waec": "waec_letter",
    "waec_letter": "waec_letter",
    "pass_fail": "pass_fail",
    "passfail": "pass_fail",
    "binary": "pass_fail",
    "qualitative": "qualitative_pd",
    "qualitative_pd": "qualitative_pd",
    "descriptive": "qualitative_pd",
    "t_score": "standard_score_t",
    "t-score": "standard_score_t",
    "standard_score_t": "standard_score_t",
    "hensachi": "standard_score_t",
}


def apply_curriculum_tracks(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    tracks = [str(t) for t in _normalize_multi(payload)]
    blob = _grading_blob(school)
    blob["curriculum_tracks"] = tracks
    _save_grading(school, blob)
    return {"ok": True, "curriculum_tracks": tracks}


def apply_assessment_metrics(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False, "error": "missing_school"}

    from apps.evals.models import GradingScale

    scale_key = (payload.get("grading_scale") or "percentage").strip()
    scale_type = _SCALE_TYPE_MAP.get(scale_key, "percentage")
    pass_threshold = payload.get("pass_threshold")
    rubric_levels = payload.get("rubric_levels")

    config: dict[str, Any] = {}
    if pass_threshold is not None:
        try:
            config["pass_threshold"] = float(Decimal(str(pass_threshold)))
        except (InvalidOperation, ValueError):
            config["pass_threshold"] = pass_threshold
    if rubric_levels is not None:
        config["rubric_levels"] = rubric_levels
    formula = PRESET_GRADING_FORMULAS.get(scale_key.replace("-", "_"))
    if formula:
        config["formula_text"] = formula

    name = f"Wizard default ({scale_key})"
    scale, _created = GradingScale.objects.update_or_create(
        school=school,
        code="wizard-default",
        defaults={
            "name": name,
            "scale_type": scale_type,
            "config": config,
            "is_default": True,
            "is_active": True,
        },
    )
    if scale.name != name or scale.config != config:
        scale.name = name
        merged = dict(scale.config or {})
        merged.update(config)
        scale.config = merged
        scale.scale_type = scale_type
        scale.is_default = True
        scale.is_active = True
        scale.save(update_fields=["name", "scale_type", "config", "is_default", "is_active"])

    GradingScale.objects.filter(school=school, is_default=True).exclude(pk=scale.pk).update(
        is_default=False
    )

    blob = _grading_blob(school)
    blob["assessment_metrics"] = {
        "grading_scale": scale_key,
        "pass_threshold": config.get("pass_threshold"),
        "rubric_levels": rubric_levels,
        "grading_scale_id": scale.pk,
    }
    _save_grading(school, blob)
    return {"ok": True, "grading_scale_id": scale.pk}


def apply_subject_mapping(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    mapping = payload.get("mapping") or payload.get("value") or payload
    if not isinstance(mapping, dict):
        mapping = {"raw": mapping}
    blob = _grading_blob(school)
    blob["subject_mapping"] = mapping
    _save_grading(school, blob)
    return {"ok": True, "subject_mapping": mapping}


def apply_transcript_template(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    template = payload.get("value") or payload.get("template")
    blob = _grading_blob(school)
    blob["transcript_template"] = template
    _save_grading(school, blob)
    return {"ok": True, "transcript_template": template}
