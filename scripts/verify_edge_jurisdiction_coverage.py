#!/usr/bin/env python3
"""Phase 0X verifier: edge_jurisdiction_flags block on every country shard."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
OUT_PATH = REPO / "docs" / "generated" / "edge_jurisdiction_coverage_audit.json"

REQUIRED_KEYS = (
    "sovereign_state",
    "territory",
    "disputed_recognition",
    "online_only_virtual_school_supported",
    "refugee_nomadic_ed_supported",
    "antarctica_research_only",
    "disputed_regions",
)
DISPUTED_ISO_MUST_FLAG = frozenset({"EH", "PS", "XK", "TW"})


def _audit() -> tuple[int, list[str]]:
    failures: list[str] = []
    shard_paths = sorted(SHARD_DIR.glob("*.json")) if SHARD_DIR.is_dir() else []
    if not shard_paths:
        return 0, ["no shards under docs/generated/country_governance_matrix/"]
    for path in shard_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        iso = str(data.get("iso_alpha2") or path.stem)
        block = data.get("edge_jurisdiction_flags")
        if not isinstance(block, dict):
            failures.append(f"{iso}: edge_jurisdiction_flags missing")
            continue
        for key in REQUIRED_KEYS:
            if key not in block:
                failures.append(f"{iso}: edge_jurisdiction_flags.{key} missing")
        if iso in DISPUTED_ISO_MUST_FLAG and not block.get("disputed_recognition"):
            failures.append(f"{iso}: disputed_recognition must be True")
    return len(shard_paths), failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0X edge jurisdiction coverage gate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    total, failures = _audit()
    verdict = "EDGE_JURISDICTION_COVERAGE_PASS" if not failures else "EDGE_JURISDICTION_COVERAGE_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "shard_total": total,
        "finding_count": len(failures),
        "failures": failures[:80],
    }
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(f"verify_edge_jurisdiction_coverage: {verdict} ({len(failures)})", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_edge_jurisdiction_coverage: {verdict} ({total} shards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
