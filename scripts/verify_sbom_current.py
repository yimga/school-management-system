#!/usr/bin/env python3
"""Fail CI when the committed SBOM is stale relative to the declared manifests.

Open-source-first audit verifier. Regenerates the CycloneDX SBOM in memory from
requirements.txt + package.json/package-lock.json and compares it byte-for-byte
to the committed docs/generated/runmycampus_sbom.cdx.json. A mismatch means a
dependency was added, removed, or version-bumped without running
`python scripts/generate_sbom.py --write` — i.e. the SBOM (and its license
inventory) no longer reflects what the platform actually ships.

Usage:
    python scripts/verify_sbom_current.py            # human-readable
    python scripts/verify_sbom_current.py --compare    # CI mode (same behavior; exit 1 on drift)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_sbom  # noqa: E402  (sibling script, path injected above)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare", action="store_true", help="CI mode (exit 1 on drift)"
    )
    parser.parse_args(argv)

    root = generate_sbom.repo_root()
    committed_path = root / generate_sbom.SBOM_RELATIVE_PATH
    expected = generate_sbom.build_sbom_text(root)

    if not committed_path.exists():
        print(
            f"SBOM MISSING: {committed_path} does not exist.\n"
            "Run: python scripts/generate_sbom.py --write",
            file=sys.stderr,
        )
        return 1

    actual = committed_path.read_text(encoding="utf-8")
    if actual == expected:
        n = expected.count('"purl"')
        print(f"SBOM current: {committed_path.name} matches the declared manifests ({n} components).")
        return 0

    print(
        "SBOM DRIFT: the committed SBOM no longer matches requirements.txt / package.json.\n"
        "Regenerate it with: python scripts/generate_sbom.py --write\n",
        file=sys.stderr,
    )
    # Show a compact diff of component lines to make the failure actionable.
    import difflib

    diff = difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile="committed",
        tofile="expected",
        lineterm="",
        n=1,
    )
    shown = 0
    for line in diff:
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            print("  " + line, file=sys.stderr)
            shown += 1
            if shown >= 40:
                print("  … (diff truncated)", file=sys.stderr)
                break
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
