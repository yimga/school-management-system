#!/usr/bin/env python
"""PWA manifest emission coverage scanner.

12-pillar audit P9 follow-up. The 4 dashboard shells (portal_base,
base, control_plane_skeleton, admin/base_site) must each emit a
``<link rel="manifest" href="...">`` so the browser can register the
PWA install prompt. Marketing is intentionally exempt (per memory
v3.8 — marketing has no manifest by design).

Static analysis only: parses each shell template, asserts the
``<link rel="manifest" ...>`` tag is present, and reports the href.

Usage:
    python scripts/scan_pwa_manifest_coverage.py             # write baseline
    python scripts/scan_pwa_manifest_coverage.py --compare   # diff vs baseline
    python scripts/scan_pwa_manifest_coverage.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-pwa-manifest-coverage.json"

SHELLS_REQUIRING_MANIFEST = (
    ("portal", REPO_ROOT / "templates" / "portal_base.html"),
    ("backend", REPO_ROOT / "templates" / "base.html"),
    ("control_plane", REPO_ROOT / "templates" / "control_plane_skeleton.html"),
    ("admin", REPO_ROOT / "templates" / "admin" / "base_site.html"),
)

# Marketing shell is exempt per memory v3.8 — listed here for visibility.
EXEMPT_SHELLS = (REPO_ROOT / "templates" / "marketing" / "base_marketing.html",)

_MANIFEST_RE = re.compile(
    r'<link\b[^>]*\brel\s*=\s*[\'"]manifest[\'"][^>]*\bhref\s*=\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)


def _scan_shell(name: str, path: Path) -> dict:
    if not path.exists():
        return {
            "name": name,
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "exists": False,
            "has_manifest": False,
            "href": None,
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _MANIFEST_RE.search(text)
    return {
        "name": name,
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "exists": True,
        "has_manifest": bool(m),
        "href": m.group(1) if m else None,
    }


def _baseline_payload(results, missing) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "each of 4 dashboard shells must emit <link rel=\"manifest\" href=\"...\">",
        "shells_required": [r["name"] for r in results],
        "exempt_marketing_shell": str(EXEMPT_SHELLS[0].relative_to(REPO_ROOT).as_posix()),
        "finding_count": len(missing),
        "findings": [{"name": r["name"], "path": r["path"]} for r in missing],
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_baseline(payload: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _print_summary(results: list[dict], missing: list[dict]) -> None:
    print(
        f"PWA manifest coverage: {len(SHELLS_REQUIRING_MANIFEST)} shell(s) "
        f"required; {len(results) - len(missing)} compliant; {len(missing)} missing"
    )
    for r in results:
        marker = "[ok]" if r["has_manifest"] else "[MISSING]"
        print(f"  {marker:10s} {r['name']:15s} {r['path']}")
        if r["has_manifest"]:
            print(f"           href={r['href']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [_scan_shell(n, p) for n, p in SHELLS_REQUIRING_MANIFEST]
    missing = [r for r in results if not r["has_manifest"] or not r["exists"]]
    payload = _baseline_payload(results, missing)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.compare:
        baseline = _load_baseline()
        if baseline is None:
            _print_summary(results, missing)
            print("\nNo baseline on disk. Run without --compare to write one.")
            return 1 if missing else 0
        baseline_names = {f["name"] for f in baseline.get("findings", [])}
        current_names = {r["name"] for r in missing}
        new = current_names - baseline_names
        _print_summary(results, missing)
        if new:
            print("\nNEW shell(s) missing manifest:")
            for n in sorted(new):
                print(f"  - {n}")
        return 1 if new else 0
    _print_summary(results, missing)
    _write_baseline(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
