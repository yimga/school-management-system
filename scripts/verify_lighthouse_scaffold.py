#!/usr/bin/env python3
"""Lighthouse A+ scaffolding gate (#2 / #17).

PASS when:
  - docs/LIGHTHOUSE_A_PLUS_RUNBOOK.md exists with key URL guidance
  - npm script ``lighthouse:a-plus`` (or LHCI/tenant config stub) is present

Reports ``EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED`` when no committed score artifact
with all performance scores ≥98 exists. Never invents scores.

Run: python scripts/verify_lighthouse_scaffold.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNBOOK = "docs/LIGHTHOUSE_A_PLUS_RUNBOOK.md"
SCORE_ARTIFACT = "docs/generated/lighthouse_a_plus_scores.json"
PACKAGE_JSON = "package.json"
LHCI_CONFIGS = (
    "lighthouserc.cjs",
    "lighthouserc.js",
    "lighthouserc-tenant.cjs",
)
MIN_SCORE = 98


def _file_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _file_contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _npm_has_script(name: str) -> bool:
    raw = _read(PACKAGE_JSON)
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    scripts = data.get("scripts") or {}
    return name in scripts


def _score_artifact_status() -> tuple[bool, str]:
    """Return (meets_a_plus, detail). Missing/invalid → not meeting A+."""
    rel = SCORE_ARTIFACT
    if not _file_exists(rel):
        return False, f"{rel} absent"
    try:
        data = json.loads(_read(rel))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{rel} unreadable: {exc}"
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return False, f"{rel} has no surfaces[]"
    below: list[str] = []
    has_tenant = False
    has_operator = False
    for s in surfaces:
        if not isinstance(s, dict):
            below.append("non-object surface")
            continue
        sid = str(s.get("id") or s.get("url") or "?")
        url = str(s.get("url") or "").lower()
        perf = s.get("performance")
        a11y = s.get("accessibility")
        try:
            perf_n = float(perf)
        except (TypeError, ValueError):
            below.append(f"{sid}: missing performance")
            continue
        # Allow 0–1 LHCI fraction or 0–100 Lighthouse points.
        if 0 < perf_n <= 1:
            perf_n *= 100
        if perf_n < MIN_SCORE:
            below.append(f"{sid}: performance={perf_n}")
        if a11y is not None:
            try:
                a11y_n = float(a11y)
            except (TypeError, ValueError):
                below.append(f"{sid}: bad accessibility")
            else:
                if 0 < a11y_n <= 1:
                    a11y_n *= 100
                if a11y_n < MIN_SCORE:
                    below.append(f"{sid}: accessibility={a11y_n}")
        if "portal" in url or "authentication" in url or "tenant" in sid:
            has_tenant = True
        if "manager" in url or "marketing" in url or "operator" in sid:
            has_operator = True
    if below:
        return False, f"scores below {MIN_SCORE}: {', '.join(below[:6])}"
    if not has_tenant:
        return False, "artifact missing a tenant surface URL/id"
    if not has_operator:
        return False, "artifact missing an operator/marketing surface URL/id"
    return True, f"{len(surfaces)} surfaces all >={MIN_SCORE}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    checks: list[dict] = []
    external: list[str] = []

    # 1. Runbook
    runbook_ok = _file_exists(RUNBOOK)
    runbook_urls = _file_contains(RUNBOOK, "portal/parent") and _file_contains(
        RUNBOOK, "lighthouse:a-plus"
    )
    runbook_bar = (
        _file_contains(RUNBOOK, ">= 98")
        or _file_contains(RUNBOOK, ">=98")
        or _file_contains(RUNBOOK, "\u2265 98")
        or _file_contains(RUNBOOK, "\u226598")
    )
    checks.append(
        {
            "check": "runbook_exists",
            "pass": runbook_ok,
            "detail": RUNBOOK if runbook_ok else "MISSING",
        }
    )
    checks.append(
        {
            "check": "runbook_content",
            "pass": runbook_urls and runbook_bar,
            "detail": (
                "tenant URLs + lighthouse:a-plus + >=98 bar"
                if runbook_urls and runbook_bar
                else "MISSING key runbook sections"
            ),
        }
    )

    # 2. npm script and/or LHCI config stubs
    npm_a_plus = _npm_has_script("lighthouse:a-plus")
    npm_tenant = _npm_has_script("lighthouse:tenant")
    npm_lh = _npm_has_script("lighthouse")
    configs_present = [c for c in LHCI_CONFIGS if _file_exists(c)]
    stub_ok = npm_a_plus or (npm_tenant and bool(configs_present))
    checks.append(
        {
            "check": "npm_lighthouse_a_plus",
            "pass": npm_a_plus,
            "detail": (
                "package.json scripts.lighthouse:a-plus"
                if npm_a_plus
                else "MISSING lighthouse:a-plus script"
            ),
        }
    )
    checks.append(
        {
            "check": "lhci_or_tenant_config",
            "pass": stub_ok and bool(configs_present),
            "detail": (
                f"configs={configs_present}; tenant_script={npm_tenant}; lighthouse={npm_lh}"
                if configs_present
                else "MISSING lighthouserc*.cjs/js"
            ),
        }
    )

    # 3. Score artifact — EXTERNAL when absent / below bar
    scores_ok, scores_detail = _score_artifact_status()
    checks.append(
        {
            "check": "score_artifact_a_plus",
            "pass": True,  # classification only
            "detail": (
                f"proven: {scores_detail}"
                if scores_ok
                else f"EXTERNAL (unproven): {scores_detail}"
            ),
        }
    )
    if not scores_ok:
        external.append(
            "EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED: No committed "
            f"{SCORE_ARTIFACT} with tenant+operator surfaces all >={MIN_SCORE}. "
            f"Detail: {scores_detail}. "
            "Run real LHCI per docs/LIGHTHOUSE_A_PLUS_RUNBOOK.md and record "
            "scores - never invent green numbers."
        )

    all_pass = all(c["pass"] for c in checks)
    report = {
        "gate": "verify_lighthouse_scaffold",
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "external_remaining": external,
        "scores_a_plus_proven": scores_ok,
        "summary": (
            "Lighthouse A+ scaffolding is present. "
            + (
                f"Committed scores >={MIN_SCORE} proven."
                if scores_ok
                else "Score evidence is EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED."
            )
            if all_pass
            else "Lighthouse scaffold checks failed."
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if all_pass else "FAIL"
        print(f"verify_lighthouse_scaffold: {status}")
        for c in checks:
            mark = "OK" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['check']}: {c['detail']}")
        if external:
            print("\n  EXTERNAL (honest classification, not a gate failure):")
            for e in external:
                print(f"    - {e}")
        if all_pass:
            print("LIGHTHOUSE_SCAFFOLD_PASS")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
