"""Drift detector for var(--elev-3) consumers across static/css/.

Wave 9 / v3.58.x Agent O. Companion to ``render_verify_elev3_flip.py``.

The --elev-3 token sits at the top of the elevation tier. Bumping its value is
a coordinated audit event because every consumer surface picks up the change.
This scanner walks static/css/ and reports the set of files that reference
``var(--elev-3``. When a new consumer surface starts using --elev-3, the count
goes above baseline and CI fails, forcing the new consumer into the audit
list in ``scripts/render_verify_elev3_flip.py::CONSUMERS`` BEFORE the next
canonical-value change.

Stdlib only. Exit codes:
  0 — consumer count <= baseline (no drift)
  1 — consumer count > baseline (drift)
  2 — usage error

Baseline file:
  var/security-audit-baseline-elev3-consumer-drift.json

CI wiring (deferred):
  Add this scanner to .github/workflows/architectural-boundaries.yml in a
  follow-up plumbing task. Until wired, run manually:
    python scripts/scan_elev3_consumer_drift.py            # check vs baseline
    python scripts/scan_elev3_consumer_drift.py --write    # rewrite baseline
    python scripts/scan_elev3_consumer_drift.py --json     # JSON to stdout
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIR = REPO_ROOT / "static" / "css"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-elev3-consumer-drift.json"
)

# Matches `var(--elev-3` (with or without fallback comma) anywhere in a CSS
# declaration value. Anchored on the opening paren so we don't false-positive
# on `--elev-30` style hypothetical tokens.
_ELEV3_REF = re.compile(r"var\(\s*--elev-3\b")
# Matches a redefine: `--elev-3:` outside the canonical :root block. We treat
# any occurrence (theme-scoped or canonical) as informational.
_ELEV3_DEFN = re.compile(r"^\s*--elev-3\s*:", re.MULTILINE)


def _iter_css_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.css")):
        yield path


def _scan() -> dict[str, list]:
    consumers: list[dict[str, object]] = []
    redefines: list[dict[str, object]] = []
    for path in _iter_css_files(SCAN_DIR):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _ELEV3_REF.search(line):
                consumers.append({"path": rel, "line": lineno, "text": line.strip()[:200]})
            if _ELEV3_DEFN.match(line):
                redefines.append({"path": rel, "line": lineno, "text": line.strip()[:200]})
    consumers.sort(key=lambda item: (item["path"], item["line"]))
    redefines.sort(key=lambda item: (item["path"], item["line"]))
    return {"consumers": consumers, "redefines": redefines}


def _baseline_payload(scan: dict[str, list]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "consumer_count": len(scan["consumers"]),
        "redefine_count": len(scan["redefines"]),
        "consumers": scan["consumers"],
        "redefines": scan["redefines"],
        "rule": (
            "Counts consumers of var(--elev-3) across static/css/. When a new "
            "consumer surface picks up --elev-3, add it to "
            "scripts/render_verify_elev3_flip.py::CONSUMERS and bump this "
            "baseline. CI gate prevents silent expansion of the top-tier "
            "consumer set."
        ),
        "ci_wiring": (
            "wire me into .github/workflows/architectural-boundaries.yml when ready"
        ),
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the baseline JSON from the current scan.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit scan as JSON on stdout (no exit-code semantics).",
    )
    args = parser.parse_args(argv)

    scan = _scan()
    consumer_count = len(scan["consumers"])

    if args.json:
        print(json.dumps(scan, indent=2))
        return 0

    if args.write:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(_baseline_payload(scan), indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"Wrote baseline: {BASELINE_PATH.relative_to(REPO_ROOT).as_posix()} "
            f"(consumers={consumer_count}, redefines={len(scan['redefines'])})"
        )
        return 0

    baseline = _load_baseline()
    if baseline is None:
        print(
            "[elev3-consumer-drift] no baseline yet -- run with --write to "
            "establish one. wire me into "
            ".github/workflows/architectural-boundaries.yml when ready.",
            file=sys.stderr,
        )
        return 0
    baseline_count = int(baseline.get("consumer_count", 0))
    if consumer_count > baseline_count:
        new_paths = {c["path"] for c in scan["consumers"]} - {
            c["path"] for c in baseline.get("consumers", [])
        }
        print(
            f"[elev3-consumer-drift] drift detected: {consumer_count} consumers "
            f"vs baseline {baseline_count}. "
            f"new files: {sorted(new_paths) or '(unchanged file set, count grew)'}. "
            "add each new consumer to "
            "scripts/render_verify_elev3_flip.py::CONSUMERS and re-baseline. "
            "wire me into .github/workflows/architectural-boundaries.yml when ready.",
            file=sys.stderr,
        )
        return 1
    print(
        f"[elev3-consumer-drift] OK: {consumer_count} consumers "
        f"(<= baseline {baseline_count}). "
        "wire me into .github/workflows/architectural-boundaries.yml when ready."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
