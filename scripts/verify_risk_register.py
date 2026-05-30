#!/usr/bin/env python3
"""Phase 0X: risk_signals block per shard (top_risks / next_review_due)"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
OUT_PATH = REPO / "docs" / "generated" / "risk_register_audit.json"

BLOCK_KEY = 'risk_signals'
SUBKEYS: tuple[str, ...] = ('top_risks', 'next_review_due')


def _dotted_lookup(row: dict, dotted: str):
    cursor: object = row
    for piece in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(piece)
    return cursor


def _audit_shards() -> tuple[int, list[str]]:
    failures: list[str] = []
    if not SHARD_DIR.is_dir():
        return 0, ["no shards directory"]
    shard_paths = sorted(SHARD_DIR.glob("*.json"))
    if not shard_paths:
        return 0, ["no shards present"]
    for path in shard_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        iso = str(data.get("iso_alpha2") or path.stem)
        block = _dotted_lookup(data, BLOCK_KEY)
        if block is None:
            failures.append(f"{iso}: {BLOCK_KEY} missing")
            continue
        if SUBKEYS:
            if not isinstance(block, dict):
                failures.append(f"{iso}: {BLOCK_KEY} must be dict")
                continue
            for sub in SUBKEYS:
                if sub not in block:
                    failures.append(f"{iso}: {BLOCK_KEY}.{sub} missing")
    return len(shard_paths), failures


def _audit_path(path: Path) -> tuple[int, list[str]]:
    if not path.exists():
        return 0, [f"{path.relative_to(REPO)}: missing"]
    return 1, []


def _audit_rollback_runbooks() -> tuple[int, list[str]]:
    runbooks = REPO / "docs" / "rollback_runbooks"
    expected = ("P0D.md", "P1.md", "P2C.md", "P3E.md", "P4G.md", "P5.md")
    failures: list[str] = []
    if not runbooks.is_dir():
        return 0, [f"docs/rollback_runbooks/ missing"]
    for name in expected:
        if not (runbooks / name).is_file():
            failures.append(f"docs/rollback_runbooks/{name}: missing")
    return len(expected), failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    mode = BLOCK_KEY
    if mode == "_template_dir:docs/customer_comms":
        total, failures = _audit_path(REPO / "docs" / "customer_comms")
    elif mode == "_doc_exists:docs/PHASE_SLO_BUDGETS.md":
        total, failures = _audit_path(REPO / "docs" / "PHASE_SLO_BUDGETS.md")
    elif mode == "_module_exists:apps/governance/tests/test_governance_property_invariants.py":
        total, failures = _audit_path(REPO / "apps" / "governance" / "tests" / "test_governance_property_invariants.py")
    elif mode == "_lifecycle_doc":
        total, failures = _audit_path(REPO / "docs" / "architecture" / "ORGANIZATION_GOVERNANCE_LAYER.md")
    elif mode == "_rollback_runbooks":
        total, failures = _audit_rollback_runbooks()
    else:
        total, failures = _audit_shards()

    verdict_slug = "RISK_REGISTER"
    verdict = f"{verdict_slug}_PASS" if not failures else f"{verdict_slug}_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "scope_total": total,
        "finding_count": len(failures),
        "failures": failures[:80],
    }
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(f"verify_risk_register: {verdict} ({len(failures)})", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_risk_register: {verdict} (scope={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
