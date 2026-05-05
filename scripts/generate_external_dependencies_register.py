#!/usr/bin/env python3
"""
Deterministic emission of docs/generated/external_dependencies_register.{json,md}
from docs/external_dependencies_register.json (human-edited source).

Usage:
  python scripts/generate_external_dependencies_register.py [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "docs" / "external_dependencies_register.json"
OUT_JSON = REPO / "docs" / "generated" / "external_dependencies_register.json"
OUT_MD = REPO / "docs" / "generated" / "external_dependencies_register.md"


def _flatten(source: dict) -> dict:
    entries_out = []
    by_level: dict[str, int] = {}
    systems_hit: set[str] = set()

    for sec in source.get("sections") or []:
        sid = sec.get("id") or ""
        title = sec.get("title") or sid
        for ent in sec.get("entries") or []:
            row = dict(ent)
            row["section_id"] = sid
            row["section_title"] = title
            entries_out.append(row)
            lvl = str(row.get("blocking_level") or "non_blocking").strip()
            by_level[lvl] = by_level.get(lvl, 0) + 1
            impacted = str(row.get("system_impacted") or "")
            for part in impacted.replace(",", " ").split():
                p = part.strip()
                if p:
                    systems_hit.add(p)

    entries_out.sort(key=lambda r: (r.get("section_id") or "", r.get("id") or ""))

    gen = {
        "schema_version": int(source.get("schema_version") or 1),
        "source_path": "docs/external_dependencies_register.json",
        "sections": source.get("sections") or [],
        "entries_flat": entries_out,
        "blocking_level_counts": dict(sorted(by_level.items())),
        "systems_impacted": sorted(systems_hit),
    }
    return gen


def _render_md(gen: dict) -> str:
    def cell(value: object) -> str:
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "# External dependencies register",
        "",
        f"**Source:** `{gen['source_path']}`  ",
        f"**Blocking level counts:** `{json.dumps(gen['blocking_level_counts'])}`  ",
        "",
        "## Payments / PSP highlights",
        "",
        "| Id | Dependency | Blocking | Status | Repo readiness | External action |",
        "|----|------------|----------|--------|----------------|-----------------|",
    ]
    for e in gen["entries_flat"]:
        if str(e.get("section_id")) != "payments_psp_settlement":
            continue
        rid = cell(e.get("id"))
        dep = cell(e.get("external_dependency"))
        blk = cell(e.get("blocking_level"))
        st = cell(e.get("status"))
        rr = cell(e.get("repo_readiness"))
        ea = cell(e.get("external_action_needed"))
        lines.append(f"| {rid} | {dep} | {blk} | {st} | {rr} | {ea} |")
    lines.extend(["", "## Systems impacted (aggregate)", "", ", ".join(gen["systems_impacted"]), ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    if not SRC.is_file():
        print(f"missing source {SRC}", file=sys.stderr)
        return 1
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    gen = _flatten(raw)

    text = json.dumps(gen, indent=2, sort_keys=True) + "\n"
    md = _render_md(gen)

    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(text, encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_MD}")
        return 0

    print(text)
    print(md)
    print("Dry-run; pass --write", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
