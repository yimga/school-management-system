#!/usr/bin/env python3
"""Phase P6 gate for privacy-bounded responsive layout observability."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    observer = (ROOT / "static" / "js" / "rmc-layout-observer.js").read_text(
        encoding="utf-8"
    )
    viewport = (ROOT / "static" / "js" / "rmc-viewport-engine.js").read_text(
        encoding="utf-8"
    )
    beacon = (ROOT / "static" / "js" / "rum-beacon.js").read_text(
        encoding="utf-8"
    )
    sanitizer = (
        ROOT / "apps" / "platform_runtime" / "layout_observability.py"
    ).read_text(encoding="utf-8")
    shell_partial = (
        ROOT / "templates" / "partials" / "rmc_viewport_engine.html"
    ).read_text(encoding="utf-8")

    for token in (
        "ResizeObserver",
        "MutationObserver",
        "MAX_ELEMENTS = 160",
        "data-rmc-layout-overflow",
        "getSnapshot",
        "visual_viewport_width",
    ):
        if token not in observer:
            errors.append(f"layout observer contract missing: {token}")
    for forbidden in (
        "fontSize",
        "style.font",
        "style.transform",
        "style.zoom",
        "textContent",
        "innerHTML",
    ):
        if forbidden in observer:
            errors.append(f"layout observer performs forbidden mutation/read: {forbidden}")
    for token in (
        "window.visualViewport",
        "--rmc-viewport-width-px",
        "--rmc-viewport-height-px",
    ):
        if token not in viewport:
            errors.append(f"visual viewport contract missing: {token}")
    for token in ("rmcLayoutObserver", "getSnapshot", "layout: layout"):
        if token not in beacon:
            errors.append(f"RUM layout bridge missing: {token}")
    for token in (
        "LAYOUT_SCHEMA_VERSION = 1",
        "sanitize_layout_observation",
        '_VIEWPORT_CLASSES = frozenset({"A", "B", "C", "U"})',
    ):
        if token not in sanitizer:
            errors.append(f"layout sanitizer contract missing: {token}")
    for token in (
        "js/rmc-layout-observer.js",
        'include "components/rum_beacon.html"',
    ):
        if token not in shell_partial:
            errors.append(f"shell-level layout wiring missing: {token}")

    rum_include_count = 0
    for template in (ROOT / "templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8", errors="ignore")
        rum_include_count += text.count("components/rum_beacon.html")
    if rum_include_count != 1:
        errors.append(
            f"RUM beacon must have one canonical shell include; found {rum_include_count}"
        )

    npm = "npm.cmd" if os.name == "nt" else "npm"
    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.platform_runtime.tests.test_layout_observability",
            "apps.platform_runtime.tests.test_rum_ingest",
            "apps.platform_runtime.tests.test_rum_aggregate",
            "apps.platform_runtime.tests.test_rum_cls_budget",
            "--verbosity=1",
        ],
        [npm, "exec", "--", "vitest", "run", "tests/js/rmc_layout_observer.test.ts"],
        ["node", "--check", "static/js/rmc-layout-observer.js"],
        ["node", "--check", "static/js/rmc-viewport-engine.js"],
        ["node", "--check", "static/js/rum-beacon.js"],
        [sys.executable, "manage.py", "check"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            errors.append(f"verification command failed: {' '.join(command)}")

    if errors:
        print("LAYOUT_OBSERVABILITY_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("LAYOUT_OBSERVABILITY_CONTRACT_PASS schema_version=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
