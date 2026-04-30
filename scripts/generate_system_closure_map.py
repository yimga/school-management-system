#!/usr/bin/env python3
"""
Regenerate docs/generated/system_closure_map.json.

- Preserves systems[] (program-scale gap catalog) from the existing JSON on disk.
- Sets sot_partial_forward_queue_batches by parsing SOT §11.4 rows whose status
  is PARTIAL, NOT DONE, or BLOCKED (DONE rows are omitted).
- Preserves extra keys under summary (e.g. sot_discipline, program_gap_registry_version)
  and only refreshes summary.note + generated_at.

Run from repo root:
  python scripts/generate_system_closure_map.py --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SUMMARY_NOTE = (
    "systems[] lists program-scale gaps (missing_pieces). "
    "sot_partial_forward_queue_batches is derived from SOT §11.4 lines whose "
    "status token is PARTIAL, NOT DONE, or BLOCKED — regenerate with this script."
)

REPO = Path(__file__).resolve().parent.parent
SOT_PATH = REPO / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
OUT_PATH = REPO / "docs" / "generated" / "system_closure_map.json"

def parse_partial_batch_ids(sot_text: str) -> list[str]:
    """Each §11.4 queue row must be a single line (as in the SOT file)."""
    ids: set[str] = set()
    for line in sot_text.splitlines():
        if "§11.4 forward queue - batch" not in line:
            continue
        m_id = re.search(r"forward queue - batch (\d+)", line)
        if not m_id:
            continue
        if re.search(r":\*\*\s*\*\*PARTIAL\*\*", line):
            ids.add(m_id.group(1))
        elif re.search(r":\*\*\s*\*\*NOT DONE\*\*", line):
            ids.add(m_id.group(1))
        elif re.search(r":\*\*\s*\*\*BLOCKED\*\*", line):
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

    if not OUT_PATH.is_file():
        print(f"generate_system_closure_map: missing base {OUT_PATH}", file=sys.stderr)
        return 1

    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    data["schema_version"] = data.get("schema_version", 1)
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
