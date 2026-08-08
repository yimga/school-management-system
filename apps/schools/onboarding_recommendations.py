"""Deterministic local-first recommendations derived from tenant intent."""
from __future__ import annotations
from typing import Any

MANIFEST_VERSION = 1


def build_onboarding_recommendations(*, country_code: str, education_cycles: list[str] | None = None, language_codes: list[str] | None = None, institution_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    cycles = [str(v).strip().lower() for v in (education_cycles or []) if v]
    languages = [str(v).strip().lower() for v in (language_codes or []) if v]
    profile = dict(institution_profile or {})
    capacity = max(0, int(profile.get("student_capacity") or 0))
    multi_campus = profile.get("organization_scope") in {"district", "network"}
    has_secondary = any(t in " ".join(cycles) for t in ("secondary", "high", "sss", "tvet"))
    modules = ["student-information", "attendance", "family-portal", "communications"]
    if has_secondary:
        modules += ["grading", "timetable", "examinations"]
    if profile.get("funding_type") in {"private", "mission", "charter"}:
        modules += ["fees-finance", "financial-aid"]
    if multi_campus:
        modules += ["district-governance", "cross-campus-analytics"]
    if capacity >= 1000:
        modules += ["bulk-operations", "advanced-analytics"]
    lms = str(profile.get("lms_preference") or "none").strip().lower()
    recommendations = {
        "blueprint": "country-and-cycle matched blueprint",
        "modules": list(dict.fromkeys(modules)),
        "apps": ["offline-capture", "family-portal", "teacher-workspace"],
        "institution_profile": "multi-campus" if multi_campus else "single-campus",
        "district": "district-console" if multi_campus else "not-required",
        "lms": lms if lms not in {"", "none"} else "native-learning-workspace",
        "grading": "registry-matched grading framework" if has_secondary else "cycle-appropriate grading",
        "languages": languages or ["country-default"],
        "dashboard": "network-executive" if multi_campus else "role-based-school-operations",
        "local_first": "offline-ready edge profile",
    }
    reasons = ["country registry", "education cycles"]
    for key, label in (("funding_type", "funding model"), ("student_capacity", "expected capacity"), ("organization_scope", "organization scope"), ("lms_preference", "LMS preference")):
        if profile.get(key):
            reasons.append(label)
    return {"version": MANIFEST_VERSION, "country_code": str(country_code or "").strip().upper()[:2], "profile": profile, "recommendations": recommendations, "reason_labels": reasons, "source": "signup-intent", "offline_safe": True}


def ensure_school_recommendations(school, *, save: bool = True) -> dict[str, Any]:
    """Create a manifest for legacy tenants without overwriting their choices."""
    settings = dict(getattr(school, "settings", None) or {})
    intent = dict(settings.get("onboarding_intent") or {})
    current = settings.get("recommendation_manifest")
    if isinstance(current, dict) and current.get("version") == MANIFEST_VERSION:
        return current
    cycles = list(intent.get("education_cycles") or [])
    if not cycles and getattr(school, "pk", None):
        cycles = list(school.education_system_types.values_list("code", flat=True))
    languages = list(intent.get("language_codes") or [])
    primary = str(getattr(school, "primary_language", "") or "").strip()
    if not languages and primary:
        languages = [primary]
    manifest = build_onboarding_recommendations(country_code=getattr(school, "country_code", ""), education_cycles=cycles, language_codes=languages, institution_profile=intent.get("institution_profile") or {})
    settings["recommendation_manifest"] = manifest
    school.settings = settings
    if save and getattr(school, "pk", None):
        school.save(update_fields=["settings", "updated_at"])
    return manifest
