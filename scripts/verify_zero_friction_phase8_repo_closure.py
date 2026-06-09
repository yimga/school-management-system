#!/usr/bin/env python3
"""
Repo-scope closure gate for Zero-Friction phase 8 (Z8–Z15 companions, edge, baselines).

Does not require live Django host or full CI architectural-boundaries replay.
Playwright abrupt-end / Postgres RLS remain operator-gated (documented in register).

Run: python scripts/verify_zero_friction_phase8_repo_closure.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VENDOR_EXTRACTOR_STEMS = (
    "powerschool",
    "blackbaud",
    "veracross",
    "alma",
    "facts",
    "skyward",
)


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _count_sibling_extractors() -> int:
    count = 0
    for sibling, pattern in (
        ("companion-docker/app/extractors", "*.py"),
        ("companion-tauri/src-tauri/src/extractors", "*.rs"),
    ):
        base = ROOT / sibling
        if base.is_dir():
            count += sum(1 for p in base.glob(pattern) if p.stem in VENDOR_EXTRACTOR_STEMS)
    return count


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []

    for rel in (
        "companion-extension/package.json",
        "companion-extension/manifest.json",
        "companion-tauri/src-tauri/Cargo.toml",
        "companion-docker/app/__init__.py",
        "packages/runmycampus-webhook-verifier-py/pyproject.toml",
        "packages/runmycampus-webhook-verifier-js/package.json",
    ):
        if not _exists(rel):
            errors.append(f"missing {rel}")

    extractors = _count_sibling_extractors()
    if extractors < 12:
        errors.append(
            f"companion sibling vendor extractors={extractors} (expected >= 12 across tauri+docker)"
        )

    edge_ok = _exists("edge/src/worker.js") or _exists("edge/worker.js")
    if not edge_ok:
        errors.append("missing edge worker (edge/src/worker.js or edge/worker.js)")

    for name, cmd in (
        (
            "dead_hrefs",
            [sys.executable, str(ROOT / "scripts/scan_operator_shell_dead_hrefs.py"), "--strict"],
        ),
        (
            "tenant_isolation",
            [
                sys.executable,
                str(ROOT / "scripts/scan_tenant_queryset_safety.py"),
                "--compare",
            ],
        ),
        (
            "sw_version",
            [
                sys.executable,
                str(ROOT / "scripts/verify_service_worker_version.py"),
                "--check-monotonic",
            ],
        ),
        (
            "phases_0_8",
            [sys.executable, str(ROOT / "scripts/verify_zero_friction_phases_0_8.py")],
        ),
    ):
        rc = subprocess.call(cmd, cwd=str(ROOT))
        if rc != 0:
            errors.append(f"subprocess gate failed: {name}")

    if errors:
        for err in errors:
            print(f"verify_zero_friction_phase8_repo_closure: {err}", file=sys.stderr)
        return 1

    print(
        "ZERO_FRICTION_PHASE8_REPO_CLOSURE_PASS "
        f"(extractors={extractors}, edge={edge_ok})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
