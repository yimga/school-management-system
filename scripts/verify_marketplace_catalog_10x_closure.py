#!/usr/bin/env python3
"""
Wave 8 — Run marketplace catalog 10x wave verifiers (stdlib subprocess bundle).

Usage: python scripts/verify_marketplace_catalog_10x_closure.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CHECKS: list[tuple[str, list[str]]] = [
    ("wave1_capability_contract", ["scripts/verify_marketplace_app_capability_contract.py"]),
    ("package_payload_parity", ["scripts/verify_marketplace_package_payload_parity.py"]),
    (
        "legacy_first_party_payload_parity",
        ["scripts/verify_first_party_package_payload_parity.py"],
    ),
    (
        "sandbox_embed_registry",
        ["scripts/verify_marketplace_sandbox_embed_registry.py"],
    ),
    (
        "legacy_package_id_bindings",
        ["scripts/verify_legacy_package_id_bindings.py"],
    ),
    (
        "catalog_package_coverage",
        ["scripts/verify_marketplace_catalog_package_coverage.py"],
    ),
    (
        "integration_adapter_credentials",
        ["scripts/verify_integration_adapter_credential_schema.py"],
    ),
    ("wave4_scroll_pagination", ["scripts/verify_scroll_compression_catalog_pagination.py"]),
    ("wave5_platform_mission", ["scripts/verify_marketplace_platform_mission.py"]),
]

MARKER_FILES: list[tuple[str, str]] = [
    ("wave2_orchestrator", "apps/marketplace/activation_orchestrator.py"),
    ("wave3_capability_registry", "apps/marketplace/capability_contract.py"),
    ("wave6_scope_normalize", "apps/marketplace/scope_normalize.py"),
]


def main() -> int:
    failed: list[str] = []
    for name, rel in MARKER_FILES:
        if not (REPO / rel).is_file():
            failed.append(name)
            print(f"missing {rel}", file=sys.stderr)
    for name, cmd in CHECKS:
        proc = subprocess.run(
            [sys.executable, *[str(REPO / c) for c in cmd]],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            failed.append(name)
            err = (proc.stderr or proc.stdout or "").strip()
            if err:
                print(err, file=sys.stderr)
    if failed:
        print(
            "MARKETPLACE_CATALOG_10X_CLOSURE_FAIL: " + ", ".join(failed),
            file=sys.stderr,
        )
        return 1
    print("MARKETPLACE_CATALOG_10X_CLOSURE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
