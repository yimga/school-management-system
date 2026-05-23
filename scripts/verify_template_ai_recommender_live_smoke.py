"""Wave D — AI recommender live-smoke verifier.

Probes the AI recommender end-to-end. Honest reporting:
  * If gateway is reachable + responds with a registry-valid key →
    TEMPLATE_AI_RECOMMENDER_LIVE_PASS (source=ai)
  * If gateway unreachable OR responds with junk → fallback rules path is
    exercised; verifier reports TEMPLATE_AI_RECOMMENDER_FALLBACK_PASS
    (source=rules, external_pending)
  * On any other failure → exit 1

Designed to be run from CI and from Lane 2 operator evidence collection.
Returns useful detail to docs/generated/template_ai_recommender_live_smoke.json
so operators can show evidence when LiteLLM is wired on Render.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _fake_school():
    """Minimal fake school surface for the recommender."""

    class _S:
        country_code = "CM"
        primary_language = "en"
        settings = {
            "country": "CM",
            "region": "",
            "primary_language": "en",
            "modules_enabled": ["academics", "finance"],
            "connectivity_profile": "low",
            "payment_maturity": "standard",
            "migration_status": "none",
            "parent_engagement_signal": "standard",
        }

    return _S()


def _fake_user():
    class _U:
        role = "ADMIN"
        is_authenticated = True
        pk = 1

    return _U()


def main() -> int:
    _bootstrap()
    from apps.brand_experience import experience_templates as et
    from apps.brand_experience.template_ai_recommender import (
        recommend_for_school,
        recommendation_audit_entry,
    )

    report: dict = {
        "status": "unknown",
        "source": "",
        "primary": "",
        "confidence": 0.0,
        "alternatives": [],
        "risks": [],
        "registry_membership_validated": False,
        "registry_template_count": len(et.OVERLAYS),
        "external_pending": False,
        "details": "",
    }

    try:
        rec = recommend_for_school(_fake_school(), user=_fake_user(), request=None, use_ai=True)
    except Exception as exc:
        report["status"] = "FAIL"
        report["details"] = f"recommender raised: {exc}"
        _persist(report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    report["source"] = rec.source
    report["primary"] = rec.primary
    report["confidence"] = rec.confidence
    report["alternatives"] = list(rec.alternatives)
    report["risks"] = list(rec.risks)

    overlay = et.get_overlay(rec.primary)
    if overlay is None:
        report["status"] = "FAIL"
        report["details"] = f"recommender returned key '{rec.primary}' which is NOT in registry"
        _persist(report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    if overlay.is_operator_only():
        report["status"] = "FAIL"
        report["details"] = f"recommender leaked operator-only template '{rec.primary}' to tenant"
        _persist(report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    report["registry_membership_validated"] = True
    audit_entry = recommendation_audit_entry(rec, {"country": "CM", "role": "ADMIN", "connectivity_profile": "low"})
    report["audit_entry_pii_safe"] = "country" in audit_entry and "school_slug" not in audit_entry

    if rec.source == "ai":
        report["status"] = "TEMPLATE_AI_RECOMMENDER_LIVE_PASS"
        report["details"] = "AI gateway returned a registry-valid recommendation."
    else:
        report["status"] = "TEMPLATE_AI_RECOMMENDER_FALLBACK_PASS"
        report["external_pending"] = True
        report["details"] = (
            "Gateway absent or returned no usable payload — rules-path fallback validated. "
            "To upgrade to LIVE: configure LITELLM_* env vars on Render + RMC_PRODUCT_MCP_ENABLED=1, "
            "then re-run this verifier."
        )

    _persist(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _persist(report: dict) -> None:
    here = Path(__file__).resolve().parent
    out = here.parent / "docs" / "generated" / "template_ai_recommender_live_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
