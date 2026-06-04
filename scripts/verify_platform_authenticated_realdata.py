#!/usr/bin/env python3
"""REALTIME pillar: authenticated surfaces use DB realdata or honest empty — not demo overlays."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_DEMO_PAYLOAD_ALLOW = (
    "apps/siteconfig/cockpit_context.py",
    "apps/siteconfig/cockpit_manager_200x_preview_data.py",
    "apps/siteconfig/cockpit_tenant_v3_preview_data.py",
    "apps/siteconfig/views_cockpit_health.py",
    "scripts/verify_platform_authenticated_realdata.py",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _check_settings_defaults(failures: list[str]) -> None:
    settings = _read("config/settings.py")
    for name in ("COCKPIT_200X_RENDER_PREVIEW_DEMO", "COCKPIT_100X_RENDER_PREVIEW_DEMO"):
        pattern = rf'{name}\s*=\s*os\.getenv\(\s*"{name}",\s*"0"\s*\)'
        if not re.search(pattern, settings):
            failures.append(f"config/settings.py must default {name} env fallback to \"0\"")


def _check_cockpit_merge_order(failures: list[str]) -> None:
    text = _read("apps/siteconfig/cockpit_context.py")
    for helper in ("_manager_cockpit_demo_enabled", "_tenant_cockpit_demo_enabled"):
        if f"def {helper}" not in text:
            failures.append(f"cockpit_context.py missing {helper}()")
    if "_manager_cockpit_demo_enabled(request)" not in text:
        failures.append("manager demo merge must be gated by _manager_cockpit_demo_enabled")
    if "_tenant_cockpit_demo_enabled(request)" not in text:
        failures.append("tenant demo merge must be gated by _tenant_cockpit_demo_enabled")
    manager_demo_idx = text.find("manager_200x_demo_payload()")
    manager_real_idx = text.find("resolve_panel_overrides")
    if manager_demo_idx != -1 and manager_real_idx != -1 and manager_demo_idx < manager_real_idx:
        failures.append("manager realdata must merge before manager_200x_demo_payload")

    panels = _read("apps/siteconfig/cockpit_panels_realdata_service.py")
    if "_honest_empty_panel" not in panels or "include_honest_empty" not in panels:
        failures.append("cockpit_panels_realdata_service must expose honest empty panels")


def _check_demo_payload_call_sites(failures: list[str]) -> None:
    for path in ROOT.glob("apps/**/*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("apps/siteconfig/tests/") or rel.startswith("apps/portal/tests/"):
            continue
        text = path.read_text(encoding="utf-8")
        if "manager_200x_demo_payload()" in text and rel not in _DEMO_PAYLOAD_ALLOW:
            failures.append(f"manager_200x_demo_payload() outside preview modules: {rel}")
        if "tenant_v3_extended_demo_payload()" in text and rel not in _DEMO_PAYLOAD_ALLOW:
            failures.append(f"tenant_v3_extended_demo_payload() outside preview modules: {rel}")


def _run_tests(py: str, failures: list[str]) -> None:
    labels = [
        "apps.siteconfig.tests.test_cockpit_activity_ticker_realdata",
        "apps.siteconfig.tests.test_cockpit_tenant_v3_realdata",
        "apps.portal.tests.test_tenant_cockpit_realdata",
    ]
    runner = ROOT / "scripts" / "run_sqlite_memory_tests.py"
    cmd = [py, str(runner), *labels, "--verbosity=1"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-500:]
        failures.append(f"realdata Django tests failed: {tail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    _check_settings_defaults(failures)
    _check_cockpit_merge_order(failures)
    _check_demo_payload_call_sites(failures)
    if not args.skip_tests:
        _run_tests(sys.executable, failures)

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(
            f"verify_platform_authenticated_realdata: {len(failures)} FAIL",
            file=sys.stderr,
        )
        return 1

    print("PLATFORM_AUTHENTICATED_REALDATA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
