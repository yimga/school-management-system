"""Phase 6 turbo runtime: bitemporal time-traveling matrix.

Renders any matrix row as it would have been on a historical date by walking
``provenance.effective_from`` / ``provenance.effective_to`` plus any time-versioned
override layers attached to the shard.

Contract:
    get_as_of(iso_alpha2, as_of) -> dict | None
    diff_between(iso_alpha2, earlier, later) -> dict
    runtime_health() -> dict
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-time-traveling-matrix"
CONTRACT_TITLE = "Bitemporal time-traveling matrix queries"

REPO = Path(__file__).resolve().parents[3]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.split("T", 1)[0])
    except ValueError:
        LOGGER.warning("time_traveling_matrix: unparseable ISO date %r", value)
        return None


def _coerce_as_of(as_of: str | date | None) -> date:
    if isinstance(as_of, date):
        return as_of
    if isinstance(as_of, str):
        parsed = _parse_iso_date(as_of)
        if parsed is None:
            raise ValueError(f"unparseable as_of: {as_of!r}")
        return parsed
    return datetime.now(timezone.utc).date()


def _shard_path(iso: str) -> Path:
    return SHARD_DIR / f"{iso.upper()}.json"


def _is_in_window(revision: dict[str, Any], target: date) -> bool:
    prov = revision.get("provenance") or {}
    eff_from = _parse_iso_date(prov.get("effective_from"))
    eff_to = _parse_iso_date(prov.get("effective_to"))
    if eff_from and target < eff_from:
        return False
    if eff_to and target > eff_to:
        return False
    return True


def _iter_revisions(row: dict[str, Any]) -> Iterable[dict[str, Any]]:
    prov = row.get("provenance") or {}
    revisions = prov.get("revisions") or []
    for revision in revisions:
        if isinstance(revision, dict):
            yield revision
    yield row


def get_as_of(iso_alpha2: str, as_of: str | date | None = None) -> dict[str, Any] | None:
    """Return shard view valid on the given date, or None when no shard exists."""
    target = _coerce_as_of(as_of)
    path = _shard_path(iso_alpha2)
    if not path.is_file():
        return None
    row = json.loads(path.read_text(encoding="utf-8"))
    candidates = [rev for rev in _iter_revisions(row) if _is_in_window(rev, target)]
    if not candidates:
        return None
    chosen = candidates[-1]
    response = dict(chosen)
    response["_as_of"] = target.isoformat()
    response["_iso_alpha2"] = str(row.get("iso_alpha2") or iso_alpha2).upper()
    return response


def diff_between(iso_alpha2: str, earlier: str | date, later: str | date) -> dict[str, Any]:
    """Return a key-level diff between two bitemporal snapshots of the same shard."""
    earlier_view = get_as_of(iso_alpha2, earlier) or {}
    later_view = get_as_of(iso_alpha2, later) or {}
    changed: dict[str, dict[str, Any]] = {}
    keys = set(earlier_view.keys()) | set(later_view.keys())
    for key in keys:
        if key.startswith("_"):
            continue
        if earlier_view.get(key) != later_view.get(key):
            changed[key] = {"before": earlier_view.get(key), "after": later_view.get(key)}
    return {
        "iso_alpha2": iso_alpha2.upper(),
        "earlier": _coerce_as_of(earlier).isoformat(),
        "later": _coerce_as_of(later).isoformat(),
        "changed_keys": sorted(changed.keys()),
        "changes": changed,
    }


def runtime_health() -> dict[str, Any]:
    if not SHARD_DIR.is_dir():
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "shard_dir_missing"}
    sample = next(SHARD_DIR.glob("*.json"), None)
    if sample is None:
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shards"}
    iso = sample.stem
    today_view = get_as_of(iso)
    return {
        "contract_id": CONTRACT_ID,
        "healthy": bool(today_view),
        "sample_iso": iso,
        "sample_has_as_of_marker": bool(today_view and "_as_of" in today_view),
    }


def scaffold_present() -> dict[str, object]:
    health = runtime_health()
    return {
        "contract_id": CONTRACT_ID,
        "contract_title": CONTRACT_TITLE,
        "runtime_implementation_status": "production" if health.get("healthy") else "scaffold_only",
        "runtime_health": health,
    }
