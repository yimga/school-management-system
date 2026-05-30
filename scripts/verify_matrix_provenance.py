#!/usr/bin/env python3
"""Phase 0X verifier: provenance block on every country shard (source / effective_from / effective_to / verified_at / verified_by)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
OUT_PATH = REPO / "docs" / "generated" / "matrix_provenance_audit.json"

REQUIRED_KEYS = ("source", "effective_from", "effective_to", "verified_at", "verified_by")


def _audit(require_citation: bool) -> tuple[int, list[str]]:
    failures: list[str] = []
    shard_paths = sorted(SHARD_DIR.glob("*.json")) if SHARD_DIR.is_dir() else []
    if not shard_paths:
        return 0, ["no shards"]
    for path in shard_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        iso = str(data.get("iso_alpha2") or path.stem)
        prov = data.get("provenance")
        if not isinstance(prov, dict):
            failures.append(f"{iso}: provenance missing")
            continue
        for key in REQUIRED_KEYS:
            if key not in prov:
                failures.append(f"{iso}: provenance.{key} missing")
        if require_citation:
            source = prov.get("source") or {}
            if not isinstance(source, dict) or not source.get("citation"):
                failures.append(f"{iso}: provenance.source.citation required under --require-citation")
    return len(shard_paths), failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0X provenance gate")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-citation", action="store_true", help="Tightens gate for P0D close")
    args = parser.parse_args()
    total, failures = _audit(args.require_citation)
    verdict = "MATRIX_PROVENANCE_PASS" if not failures else "MATRIX_PROVENANCE_FAIL"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "shard_total": total,
        "finding_count": len(failures),
        "require_citation": args.require_citation,
        "failures": failures[:80],
    }
    if args.json:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        print(f"verify_matrix_provenance: {verdict} ({len(failures)})", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_matrix_provenance: {verdict} ({total} shards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
