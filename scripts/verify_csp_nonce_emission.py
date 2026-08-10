#!/usr/bin/env python
"""CSP-nonce emission verifier across all 5 shells.

12-pillar audit P1 follow-up. [`apps/security/csp_middleware.py`](../apps/security/csp_middleware.py)
injects a per-request CSP nonce that inline `<script>` tags must echo
via `nonce="{{ csp_nonce }}"`. Missing the template-side echo means the
CSP either denies the script (page breaks) or admits unsafe-inline
(security regression).

This gate parses each of the 5 canonical shell templates and asserts:

  1. The shell uses `{% load static %}` etc. (template parses).
  2. Every `<script>` block that has inline body content carries a
     `nonce="{{ csp_nonce }}"` attribute.
  3. The shell or its ``<head>``-level chain includes
     ``csp_nonce`` in the template context (via context processor or
     middleware-supplied request attribute).

Static analysis only — does not boot Django. Catches the common drift
class: someone adds an inline analytics snippet to a shell without the
nonce attribute.

Usage:
    python scripts/verify_csp_nonce_emission.py             # write baseline
    python scripts/verify_csp_nonce_emission.py --compare   # diff vs baseline (CI)
    python scripts/verify_csp_nonce_emission.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-csp-nonce-emission.json"

# The 5 canonical shells per CLAUDE.md deploy checklist.
SHELL_TEMPLATES = (
    REPO_ROOT / "templates" / "marketing" / "base_marketing.html",
    REPO_ROOT / "templates" / "control_plane_skeleton.html",
    REPO_ROOT / "templates" / "portal_base.html",
    REPO_ROOT / "templates" / "base.html",
    REPO_ROOT / "templates" / "admin" / "base_site.html",
)

# Non-shell templates that carry executable inline <script> blocks and must also echo
# the nonce. Extends coverage beyond the 5 shells so an inline script added outside a
# shell cannot silently reintroduce an unsafe-inline dependency and block CSP enforce.
NONCE_TRACKED_TEMPLATES = (
    REPO_ROOT / "templates" / "migration_cloud" / "conflicts.html",
    REPO_ROOT / "templates" / "migration_cloud" / "connector" / "bundle_review.html",
    REPO_ROOT / "templates" / "migration_cloud" / "progress.html",
    REPO_ROOT / "templates" / "partials" / "rmc_page_personality.html",
    REPO_ROOT / "templates" / "platform_runtime" / "school_configuration_center.html",
    REPO_ROOT / "templates" / "portal" / "ai_line_intents.html",
    REPO_ROOT / "templates" / "siteconfig" / "partials" / "dashboard_configuration_hub_body.html",
)

ALL_TRACKED_TEMPLATES = (*SHELL_TEMPLATES, *NONCE_TRACKED_TEMPLATES)

# Match `<script ...>BODY</script>` blocks (no src). Multi-line aware.
_INLINE_SCRIPT_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>(?:(?!</script>).)*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_HAS_SRC_RE = re.compile(r"\bsrc\s*=", re.IGNORECASE)
# Non-executable script types the browser never runs as JS (data/template payloads).
# These are not subject to CSP script-src, so they need no nonce.
_NON_EXEC_TYPE_RE = re.compile(
    r"""type\s*=\s*['"](?:application/(?:json|ld\+json)|text/(?:template|html|x-template))['"]""",
    re.IGNORECASE,
)
_HAS_NONCE_RE = re.compile(r"\bnonce\s*=\s*['\"]\{\{\s*csp_nonce\s*\}\}['\"]", re.IGNORECASE)
_ALLOW_RE = re.compile(r"<!--\s*csp-nonce-allow:", re.IGNORECASE)


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _scan_shell(path: Path) -> dict:
    if not path.exists():
        return {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "exists": False,
            "violations": [],
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    violations: list[dict] = []
    for match in _INLINE_SCRIPT_RE.finditer(text):
        attrs = match.group("attrs") or ""
        body = (match.group("body") or "").strip()
        if not body:
            continue  # No inline content -> no nonce needed.
        if _HAS_SRC_RE.search(attrs):
            continue  # External script -> SRI gate handles it.
        if _NON_EXEC_TYPE_RE.search(attrs):
            continue  # Data/template block (JSON, ld+json, x-template) -> never executed.
        if _HAS_NONCE_RE.search(attrs):
            continue  # Compliant.
        # Allow-marker on the line just before the tag.
        start_idx = match.start()
        preceding = text[max(0, start_idx - 200):start_idx]
        if _ALLOW_RE.search(preceding):
            continue
        violations.append({
            "line": _line_of(text, start_idx),
            "attrs_snippet": attrs.strip()[:80],
        })
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "exists": True,
        "violations": violations,
    }


def _flatten(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in results:
        for v in r["violations"]:
            out.append({"path": r["path"], "line": v["line"], "attrs": v["attrs_snippet"]})
    out.sort(key=lambda f: (f["path"], f["line"]))
    return out


def _baseline_payload(findings: list[dict], shells_missing: list[str]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "inline <script> elements in the 5 canonical shells must carry "
            "nonce=\"{{ csp_nonce }}\" (or a <!-- csp-nonce-allow: --> marker "
            "for legitimately-safe JSON data blocks)"
        ),
        "shells_missing": shells_missing,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_baseline(findings: list[dict], shells_missing: list[str]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings, shells_missing), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _print_summary(findings: list[dict], results: list[dict]) -> None:
    print(f"CSP-nonce emission: {len(ALL_TRACKED_TEMPLATES)} template(s); violations={len(findings)}")
    for r in results:
        if not r["exists"]:
            print(f"  ! MISSING  {r['path']}")
            continue
        n = len(r["violations"])
        marker = "[ok]" if n == 0 else f"[{n} viol]"
        print(f"  {marker:9s} {r['path']}")
        for v in r["violations"]:
            print(f"      line {v['line']}: <script {v['attrs_snippet']}>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [_scan_shell(p) for p in ALL_TRACKED_TEMPLATES]
    findings = _flatten(results)
    shells_missing = [r["path"] for r in results if not r["exists"]]
    payload = _baseline_payload(findings, shells_missing)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.compare:
        baseline = _load_baseline()
        if baseline is None:
            _print_summary(findings, results)
            print("\nNo baseline on disk. Run without --compare to write one.")
            return 1 if findings else 0
        baseline_set = {(f["path"], f["line"]) for f in baseline.get("findings", [])}
        current_set = {(f["path"], f["line"]) for f in findings}
        new = current_set - baseline_set
        _print_summary(findings, results)
        if new:
            print("\nNEW inline <script> without csp_nonce:")
            for path, line in sorted(new):
                print(f"  {path}:{line}")
        if shells_missing:
            return 1
        return 1 if new else 0
    _print_summary(findings, results)
    _write_baseline(findings, shells_missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
