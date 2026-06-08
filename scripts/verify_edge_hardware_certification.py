#!/usr/bin/env python3
"""Phase P1 gate for hardware-agnostic edge certification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    catalog_path = ROOT / "config" / "edge_model_catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"edge model catalog unreadable: {exc}")
        catalog = {}
    if catalog.get("version") != 1:
        errors.append("edge model catalog version must be 1")

    hardware = (ROOT / "services" / "edge_hardware.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    for required in (
        "x86_64",
        "arm64",
        "RMC_EDGE_CPU_LIMIT",
        "RMC_EDGE_MEMORY_LIMIT_BYTES",
        "recommendation_only=True",
    ):
        if required not in hardware:
            errors.append(f"edge hardware profiler missing: {required}")

    cert = (ROOT / "services" / "edge_model_certification.py").read_text(
        encoding="utf-8", errors="ignore"
    )
    for required in (
        "HMAC-SHA256",
        "body_sha256",
        "performance_gate_passed",
        "/api/tags",
        "/api/ps",
        "/api/generate",
        "production_certified",
    ):
        if required not in cert:
            errors.append(f"edge certification missing: {required}")

    test = subprocess.run(
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.platform_runtime.tests.test_edge_hardware",
            "--verbosity=1",
        ],
        cwd=ROOT,
        check=False,
    )
    if test.returncode:
        errors.append("edge hardware test suite failed")

    if errors:
        print("EDGE_HARDWARE_CERTIFICATION_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("EDGE_HARDWARE_CERTIFICATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
