"""Phase 6 turbo runtime: 60-second zero-form tenant bootstrap.

Given a country ISO code, derives a complete tenant pre-config from the matrix
shard so the operator can click "confirm" once. The function is fully
deterministic and offline-first; GeoIP resolution is the caller's responsibility
(the existing `apps/siteconfig/geoip_country_lookup.py` is the usual upstream).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-zero-form-bootstrap"
CONTRACT_TITLE = "Zero-form tenant bootstrap"

REPO = Path(__file__).resolve().parents[3]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"


def bootstrap_from_iso(country_iso: str) -> dict[str, Any]:
    path = SHARD_DIR / f"{country_iso.upper()}.json"
    if not path.is_file():
        return {"bootstrap_status": "no_matrix_shard", "country_iso": country_iso.upper()}
    row = json.loads(path.read_text(encoding="utf-8"))
    rm = row.get("regulatory_matrix") or {}
    return {
        "bootstrap_status": "ready_for_confirm",
        "country_iso": row.get("iso_alpha2"),
        "sector_default": "education",
        "governance_archetype": row.get("governance_archetype"),
        "recommended_operating_mode": row.get("recommended_operating_mode", "standalone"),
        "official_languages": [lang.get("iso639") for lang in (row.get("official_languages") or []) if isinstance(lang, dict)],
        "local_terminology": row.get("local_terminology"),
        "moe_preset_key": (row.get("deep_layers") or {}).get("moe_preset"),
        "payment_currency_hint": row.get("currency"),
        "timezone_hint": row.get("timezone"),
        "privacy_consent_banner": rm.get("student_privacy_regimes"),
        "accessibility_baseline": (rm.get("accessibility_statute") or {}).get("platform_baseline"),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def runtime_health() -> dict[str, Any]:
    sample = next(SHARD_DIR.glob("*.json"), None) if SHARD_DIR.is_dir() else None
    if sample is None:
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shards"}
    result = bootstrap_from_iso(sample.stem)
    return {"contract_id": CONTRACT_ID, "healthy": result.get("bootstrap_status") == "ready_for_confirm", "sample": sample.stem}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
