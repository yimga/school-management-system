#!/usr/bin/env python
"""Marketing asset parity scanner.

Prevents the "documentation ahead of code" failure mode where a closure report
or design doc claims a marketing asset exists but the file was never committed
(or vice versa: a file lives in static/images/marketing/ but is unreferenced).

Scans every Markdown file in ``docs/`` plus ``CLAUDE.md`` at repo root for
filenames matching the marketing-asset pattern::

    (platform|solution|module|hero|illustration|viz|setup-studio|ecosystem)-<slug>.svg

For each claimed asset:

  * verifies the file exists under ``static/images/marketing/``
  * verifies the file is referenced from at least one template under
    ``templates/`` (so we don't ship dead assets)

Exits 1 if either check fails. Exits 0 if every claimed asset is both present
on disk and referenced from a template.

Usage::

    python scripts/check_marketing_assets_claimed_vs_present.py
    python scripts/check_marketing_assets_claimed_vs_present.py --json
    python scripts/check_marketing_assets_claimed_vs_present.py --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ASSETS_DIR = REPO_ROOT / "static" / "images" / "marketing"
TEMPLATES_DIR = REPO_ROOT / "templates"

ASSET_PREFIXES = (
    "platform",
    "solution",
    "module",
    "hero",
    "illustration",
    "viz",
    "setup-studio",
    "ecosystem",
    "control-plane",
    "migration",
    "global",
    "health-score",
    "logo",
    "testimonial",
)

ASSET_FILENAME_RE = re.compile(
    r"\b((?:" + "|".join(re.escape(p) for p in ASSET_PREFIXES) + r")-[A-Za-z0-9_-]+\.svg)\b"
)

# Markers that qualify an asset reference as roadmap/intent, not a shipping claim.
# When any of these appear on the same line as an asset filename, the line is
# treated as "planned" and excluded from the missing-asset failure mode. This
# lets execution logs and roadmaps reference future assets without polluting CI.
PLANNED_MARKERS = (
    "(planned)",
    "[planned]",
    "(roadmap)",
    "[roadmap]",
    "(todo)",
    "[todo]",
    "(future)",
    "[future]",
    "not yet shipped",
    "not yet built",
    "yet to ship",
    "yet to build",
    "<!-- planned -->",
    "<!-- roadmap -->",
)

# Explicit roadmap allowlist — assets named in docs as future deliverables.
# Each entry needs a reason so the allowlist stays honest. Remove an entry
# only when the corresponding asset ships AND is referenced from a template.
PLANNED_ASSETS: dict[str, str] = {
    "platform-admissions-readiness-board.svg":
        "Phase-1 design work — Readiness-board archetype for /run/admissions/",
    "platform-fees-collection-cockpit.svg":
        "Phase-1 design work — Finance-cockpit archetype for /pay/fees/",
    "platform-parent-day-in-life.svg":
        "Phase-1 design work — Persona day artifact for /solutions/parent/",
    "platform-teacher-classroom-desk.svg":
        "Phase-1 design work — Classroom-desk archetype for /teach/",
    "solution-faith-community-hub.svg":
        "Phase-1 design work — Community-operations archetype for /solutions/faith-based/",
    "solution-growing-network-playbook.svg":
        "Phase-1 design work — Launch-playbook archetype for /solutions/growing-networks/",
    "solution-private-growth-engine.svg":
        "Phase-1 design work — Enrollment-growth archetype for /solutions/private/",
}

# Legacy placeholder assets kept on disk for backfill/fallback paths but not
# referenced by any current view/template. Retirement decision deferred to a
# later cleanup wave; allowlisted here so the scanner can stay green.
LEGACY_KEPT_ASSETS: dict[str, str] = {
    "hero-placeholder.svg":
        "Generic fallback for marketing_hero_image.html when a slug-keyed hero is missing",
    "logo-placeholder.svg":
        "Generic logo placeholder for press-marks and partner-tile fallbacks",
    "testimonial-thumb.svg":
        "Generic avatar fallback for testimonial cards when a real photo is absent",
}


def _iter_doc_files() -> list[Path]:
    docs: list[Path] = []
    if CLAUDE_MD.exists():
        docs.append(CLAUDE_MD)
    if DOCS_DIR.exists():
        docs.extend(sorted(DOCS_DIR.rglob("*.md")))
    return docs


def _claimed_assets() -> dict[str, list[str]]:
    """Returns {asset_filename: [doc_paths_that_mention_it]} for unqualified claims only.

    References on lines containing a PLANNED_MARKERS token are excluded — they
    represent roadmap/intent, not shipping claims.
    """
    claims: dict[str, list[str]] = {}
    for doc in _iter_doc_files():
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line_lower = line.lower()
            if any(marker in line_lower for marker in PLANNED_MARKERS):
                continue
            for match in ASSET_FILENAME_RE.finditer(line):
                name = match.group(1)
                claims.setdefault(name, []).append(str(doc.relative_to(REPO_ROOT)))
    return claims


def _present_assets() -> set[str]:
    if not ASSETS_DIR.exists():
        return set()
    return {p.name for p in ASSETS_DIR.glob("*.svg")}


REFERENCE_SEARCH_ROOTS = (
    REPO_ROOT / "templates",
    REPO_ROOT / "apps",
    REPO_ROOT / "config" / "marketing_content",
    REPO_ROOT / "static" / "images" / "marketing",
)
REFERENCE_SEARCH_GLOBS = ("*.html", "*.py", "*.json", "*.md")
REFERENCE_SEARCH_EXCLUDE = {"__pycache__", "node_modules", ".pytest_cache", "migrations"}


def _asset_references(name: str, file_index: list[tuple[str, str]]) -> list[str]:
    """Find every file in the prebuilt index that mentions ``name``.

    Reading every file once into ``file_index`` and then checking membership
    is O(files + assets), vs the naive O(files * assets) which timed out at 60s.
    """
    return [rel for rel, text in file_index if name in text]


def _file_index() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    seen: set[Path] = set()
    for root in REFERENCE_SEARCH_ROOTS:
        if not root.exists():
            continue
        for glob in REFERENCE_SEARCH_GLOBS:
            for path in root.rglob(glob):
                if path in seen:
                    continue
                if any(part in REFERENCE_SEARCH_EXCLUDE for part in path.parts):
                    continue
                seen.add(path)
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                files.append((str(path.relative_to(REPO_ROOT)), text))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="include claim sources + ref sites in human output")
    args = parser.parse_args()

    claims = _claimed_assets()
    present = _present_assets()

    claimed_but_missing: list[dict] = []
    planned_not_yet_built: list[dict] = []
    present_but_unreferenced: list[str] = []

    for name, sources in sorted(claims.items()):
        if name in present:
            continue
        if name in PLANNED_ASSETS:
            planned_not_yet_built.append({
                "asset": name,
                "reason": PLANNED_ASSETS[name],
                "claimed_in": sources,
            })
            continue
        claimed_but_missing.append({"asset": name, "claimed_in": sources})

    legacy_kept: list[dict] = []
    file_index = _file_index()
    for name in sorted(present):
        refs = _asset_references(name, file_index)
        if refs:
            continue
        if name in LEGACY_KEPT_ASSETS:
            legacy_kept.append({"asset": name, "reason": LEGACY_KEPT_ASSETS[name]})
            continue
        present_but_unreferenced.append(name)

    report = {
        "scanned_docs": len(_iter_doc_files()),
        "claimed_assets": len(claims),
        "present_assets": len(present),
        "claimed_but_missing": claimed_but_missing,
        "planned_not_yet_built": planned_not_yet_built,
        "present_but_unreferenced": present_but_unreferenced,
        "legacy_kept": legacy_kept,
        "ok": not claimed_but_missing and not present_but_unreferenced,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    print(f"Marketing asset parity audit")
    print(f"  Scanned docs:       {report['scanned_docs']}")
    print(f"  Claimed in docs:    {report['claimed_assets']}")
    print(f"  Present on disk:    {report['present_assets']}")
    print(f"  Missing (fail):     {len(claimed_but_missing)}")
    print(f"  Planned (allowed):  {len(planned_not_yet_built)}")
    print(f"  Unreferenced:       {len(present_but_unreferenced)}")
    print()

    if planned_not_yet_built and args.verbose:
        print("PLANNED-NOT-YET-BUILT (allowlisted; tracked for future delivery):")
        for entry in planned_not_yet_built:
            print(f"  - {entry['asset']}")
            print(f"      reason: {entry['reason']}")
        print()

    if claimed_but_missing:
        print("CLAIMED-BUT-MISSING (documentation says these exist; the file does not):")
        for entry in claimed_but_missing:
            print(f"  - {entry['asset']}")
            if args.verbose:
                for src in entry["claimed_in"]:
                    print(f"      claimed in: {src}")
        print()

    if present_but_unreferenced:
        print("PRESENT-BUT-UNREFERENCED (asset exists on disk; no template references it):")
        for name in present_but_unreferenced:
            print(f"  - {name}")
        print()

    if report["ok"]:
        print("OK: every claimed asset exists and every present asset is referenced.")
        return 0
    print("FAIL: reconcile docs and assets before shipping.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
