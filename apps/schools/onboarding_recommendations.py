"""Explainable, deterministic, local-first tenant setup recommendations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

MANIFEST_VERSION = 3


def _bounded_int(value: Any, *, maximum: int = 1_000_000) -> int:
    try:
        return min(maximum, max(0, int(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _recommendation(
    key: str,
    label: str,
    value: Any,
    *,
    reason: str,
    confidence: str = "high",
    decision: str = "automatic",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "display_value": ", ".join(str(item) for item in value)
        if isinstance(value, list)
        else str(value),
        "reason": reason,
        "confidence": confidence,
        "decision": decision,
        "dependencies": dependencies or [],
        "editable": True,
    }


def build_onboarding_recommendations(
    *,
    country_code: str,
    education_cycles: list[str] | None = None,
    language_codes: list[str] | None = None,
    institution_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    country = str(country_code or "").strip().upper()[:2]
    cycles = [
        str(value).strip().lower() for value in (education_cycles or []) if value
    ]
    languages = [
        str(value).strip().lower() for value in (language_codes or []) if value
    ]
    profile = dict(institution_profile or {})
    capacity = _bounded_int(profile.get("student_capacity"))
    profile["student_capacity"] = capacity
    campus_count = _bounded_int(profile.get("campus_count"), maximum=10_000)
    staff_count = _bounded_int(profile.get("staff_count"))
    profile["campus_count"] = campus_count
    profile["staff_count"] = staff_count
    scope = str(profile.get("organization_scope") or "single").strip().lower()
    multi_campus = scope in {"district", "network"}
    cycle_text = " ".join(cycles)
    has_secondary = any(
        token in cycle_text for token in ("secondary", "high", "sss", "tvet")
    )
    funding = str(profile.get("funding_type") or "").strip().lower()
    lms = str(profile.get("lms_preference") or "none").strip().lower()
    operating_model = str(profile.get("operating_model") or "day").strip().lower()
    connectivity = str(profile.get("connectivity_profile") or "mixed").strip().lower()
    payment_profile = str(profile.get("payment_profile") or "basic").strip().lower()
    go_live_timeline = str(profile.get("go_live_timeline") or "exploring").strip().lower()
    migration_vendor = str(profile.get("migration_vendor") or "").strip().lower()
    migration_domains = list(dict.fromkeys(
        str(value).strip().lower()
        for value in (profile.get("migration_domains") or [])
        if str(value).strip()
    ))
    profile.update({
        "operating_model": operating_model,
        "connectivity_profile": connectivity,
        "payment_profile": payment_profile,
        "go_live_timeline": go_live_timeline,
        "migration_vendor": migration_vendor,
        "migration_domains": migration_domains,
    })

    modules = ["student-information", "attendance", "family-portal", "communications"]
    if has_secondary:
        modules += ["grading", "timetable", "examinations"]
    if funding in {"private", "mission", "charter"}:
        modules += ["fees-finance", "financial-aid"]
    if multi_campus:
        modules += ["district-governance", "cross-campus-analytics"]
    if capacity >= 1000:
        modules += ["bulk-operations", "advanced-analytics"]
    if operating_model in {"boarding", "mixed"}:
        modules += ["boarding", "student-welfare"]
    if payment_profile in {"online", "multi-channel"}:
        modules += ["payments", "reconciliation"]
    if connectivity == "limited":
        modules += ["offline-sync", "continuity-operations"]
    if migration_vendor or migration_domains:
        modules += ["guided-data-migration", "migration-reconciliation"]
    modules = list(dict.fromkeys(modules))

    enterprise_fit = multi_campus or campus_count > 1 or capacity >= 1000 or staff_count >= 150
    operations_fit = (
        operating_model in {"boarding", "mixed"}
        or payment_profile in {"online", "multi-channel"}
        or connectivity == "limited"
    )
    subscription_plan = (
        "campus-enterprise" if enterprise_fit
        else "school-pro-operations" if operations_fit
        else "school-pro"
    )

    recommendations = {
        "blueprint": "country-and-cycle matched blueprint",
        "modules": modules,
        "apps": ["offline-capture", "family-portal", "teacher-workspace"],
        "institution_profile": "multi-campus" if multi_campus else "single-campus",
        "district": "district-console" if multi_campus else "not-required",
        "lms": lms if lms not in {"", "none"} else "native-learning-workspace",
        "grading": "registry-matched grading framework" if has_secondary else "cycle-appropriate grading",
        "languages": languages or ["country-default"],
        "dashboard": "network-executive" if multi_campus else "role-based-school-operations",
        "local_first": "offline-ready edge profile",
        "subscription_plan": subscription_plan,
        "migration": {
            "vendor": migration_vendor or "not-declared",
            "domains": migration_domains,
            "mode": "guided-staged-import" if migration_vendor else "discovery-required",
        },
    }
    cards = [
        _recommendation(
            "blueprint", "Blueprint", recommendations["blueprint"],
            reason="Matched from country and education cycles.", decision="confirm",
            dependencies=["country", "education-cycles"],
        ),
        _recommendation(
            "modules", "Modules", modules,
            reason="The smallest day-one module set for the declared school profile.",
            decision="confirm",
        ),
        _recommendation(
            "lms", "Learning platform", recommendations["lms"],
            reason="Uses the stated preference, with the native offline-safe fallback.",
        ),
        _recommendation(
            "grading", "Grading", recommendations["grading"],
            reason="Derived from cycles; the active regional registry is authoritative.",
            decision="confirm", dependencies=["grading-registry"],
        ),
        _recommendation(
            "dashboard", "Dashboard", recommendations["dashboard"],
            reason="Matched to single-school or network operating scope.",
        ),
        _recommendation(
            "district", "District tools", recommendations["district"],
            reason="Enabled only for declared district or network operations.",
        ),
        _recommendation(
            "local_first", "Offline profile", recommendations["local_first"],
            reason="Local capture and sync-safe workflows are the platform baseline.",
        ),
        _recommendation(
            "subscription_plan", "Plan fit", subscription_plan,
            reason="Sized from campuses, enrollment, staff and day-to-day operating needs.",
            decision="confirm-with-operator",
            dependencies=["plan-catalog", "operator-confirmation"],
        ),
        _recommendation(
            "migration", "Data migration", recommendations["migration"],
            reason=(
                "Stages the declared source and record domains for validated import, "
                "reconciliation and rollback after provisioning."
            ),
            decision="confirm",
            dependencies=["migration-readiness", "tenant-owner-confirmation"],
        ),
    ]
    source_payload = {
        "country_code": country, "education_cycles": cycles,
        "language_codes": languages, "institution_profile": profile,
    }
    signals = (
        (bool(country), "country registry"), (bool(cycles), "education cycles"),
        (bool(funding), "funding model"), (bool(capacity), "expected capacity"),
        (bool(scope), "organization scope"),
        (lms not in {"", "none"}, "LMS preference"),
        (bool(campus_count), "campus count"),
        (bool(staff_count), "staff count"),
        (operating_model != "day", "operating model"),
        (connectivity != "mixed", "connectivity profile"),
        (payment_profile != "basic", "payment profile"),
        (bool(migration_vendor), "migration vendor"),
        (bool(migration_domains), "migration domains"),
    )
    reasons = [label for present, label in signals if present]
    required_signals = (
        (bool(country), "country"), (bool(cycles), "education cycles"),
        (bool(funding), "funding model"), (bool(capacity), "expected capacity"),
    )
    missing_inputs = [label for present, label in required_signals if not present]
    return {
        "version": MANIFEST_VERSION,
        "fingerprint": _fingerprint(source_payload),
        "country_code": country,
        "profile": profile,
        "recommendations": recommendations,
        "recommendation_cards": cards,
        "reason_labels": reasons,
        "missing_inputs": missing_inputs,
        "confidence": (
            "high" if len(missing_inputs) <= 1
            else "medium" if len(missing_inputs) <= 2 else "low"
        ),
        "source": "signup-intent",
        "offline_safe": True,
        "subscription": {
            "recommended_slug": subscription_plan,
            "binding": "recommendation-only",
            "requires_confirmation": True,
            "auto_entitlement": False,
        },
    }


def ensure_school_recommendations(school, *, save: bool = True) -> dict[str, Any]:
    """Create or refresh a manifest without overwriting tenant choices."""
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
        institution_profile.setdefault(
            "migration_domains", migration_intent.get("data_domains") or []
        )
    manifest = build_onboarding_recommendations(
        country_code=getattr(school, "country_code", ""),
        education_cycles=cycles,
        language_codes=languages,
        institution_profile=institution_profile,
    )
    current = settings.get("recommendation_manifest")
    if (
        isinstance(current, dict)
        and current.get("version") == MANIFEST_VERSION
        and current.get("fingerprint") == manifest["fingerprint"]
    ):
        return current
    if save and getattr(school, "pk", None):
        settings["recommendation_manifest"] = manifest
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
    return manifest
