#!/usr/bin/env python3
"""
Cursor Phase 7 — Runtime-first enforcement — mechanical gate (narrow bundle).

For execution-law granular verification (tenant lints incl. studio_os + middleware tests), run
``scripts/verify_cursor_phase7_granular.py`` after this passes.

Validates canonical precedence order, required resolver registry entries, core module
and template presence, then runs contract/precedence/inspector pytest modules.

Environment:
  PHASE7_RUNTIME_FIRST_SKIP_PYTEST=1 — skip the pytest subprocess (used by
  verify_cursor_phase7_granular.py, which runs one combined pytest session).

Exit 0 = all checks pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "docs" / "phase_audit" / "PHASE_07_RUNTIME_FIRST_AUDIT.md"
PRECEDENCE_DOC = ROOT / "docs" / "runtime_precedence.md"

# Must match docs/runtime_precedence.md section 1 and apps/platform_runtime/precedence.py
CANONICAL_PRECEDENCE = (
    "platform_default",
    "registry_default",
    "blueprint_default",
    "policy_bundle",
    "entitlement_gate",
    "tenant_override",
    "sandbox_override",
)

REQUIRED_RESOLVERS = frozenset(
    {
        "RuntimeResolver",
        "BrandingResolver",
        "BlueprintResolver",
        "PolicyResolver",
        "WorkflowResolver",
        "DashboardResolver",
        "EntitlementResolver",
        "IntegrationResolver",
        "LocalizationResolver",
    }
)

REQUIRED_PATHS = (
    ROOT / "apps" / "platform_runtime" / "precedence.py",
    ROOT / "apps" / "platform_runtime" / "resolver_registry.py",
    ROOT / "apps" / "platform_runtime" / "runtime_resolver.py",
    ROOT / "apps" / "platform_runtime" / "runtime_inspector.py",
    ROOT / "templates" / "schools" / "super_runtime_inspector.html",
    ROOT / "docs" / "runtime_precedence.md",
)


def main() -> int:
    errors: list[str] = []

    for p in REQUIRED_PATHS:
        if not p.is_file():
            errors.append(f"Missing required file: {p.relative_to(ROOT)}")

    if not AUDIT.is_file():
        errors.append(f"Missing mandatory audit: {AUDIT.relative_to(ROOT)}")
    else:
        body = AUDIT.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "## 1. Goal",
            "## 2. Precedence",
            "## 3. Resolver map",
            "## 4. Touched behavior paths",
            "## 6. Acceptance",
        ):
            if needle not in body:
                errors.append(f"PHASE_07 audit missing section {needle!r}")

    if PRECEDENCE_DOC.is_file():
        prev_body = PRECEDENCE_DOC.read_text(encoding="utf-8", errors="replace")
        for layer in ("Platform default", "Registry", "Blueprint", "Policy bundle"):
            if layer not in prev_body:
                errors.append(f"runtime_precedence.md should mention {layer!r}")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.platform_runtime.precedence import PRECEDENCE_ORDER

    if tuple(PRECEDENCE_ORDER) != CANONICAL_PRECEDENCE:
        errors.append(
            f"PRECEDENCE_ORDER mismatch: got {tuple(PRECEDENCE_ORDER)!r}, "
            f"expected {CANONICAL_PRECEDENCE!r}"
        )

    from apps.platform_runtime.resolver_registry import RESOLVER_ENTRY_POINTS

    names = {entry[0] for entry in RESOLVER_ENTRY_POINTS}
    missing = REQUIRED_RESOLVERS - names
    if missing:
        errors.append(
            f"resolver_registry missing required resolvers: {sorted(missing)}"
        )

    # Granular gate (verify_cursor_phase7_granular.py) runs one combined pytest session to avoid
    # back-to-back SQLite test DB contention on Windows ("database is locked").
    if os.environ.get("PHASE7_RUNTIME_FIRST_SKIP_PYTEST", "").strip() not in ("1", "true", "yes"):
        py = sys.executable
        pytest_targets = [
            "apps/platform_runtime/tests/test_phase7_runtime_gate.py",
            "apps/platform_runtime/tests/test_precedence.py",
            "apps/platform_runtime/tests/test_runtime_contract.py",
        ]
        proc = subprocess.run(
            [py, "-m", "pytest", *pytest_targets, "-q", "--no-header"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            errors.append(
                f"pytest Phase 7 contract suite failed (exit {proc.returncode}):\n"
                f"{proc.stdout}\n{proc.stderr}"
            )

    if errors:
        print("verify_cursor_phase7_runtime_first: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  ---\n{e}", file=sys.stderr)
        return 1

    print(
        "verify_cursor_phase7_runtime_first: PASS",
        f"({len(REQUIRED_RESOLVERS)} required resolvers; precedence len={len(CANONICAL_PRECEDENCE)})",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
