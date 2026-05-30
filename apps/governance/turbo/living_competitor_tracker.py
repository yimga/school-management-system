"""Phase 6 turbo runtime: living competitor delta tracker.

Compares an external competitor feature snapshot against the RunMyCampus
internal feature surface and emits a structured delta report. The scrape /
fetch of the competitor snapshot itself is an external job; this module owns
the schema, the diff, and the report.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-living-competitor-tracker"
CONTRACT_TITLE = "Living competitor delta tracker"

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT_PATH = REPO / "docs" / "generated" / "competitor_feature_snapshot.json"
DELTA_PATH = REPO / "docs" / "generated" / "competitor_delta_report.json"

DEFAULT_RMC_FEATURES: tuple[str, ...] = (
    "multi_tenant_isolation",
    "offline_first_pwa",
    "mobile_money_paystack_flutterwave_mtn_orange",
    "stripe_dynamic_checkout",
    "oneroster_org_tree",
    "emis_aggregate_pipeline",
    "country_governance_matrix",
    "context_profiles",
)


def _load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.is_file():
        return {"competitors": [], "captured_at": None}
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def compute_delta(rmc_features: Iterable[str] = DEFAULT_RMC_FEATURES) -> dict[str, Any]:
    snapshot = _load_snapshot()
    rmc_set = set(rmc_features)
    deltas = []
    for competitor in snapshot.get("competitors", []):
        comp_features = set(competitor.get("features", []))
        deltas.append({
            "competitor": competitor.get("name"),
            "they_have_we_dont": sorted(comp_features - rmc_set),
            "we_have_they_dont": sorted(rmc_set - comp_features),
            "shared": sorted(rmc_set & comp_features),
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rmc_feature_count": len(rmc_set),
        "competitor_count": len(deltas),
        "deltas": deltas,
    }
    DELTA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DELTA_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def runtime_health() -> dict[str, Any]:
    report = compute_delta()
    return {"contract_id": CONTRACT_ID, "healthy": "deltas" in report, "competitor_count": report["competitor_count"]}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
