"""
Phase Global: Deep hydration on school create — set modality, terminology, grading from template.
SystemMorphService runs after profile is applied in provisioning to inject config from
EducationSystemProfile (e.g. modality Hybrid → BigBlueButton; terminology from translation_map).
"""
from __future__ import annotations

from typing import Any

from apps.siteconfig.education_profile_engine import resolve_profile_for_school


def hydrate_school_from_profile(school) -> dict[str, Any]:
    """
    Deep-hydrate school.settings from the resolved EducationSystemProfile.
    Merges modality, terminology (labels_map), grading from profile.config into school.settings.
    Call after profile is applied in provisioning. Returns applied keys for logging.
    """
    if school is None:
        return {}
    profile = resolve_profile_for_school(school, requested_profile_code="", auto_create=False)
    if not profile:
        return {}
    cfg = getattr(profile, "config", None) or {}
    if not isinstance(cfg, dict):
        return {}
    settings = dict(school.settings or {})
    applied = {}
    if cfg.get("modality"):
        settings.setdefault("education_profile", {})
        if isinstance(settings["education_profile"], dict):
            settings["education_profile"]["modality"] = cfg["modality"]
            applied["modality"] = cfg["modality"]
    if cfg.get("labels_map") and isinstance(cfg["labels_map"], dict):
        settings.setdefault("education_profile", {})
        if isinstance(settings["education_profile"], dict):
            settings["education_profile"]["labels_map"] = {**settings["education_profile"].get("labels_map") or {}, **cfg["labels_map"]}
            applied["labels_map"] = True
    if cfg.get("grading_logic"):
        settings.setdefault("education_profile", {})
        if isinstance(settings["education_profile"], dict):
            settings["education_profile"]["grading_logic"] = cfg["grading_logic"]
            applied["grading_logic"] = cfg["grading_logic"]
    if applied:
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
    return applied
