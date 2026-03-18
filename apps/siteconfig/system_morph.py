"""
Phase Global: Deep hydration on school create — set modality, terminology, grading from template.
SystemMorphService runs after profile is applied in provisioning to inject config from
EducationSystemProfile (e.g. modality Hybrid → BigBlueButton; terminology from translation_map).
§2.4: Typed exception tuple for policy cache invalidation (no broad except).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.siteconfig.education_profile_engine import resolve_profile_for_school

logger = logging.getLogger(__name__)

# §2.4: Typed tuple for invalidate_policy_cache (optional post-save; fail soft).
_SYSTEM_MORPH_POLICY_CACHE_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


def hydrate_school_from_profile(school) -> dict[str, Any]:
    """
    Deep-hydrate school.settings from the resolved EducationSystemProfile.
    Merges modality, terminology (labels_map), grading from profile.config into school.settings.
    Call after profile is applied in provisioning. Returns applied keys for logging.
    """
    if school is None:
        return {}
    profile = resolve_profile_for_school(
        school, requested_profile_code="", auto_create=False
    )
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
            existing_map = settings["education_profile"].get("labels_map") or {}
            settings["education_profile"]["labels_map"] = {
                **existing_map,
                **cfg["labels_map"],
            }
            applied["labels_map"] = True
    if cfg.get("grading_logic"):
        settings.setdefault("education_profile", {})
        if isinstance(settings["education_profile"], dict):
            settings["education_profile"]["grading_logic"] = cfg["grading_logic"]
            applied["grading_logic"] = cfg["grading_logic"]
    if applied:
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except _SYSTEM_MORPH_POLICY_CACHE_ERRORS as e:
            log_exception_with_context(
                "hydrate_school_from_profile: invalidate_policy_cache failed",
                school_id=getattr(school, "id", None),
                extra={"applied_keys": list(applied.keys())},
            )
            logger.debug(
                "invalidate_policy_cache skip for school: %s", e, exc_info=True
            )
    return applied
