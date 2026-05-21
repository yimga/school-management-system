#!/usr/bin/env python3
"""Scan control-plane templates for layout patterns that cause abrupt page ends."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"

EXTENDS_CP = re.compile(
    r"""extends\s+['"]control_plane_base\.html['"]""", re.IGNORECASE
)
OVERFLOW_HIDDEN = re.compile(r"overflow\s*:\s*hidden", re.IGNORECASE)
MAX_VH_CLIP = re.compile(
    r"max-height\s*:\s*calc\s*\(\s*100vh\s*-\s*\d+px\s*\)", re.IGNORECASE
)
DUPLICATE_CLASS = re.compile(r"""class\s*=\s*['"][^'"]*['"][^>]*class\s*=\s*['"]""", re.I)
MIN_H_ZERO_TRAP = re.compile(
    r"min-h-0[^\"']*[\"'][^>]*>[\s\S]{0,200}?overflow\s*:\s*hidden",
    re.IGNORECASE | re.DOTALL,
)


def scan_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not EXTENDS_CP.search(text):
        return []
    rel = path.relative_to(REPO).as_posix()
    findings = []
    for i, line in enumerate(text.splitlines(), 1):
        if OVERFLOW_HIDDEN.search(line) and "sticky-overflow-allow" not in line:
            findings.append(
                {"file": rel, "line": i, "rule": "overflow-hidden", "snippet": line.strip()[:120]}
            )
        if MAX_VH_CLIP.search(line):
            findings.append(
                {"file": rel, "line": i, "rule": "max-height-100vh-clip", "snippet": line.strip()[:120]}
            )
        if DUPLICATE_CLASS.search(line):
            findings.append(
                {"file": rel, "line": i, "rule": "duplicate-class-attr", "snippet": line.strip()[:120]}
            )
    if MIN_H_ZERO_TRAP.search(text):
        findings.append(
            {
                "file": rel,
                "line": 0,
                "rule": "min-h-0-with-overflow-hidden",
                "snippet": "(multiline pattern)",
            }
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path, help="Write JSON report path")
    args = parser.parse_args()
    all_findings: list[dict] = []
    scanned = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        scanned += 1
        all_findings.extend(scan_file(path))

    by_file: dict[str, list[dict]] = {}
    for f in all_findings:
        by_file.setdefault(f["file"], []).append(f)

    print(f"Scanned {scanned} templates; {len(by_file)} control-plane files with findings")
    print(f"Total findings: {len(all_findings)}")
    for rel in sorted(by_file.keys())[:40]:
        print(f"  {rel}: {len(by_file[rel])}")
    if len(by_file) > 40:
        print(f"  ... and {len(by_file) - 40} more files")

    if args.write:
        import json

        payload = {
            "scanned": scanned,
            "files_with_findings": len(by_file),
            "findings": all_findings,
        }
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.write}")

    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
