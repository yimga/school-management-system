"""Phase 6 turbo runtime: TLA+ spec registry.

Owns the catalog of TLA+ specs that model-check governance invariants. The
specs themselves live at docs/formal/*.tla; this module verifies they exist and
exposes the list to CI runners that drive TLC.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-formal-verification-tla"
CONTRACT_TITLE = "TLA+ specs for governance invariants"

REPO = Path(__file__).resolve().parents[3]
SPEC_DIR = REPO / "docs" / "formal"

REQUIRED_SPECS: tuple[str, ...] = (
    "TenantIsolation.tla",
    "RoleEscalation.tla",
    "TranscriptForgery.tla",
    "InheritMapIdempotence.tla",
)


def list_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "path": str((SPEC_DIR / name).relative_to(REPO)).replace("\\", "/"),
            "present": (SPEC_DIR / name).is_file(),
        }
        for name in REQUIRED_SPECS
    ]


def runtime_health() -> dict[str, Any]:
    specs = list_specs()
    missing = [s["name"] for s in specs if not s["present"]]
    return {"contract_id": CONTRACT_ID, "healthy": not missing, "missing": missing, "spec_count": len(specs)}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
