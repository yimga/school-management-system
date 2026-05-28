"""ExperienceTemplate AI recommender — gateway-routed with deterministic fallback.

ALL AI calls route through ``services.ai_helpers`` per the architectural
boundary scanner. Never imports ``services.ai_gateway`` directly.

The recommender returns a typed ``TemplateRecommendation`` regardless of which
path (AI / rules) produced it. Registry membership is validated before any
recommendation is returned — the recommender NEVER fabricates a template key.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps.brand_experience.experience_templates import (
    OVERLAYS,
    ExperienceTemplateOverlay,
    get_overlay,
    list_overlays,
)


@dataclass(frozen=True)
class TemplateRecommendation:
    primary: str
    why: str
    required_modules: tuple[str, ...]
    missing_setup: tuple[str, ...]
    preview_url: str
    risks: tuple[str, ...]
    alternatives: tuple[str, ...]
    confidence: float
    source: str  # "ai" or "rules"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, tuple):
                d[k] = list(v)
        return d


def _gather_signals(school: Any, user: Any) -> dict[str, Any]:
    """Compose recommender input from existing first-class signals.

    Reads from school.settings + school first-class fields (Wave 10 made
    primary_language first-class; country comes from CountryRegistry resolution
    that the request middleware already attached).
    """
    settings_payload = getattr(school, "settings", None) or {}
    role = ""
    if user is not None and hasattr(user, "role"):
        role = str(getattr(user, "role", "") or "")
    return {
        "country": (getattr(school, "country_code", "") or settings_payload.get("country", "") or "").upper(),
        "region": settings_payload.get("region", "") or "",
        "primary_language": getattr(school, "primary_language", "") or settings_payload.get("primary_language", "en"),
        "modules_enabled": list(settings_payload.get("modules_enabled", []) or []),
        "connectivity_profile": settings_payload.get("connectivity_profile", "standard"),
        "payment_maturity": settings_payload.get("payment_maturity", "standard"),
        "migration_status": settings_payload.get("migration_status", "none"),
        "parent_engagement_signal": settings_payload.get("parent_engagement_signal", "standard"),
        "role": role,
    }


def _filter_candidates(
    signals: dict[str, Any], *, tenant_safe_only: bool = True
) -> list[ExperienceTemplateOverlay]:
    cc = signals.get("country", "")
    lang = signals.get("primary_language", "")
    candidates = []
    for o in OVERLAYS:
        if tenant_safe_only and o.is_operator_only():
            continue
        if "*" not in o.supported_countries and cc and cc not in o.supported_countries:
            continue
        if "*" not in o.supported_languages and lang and lang not in o.supported_languages:
            continue
        candidates.append(o)
    return candidates


def _score_candidate(o: ExperienceTemplateOverlay, signals: dict[str, Any]) -> float:
    score = 0.5
    if signals.get("connectivity_profile") == "low" and o.mobile_level == "mobile-first":
        score += 0.2
    if signals.get("country") and signals["country"] in o.supported_countries:
        score += 0.15
    if signals.get("primary_language") and signals["primary_language"] in o.supported_languages:
        score += 0.1
    role = (signals.get("role") or "").upper()
    role_to_category = {
        "PARENT": "parent",
        "STUDENT": "student",
        "TEACHER": "teacher",
        "ADMIN": "tenant-admin",
        "PROPRIETOR": "tenant-admin",
    }
    if role in role_to_category and o.category == role_to_category[role]:
        score += 0.25
    return min(score, 1.0)


def _rules_recommend(signals: dict[str, Any]) -> TemplateRecommendation:
    candidates = _filter_candidates(signals, tenant_safe_only=True)
    if not candidates:
        candidates = [o for o in OVERLAYS if not o.is_operator_only()]
    scored = sorted(
        ((o, _score_candidate(o, signals)) for o in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    primary, primary_score = scored[0]
    alt_keys = tuple(o.key for o, _ in scored[1:3])
    risks: list[str] = []
    if signals.get("connectivity_profile") == "low" and primary.mobile_level != "mobile-first":
        risks.append("low_connectivity_school_using_data_rich_template")
    missing_setup: list[str] = []
    if not signals.get("country"):
        missing_setup.append("country_not_set")
    if not signals.get("modules_enabled"):
        missing_setup.append("modules_not_configured")
    return TemplateRecommendation(
        primary=primary.key,
        why=f"Best match for category {primary.category} given country {signals.get('country', '?')} and role {signals.get('role', '?')}.",
        required_modules=tuple(),
        missing_setup=tuple(missing_setup),
        preview_url=f"/configuration/templates/{primary.key}/preview/",
        risks=tuple(risks),
        alternatives=alt_keys,
        confidence=primary_score,
        source="rules",
    )


def recommend_for_school(
    school: Any,
    *,
    user: Any = None,
    request: Any = None,
    use_ai: bool = True,
) -> TemplateRecommendation:
    """Return a registry-validated TemplateRecommendation.

    AI path routes through services.ai_helpers.invoke_with_request and falls
    back to rules if the gateway is unreachable, returns nothing useful, or
    proposes a template_key that is not in the registry.
    """
    signals = _gather_signals(school, user)
    if not use_ai:
        return _rules_recommend(signals)
    try:
        from services import ai_helpers  # lazy import keeps verifier soft-pass clean
    except ImportError:
        return _rules_recommend(signals)
    try:
        prompt = (
            "Recommend the best ExperienceTemplate for this school based on these signals. "
            "Return a JSON object with keys: primary (string), why (string), "
            "alternatives (list[str]), risks (list[str]), confidence (0..1). "
            "Choose from this registry only.\n"
            f"Signals: {signals}\n"
            f"Registry keys (tenant-safe only): "
            f"{[o.key for o in OVERLAYS if not o.is_operator_only()]}"
        )
        payload = ai_helpers.invoke_with_request(
            request,
            prompt=prompt,
            task_type="EXPERIENCE_TEMPLATE_RECOMMENDER",
            options={"json_mode": True, "max_output_tokens": 300},
        )
    except Exception:
        return _rules_recommend(signals)
    if not isinstance(payload, dict):
        return _rules_recommend(signals)
    proposed_key = str(payload.get("primary") or "").strip()
    if not proposed_key or get_overlay(proposed_key) is None:
        return _rules_recommend(signals)
    candidate = get_overlay(proposed_key)
    if candidate.is_operator_only():
        return _rules_recommend(signals)
    valid_alts = tuple(
        k for k in (payload.get("alternatives") or [])
        if isinstance(k, str) and get_overlay(k) is not None and not get_overlay(k).is_operator_only()
    )[:2]
    return TemplateRecommendation(
        primary=proposed_key,
        why=str(payload.get("why") or "AI-routed recommendation."),
        required_modules=tuple(),
        missing_setup=tuple(),
        preview_url=f"/configuration/templates/{proposed_key}/preview/",
        risks=tuple(str(r) for r in (payload.get("risks") or []) if isinstance(r, str))[:5],
        alternatives=valid_alts,
        confidence=float(payload.get("confidence") or 0.5),
        source="ai",
    )


def recommend_local_first_for_country(country_code: str) -> list[dict]:
    """Return all local-first templates targeting the given country, ordered."""
    cc = (country_code or "").strip().upper()
    if not cc:
        return []
    return list_overlays(country=cc, category="local-first")


def recommendation_audit_entry(rec: TemplateRecommendation, signals: dict[str, Any]) -> dict[str, Any]:
    """Build a PII-safe audit entry for the recommendation event.

    The audit entry intentionally omits raw user/school identifiers — only
    hashed/categorical signals make it into the log.
    """
    return {
        "primary": rec.primary,
        "confidence": rec.confidence,
        "source": rec.source,
        "country": signals.get("country") or "",
        "role_category": (signals.get("role") or "").upper() or "",
        "connectivity_profile": signals.get("connectivity_profile") or "",
    }
