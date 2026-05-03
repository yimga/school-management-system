#!/usr/bin/env python3
"""
Regenerate docs/generated/system_closure_map.json.

- systems[] is authored in scripts/system_closure_registry.py (PROGRAM_SYSTEMS).
- Sets sot_partial_forward_queue_batches by parsing SOT §11.4 rows whose status
  is PARTIAL, NOT DONE, or BLOCKED (DONE rows are omitted).
- Preserves extra keys under summary (e.g. sot_discipline) when merging from disk.
- Sets summary.note + generated_at + program_gap_registry_version.

Run from repo root:
  python scripts/generate_system_closure_map.py --write
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SUMMARY_NOTE = (
    "systems[] is sourced from scripts/system_closure_registry.py (PROGRAM_SYSTEMS). "
    "sot_partial_forward_queue_batches is derived from SOT §11.4 lines whose "
    "status token is PARTIAL, NOT DONE, or BLOCKED — regenerate with this script."
)

REPO = Path(__file__).resolve().parent.parent
SOT_PATH = REPO / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
OUT_PATH = REPO / "docs" / "generated" / "system_closure_map.json"
REGISTRY_PATH = REPO / "scripts" / "system_closure_registry.py"


def _load_program_systems() -> list[dict]:
    spec = importlib.util.spec_from_file_location(
        "system_closure_registry", REGISTRY_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load registry {REGISTRY_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = getattr(mod, "PROGRAM_SYSTEMS", None)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("PROGRAM_SYSTEMS must be a non-empty list")
    return rows

def parse_partial_batch_ids(sot_text: str) -> list[str]:
    """Each §11.4 queue row must be a single line (as in the SOT file)."""
    ids: set[str] = set()
    for line in sot_text.splitlines():
        if "§11.4 forward queue - batch" not in line:
            continue
        m_id = re.search(r"forward queue - batch (\d+)", line)
        if not m_id:
            continue
        # Row *status* is the first bold token after the closing "):" title (before the body).
        # Do not scan the full line — later clauses can mention **PARTIAL EXTERNAL BLOCKER** for other batches.
        m_stat = re.search(r"\):\*\*\s*\*\*([^*]+)\*\*", line)
        if not m_stat:
            continue
        stat = m_stat.group(1).strip()
        if stat.startswith("DONE"):
            continue
        if stat.startswith("PARTIAL CLOSED"):
            continue
        if stat.startswith("PARTIAL EXTERNAL BLOCKER"):
            ids.add(m_id.group(1))
        elif stat.startswith("PARTIAL"):
            ids.add(m_id.group(1))
        elif stat.startswith("NOT DONE"):
            ids.add(m_id.group(1))
        elif stat.startswith("BLOCKED"):
            ids.add(m_id.group(1))
    return sorted(ids, key=int)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write docs/generated/system_closure_map.json (default is dry-run print).",
    )
    args = parser.parse_args(argv)

    if not SOT_PATH.is_file():
        print(f"generate_system_closure_map: missing {SOT_PATH}", file=sys.stderr)
        return 1

    sot_text = SOT_PATH.read_text(encoding="utf-8")
    partial_ids = parse_partial_batch_ids(sot_text)

    if not REGISTRY_PATH.is_file():
        print(f"generate_system_closure_map: missing registry {REGISTRY_PATH}", file=sys.stderr)
        return 1

    base = {}
    if OUT_PATH.is_file():
        base = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    data = dict(base)
    data["schema_version"] = data.get("schema_version", 1)
    data["program_gap_registry_version"] = 6
    data["systems"] = _load_program_systems()
    data["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data["source"] = [
        "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md",
        "docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md",
    ]
    data["generator"] = "scripts/generate_system_closure_map.py"
    summary = dict(data.get("summary") or {})
    summary["note"] = SUMMARY_NOTE
    summary.setdefault(
        "regeneration_command",
        "python scripts/generate_system_closure_map.py --write",
    )
    summary["systems_registry"] = "scripts/system_closure_registry.py"
    data["summary"] = summary
    data["sot_partial_forward_queue_batches"] = partial_ids

    out_json = json.dumps(data, indent=2) + "\n"
    if args.write:
        OUT_PATH.write_text(out_json, encoding="utf-8")
        print(f"generate_system_closure_map: wrote {OUT_PATH}")
        print(f"  partial_batches ({len(partial_ids)}): {partial_ids}")
        return 0

    print(out_json)
    print(f"partial_batches ({len(partial_ids)}): {partial_ids}", file=sys.stderr)
    print("Dry-run; pass --write to update JSON.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
