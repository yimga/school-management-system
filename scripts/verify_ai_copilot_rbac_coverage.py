#!/usr/bin/env python
"""Verify user-facing AI invoke paths declare copilot RBAC coverage.

Every ``apps/`` module that calls ``invoke_with_request`` or
``invoke_with_request_stream`` must either:

  * call ``prepare_copilot_invoke`` / ``prepare_engine_room_rbac`` /
    ``guard_copilot_invoke`` / ``validate_copilot_query``, or
  * set ``copilot_rbac_enforced`` / ``copilot_rbac_skip`` in metadata before
    invoke, or
  * appear on the internal-task allowlist (batch/background paths).

Central enforcement in ``services.ai_helpers`` still applies at runtime; this
gate catches regressions where a new view bypasses the canonical envelope.

Usage:
  python scripts/verify_ai_copilot_rbac_coverage.py
  python scripts/verify_ai_copilot_rbac_coverage.py --strict
  python scripts/verify_ai_copilot_rbac_coverage.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-ai-copilot-rbac-coverage.json"

INVOKE_RE = re.compile(r"\binvoke_with_request(?:_stream)?\s*\(")
RBAC_MARKERS = (
    "prepare_copilot_invoke",
    "prepare_engine_room_rbac",
    "guard_copilot_invoke",
    "invoke_service_layer_ai",
    "validate_copilot_query",
    "copilot_rbac_enforced",
    "copilot_rbac_skip",
    "process_platform_query",
)

GATEWAY_INVOKE_RE = re.compile(
    r"\bfrom services\.ai_gateway import invoke\b|\bservices\.ai_gateway\.invoke\s*\("
)

SERVICES_DIR = REPO_ROOT / "services"

# services/* modules allowed to call ai_gateway.invoke directly (infrastructure).
SERVICES_GATEWAY_ALLOWLIST = frozenset(
    {
        "services/ai_helpers.py",
        "services/ai_gateway_streaming.py",
        "services/ai_gateway.py",
        "services/ai/deployment_posture.py",
    }
)

# Repo-relative POSIX paths — infrastructure may call gateway directly (see scan_ai_gateway_boundary).
APPS_GATEWAY_ALLOWLIST = frozenset(
    {
        "apps/migration_cloud/ai_bridge.py",
        "apps/portal/views_ai_gateway.py",
    }
)

# Repo-relative POSIX paths — background / staff-only batch AI (no user query RBAC).
ALLOWLIST = frozenset(
    {
        "apps/migration_cloud/ai_bridge.py",
        "apps/siteconfig/support_ai_triage.py",
        "apps/siteconfig/support_ai_reply.py",
        "apps/setup_studio/wizard_ai.py",
        "apps/platform_runtime/workflow_auto_fix.py",
        "apps/platform_runtime/ai_workflow_invoker.py",
        "apps/brand_experience/template_ai_recommender.py",
        "apps/portal/tasks.py",
        "apps/api/learning_institution_api.py",
    }
)

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests"}


def _iter_app_python_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if "tests" in rel_parts:
            continue
        if "management" in rel_parts and "commands" in rel_parts:
            continue
        out.append(path)
    return out


def scan() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in _iter_app_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not INVOKE_RE.search(text):
            continue
        if any(marker in text for marker in RBAC_MARKERS):
            continue
        findings.append(
            {
                "path": rel,
                "reason": "invoke_without_copilot_rbac_marker",
            }
        )

    for path in _iter_app_python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in APPS_GATEWAY_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not GATEWAY_INVOKE_RE.search(text):
            continue
        if any(marker in text for marker in RBAC_MARKERS):
            continue
        findings.append(
            {
                "path": rel,
                "reason": "apps_direct_gateway_invoke_without_rbac_bridge",
            }
        )

    for path in sorted(SERVICES_DIR.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if "tests" in rel_parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in SERVICES_GATEWAY_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not GATEWAY_INVOKE_RE.search(text):
            continue
        if "invoke_service_layer_ai" in text or "guard_copilot_invoke" in text:
            continue
        findings.append(
            {
                "path": rel,
                "reason": "services_direct_gateway_invoke_without_rbac_bridge",
            }
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 when findings > 0")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings = scan()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "findings": findings,
    }

    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline: {BASELINE_PATH} ({len(findings)} findings)")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if findings:
            print(f"AI copilot RBAC coverage: {len(findings)} gap(s)")
            for row in findings:
                print(f"  - {row['path']}: {row['reason']}")
        else:
            print("AI_COPILOT_RBAC_COVERAGE_PASS")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
