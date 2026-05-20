#!/usr/bin/env python3
"""
Platform surface layout contract — forensic audit closeout (v3.42.7).

Validates the manager control-plane fixes from the Studio overview forensic audit:
  - AI guided assistant card (no Bootstrap white leak)
  - Document-scroll shell (no 100vh trap on skeleton)
  - Config chip topology (Studio / Operations hide)
  - Ctrl+K owned by command palette (not duplicate in shell manager JS)
  - Studio OS viewport min-height traps removed under document scroll
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "platform_surface_layout_contract.json"


@dataclass
class Row:
    check_id: str
    description: str
    status: str
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _not_contains(rel: str, needle: str) -> bool:
    return needle not in _read(rel)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    add(
        "ai_guided_assistant_semantic",
        "AI guided assistant uses rmc-ai-guided-assistant-card (not Bootstrap .card)",
        _contains("templates/components/ai_guided_assistant_card.html", "rmc-ai-guided-assistant-card")
        and _not_contains("templates/components/ai_guided_assistant_card.html", 'class="card '),
        "ai_guided_assistant_card.html",
    )
    add(
        "ai_guided_assistant_stylesheet",
        "AI assistant stylesheet linked on control-plane skeleton",
        _exists("static/css/rmc-ai-guided-assistant-card.css")
        and _contains("templates/control_plane_skeleton.html", "rmc-ai-guided-assistant-card.css"),
        "control_plane_skeleton.html",
    )
    add(
        "document_scroll_skeleton",
        "Control-plane skeleton uses document scroll contract",
        _contains("templates/control_plane_skeleton.html", 'data-rmc-cp-scroll="document"'),
        "control_plane_skeleton.html",
    )
    add(
        "main_scroll_admin_manager",
        "Manager Unfold admin shell sets data-rmc-cp-scroll=main (viewport-trapped #cp-main-content)",
        _contains("templates/admin/base_site.html", "data-rmc-cp-scroll', 'main'")
        and _contains("templates/admin/base.html", 'data-rmc-cp-scroll="main"'),
        "admin/base_site.html",
    )
    add(
        "document_scroll_portal_manager_bridge",
        "Manager portal bridge body sets data-rmc-cp-scroll=document",
        _contains("templates/portal_base.html", "data-rmc-cp-scroll"),
        "portal_base.html",
    )
    add(
        "no_viewport_height_trap_css",
        "manager-control-plane.css scopes layout to document scroll (no global 100vh trap)",
        _contains("static/css/manager-control-plane.css", '[data-rmc-cp-scroll="document"]')
        and _not_contains(
            "static/css/manager-control-plane.css",
            "body.control-plane-shell {\n  display: flex;\n  flex-direction: column;\n  height: 100vh;",
        ),
        "manager-control-plane.css",
    )
    add(
        "studio_os_min_height_released",
        "Studio OS control-compact min-height trap released under document scroll",
        _contains(
            "static/css/manager-control-plane.css",
            "studio-os[data-studio-density=\"control-compact\"]",
        )
        and _contains("static/css/manager-control-plane.css", "min-height: auto !important"),
        "manager-control-plane.css",
    )
    add(
        "config_chip_topology",
        "Config chip hidden in Studio / Operations via shell_contract + topbar",
        _contains("apps/platform_runtime/shell_contract.py", "manager_header_hide_config_chip")
        and _contains(
            "templates/partials/manager_operator_topbar.html",
            "manager_header_hide_config_chip",
        ),
        "shell_contract + manager_operator_topbar.html",
    )
    add(
        "ctrl_k_palette_ownership",
        "authenticated-shell-manager.js does not bind Ctrl+K (palette owns it)",
        _contains("static/js/authenticated-shell-manager.js", "rmc-command-palette.js")
        and _not_contains(
            "static/js/authenticated-shell-manager.js",
            'e.key === "k"',
        ),
        "authenticated-shell-manager.js",
    )
    add(
        "shell_search_idempotent",
        "Header search wiring is idempotent (no duplicate listeners)",
        _contains(
            "static/js/authenticated-shell-manager.js",
            "data-rmc-shell-search-wired",
        ),
        "authenticated-shell-manager.js",
    )
    add(
        "skeleton_shell_manager_script",
        "authenticated-shell-manager.js loaded once from skeleton",
        _contains("templates/control_plane_skeleton.html", "authenticated-shell-manager.js")
        and _not_contains(
            "templates/control_plane_base.html",
            "authenticated-shell-manager.js",
        ),
        "skeleton only",
    )

    if args.run_tests:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/run_sqlite_memory_tests.py",
                "apps.platform_runtime.tests.test_ai_guided_assistant_card_contract",
                "apps.platform_runtime.tests.test_shell_contract",
                "apps.siteconfig.tests.test_manager_portal_chrome_contract",
                "--verbosity=1",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        add(
            "django_contract_tests",
            "Django contract tests for surface layout",
            proc.returncode == 0,
            (proc.stdout or proc.stderr or "")[-300:],
        )

    failed = [r for r in rows if r.status != "PASS"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PLATFORM_SURFACE_LAYOUT_PASS" if not failed else "PLATFORM_SURFACE_LAYOUT_FAIL",
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": len(failed),
        "rows": [asdict(r) for r in rows],
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failed:
        print(
            f"verify_platform_surface_layout_contract: {payload['verdict']} ({len(failed)} FAIL)",
            file=sys.stderr,
        )
        for r in failed:
            print(f"  - {r.check_id}: {r.proof}", file=sys.stderr)
        return 1

    print(
        f"verify_platform_surface_layout_contract: {payload['verdict']} ({payload['passed']} checks)"
    )
    return 0


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


if __name__ == "__main__":
    raise SystemExit(main())
