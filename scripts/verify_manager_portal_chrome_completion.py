#!/usr/bin/env python3
"""
Manager corporate footer + tenant portal chrome completion gate.

Verifies:
- manager.runmycampus.com shells emit the corporate gateway footer (skeleton-wide)
- Tenant portal_base never includes marketing corporate footer
- Portal chrome resolver + variants wired for ThemePack / DashboardPack
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
GENERATED = ROOT / "docs" / "generated" / "manager_portal_chrome_audit.json"


@dataclass
class Row:
    area: str
    check_id: str
    description: str
    status: str
    proof: str


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8")


def _not_contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle not in path.read_text(encoding="utf-8")


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-400:] if out else ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    py = sys.executable
    rows: list[Row] = []

    def add(area: str, check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(area, check_id, description, "PASS" if ok else "FAIL", proof))

    # --- Manager corporate footer ---
    add(
        "manager",
        "skeleton_footer",
        "control_plane_skeleton uses compact operator footer (not marketing bundle)",
        _contains("templates/control_plane_skeleton.html", "cp-corporate-footer")
        and _contains(
            "templates/control_plane_skeleton.html",
            "rmc_operator_footer_compact.html",
        )
        and _not_contains(
            "templates/control_plane_skeleton.html",
            "corporate_footer_bundle.html",
        ),
        "control_plane_skeleton.html",
    )
    add(
        "manager",
        "login_footer_override",
        "Login pages suppress duplicate skeleton footer",
        _contains("templates/auth/manager_login.html", "block cp_shell_footer")
        and _contains("templates/auth/admin_login.html", "block cp_shell_footer"),
        "manager_login + admin_login",
    )
    add(
        "manager",
        "login_compact_footer",
        "Sign-in uses compact operator footer (not full marketing mega-footer)",
        _contains("templates/partials/rmc_operator_footer_compact.html", "rmc-manager-login-footer")
        and _contains("templates/auth/manager_login.html", "manager_login_footer.html")
        and _not_contains("templates/auth/manager_login.html", "corporate_footer_bundle.html")
        and _exists("static/css/rmc-footer-surfaces.css"),
        "rmc_operator_footer_compact.html + rmc-footer-surfaces.css",
    )
    add(
        "manager",
        "context_flag",
        "SHOW_MANAGER_CORPORATE_FOOTER on manager host",
        _contains(
            "apps/siteconfig/context_processors.py",
            'ctx["SHOW_MANAGER_CORPORATE_FOOTER"] = public_host_kind == "manager"',
        ),
        "context_processors.py",
    )
    add(
        "manager",
        "footer_css",
        "Manager corporate footer stylesheet exists",
        _exists("static/css/manager-corporate-footer.css"),
        "manager-corporate-footer.css",
    )
    add(
        "manager",
        "platform_shell_wrapper",
        "Skeleton wraps all manager pages in cp-shell-content + cp_shell_page",
        _contains("templates/control_plane_skeleton.html", "cp_shell_page")
        and _contains("templates/control_plane_skeleton.html", "cp_shell_footer")
        and _contains("templates/control_plane_base.html", "block cp_shell_page"),
        "control_plane_skeleton + control_plane_base",
    )
    add(
        "manager",
        "footer_inside_shell_css",
        "Footer layout CSS avoids viewport-shrink (no min-height 100vh on shell)",
        _exists("static/css/manager-corporate-footer.css")
        and _not_contains("static/css/manager-corporate-footer.css", "min-height: 100vh"),
        "manager-corporate-footer.css",
    )
    add(
        "manager",
        "horizontal_nav_rail_css",
        "Platform horizontal nav rail grammar stylesheet",
        _exists("static/css/rmc-horizontal-nav-rail.css"),
        "rmc-horizontal-nav-rail.css",
    )
    add(
        "manager",
        "horizontal_nav_rail_wired",
        "All major shells load horizontal nav rail CSS",
        all(
            _contains(rel, "rmc-horizontal-nav-rail.css")
            for rel in (
                "templates/control_plane_skeleton.html",
                "templates/portal_base.html",
                "templates/base.html",
                "templates/admin/base_site.html",
            )
        ),
        "skeleton + portal + base + admin",
    )
    add(
        "manager",
        "horizontal_nav_rail_templates",
        "Primary + workspace nav templates use rail grammar",
        _contains("templates/partials/control_plane_primary_nav.html", "rmc-horizontal-nav-rail")
        and _contains(
            "templates/components/rmc_operator_surface_strip.html",
            "rmc-operator-workspace-nav__spine-item",
        )
        and _contains(
            "apps/schools/super_admin_paired_surfaces.py",
            "def _operator_spine_link_is_active",
        ),
        "primary_nav + surface_strip + paired_surfaces",
    )
    add(
        "manager",
        "horizontal_nav_rail_fast_tests",
        "Fast SimpleTestCase contract module present",
        _exists("apps/schools/tests/test_horizontal_nav_rail.py"),
        "test_horizontal_nav_rail.py",
    )
    add(
        "manager",
        "skeleton_footer_contract_test",
        "Template contract: skeleton emits compact operator footer when flagged",
        _contains(
            "apps/siteconfig/tests/test_manager_portal_chrome_contract.py",
            "test_control_plane_skeleton_wires_compact_operator_footer",
        ),
        "test_manager_portal_chrome_contract",
    )
    footer_gate_code, footer_gate_tail = _run(
        [py, "scripts/verify_footer_surface_contract.py", "--write"],
        timeout=120,
    )
    add(
        "platform",
        "footer_surface_gate",
        "Platform footer surface contract (59-check template sweep)",
        footer_gate_code == 0,
        footer_gate_tail or "verify_footer_surface_contract.py",
    )
    add(
        "platform",
        "footer_surface_tests_module",
        "Footer surface Django contract tests present",
        _exists("apps/siteconfig/tests/test_footer_surface_contract.py"),
        "test_footer_surface_contract.py",
    )

    # --- Tenant isolation ---
    add(
        "tenant",
        "portal_no_marketing_footer",
        "portal_base does not include marketing corporate footer",
        _not_contains("templates/portal_base.html", "corporate_footer_bundle.html")
        and _not_contains("templates/portal_base.html", "marketing_footer.html"),
        "portal_base.html",
    )
    add(
        "tenant",
        "portal_chrome_resolver",
        "Portal chrome resolver module",
        _exists("apps/siteconfig/portal_chrome.py"),
        "portal_chrome.py",
    )
    add(
        "tenant",
        "dashboard_template_chrome_wire",
        "TenantLayoutAssignment template chrome wired in context processor",
        _contains(
            "apps/siteconfig/context_processors.py",
            "resolve_dashboard_template_for_request",
        )
        and _contains(
            "apps/siteconfig/portal_chrome.py",
            "def resolve_dashboard_template_for_request",
        ),
        "context_processors + portal_chrome",
    )
    add(
        "tenant",
        "dashboard_hub_chrome_column",
        "Dashboard configuration hub shows portal chrome per role",
        _contains(
            "templates/siteconfig/partials/dashboard_configuration_hub_body.html",
            "Portal chrome",
        ),
        "dashboard_configuration_hub_body.html",
    )
    add(
        "tenant",
        "portal_footer_partial",
        "portal_base uses PORTAL_FOOTER_PARTIAL include",
        _contains("templates/portal_base.html", "PORTAL_FOOTER_PARTIAL"),
        "portal_base.html",
    )
    add(
        "tenant",
        "portal_header_variant",
        "portal_base exposes data-portal-header-variant",
        _contains("templates/portal_base.html", "data-portal-header-variant"),
        "portal_base.html",
    )
    add(
        "tenant",
        "portal_chrome_css",
        "Portal chrome variant CSS",
        _exists("static/css/portal-chrome-variants.css"),
        "portal-chrome-variants.css",
    )
    add(
        "tenant",
        "minimal_footer_partial",
        "School-scoped minimal footer partial",
        _exists("templates/components/portal_footers/minimal.html"),
        "portal_footers/minimal.html",
    )
    add(
        "tenant",
        "tenant_no_manager_footer_flag",
        "Corporate marketing footer gated off tenant schools",
        _contains(
            "apps/siteconfig/context_processors.py",
            "public_host_kind == \"manager\" and not school",
        ),
        "SHOW_CORPORATE_MARKETING_FOOTER gate",
    )
    add(
        "manager",
        "header_account_menu",
        "Manager header search alignment + account dropdown routes",
        _contains("static/css/rmc-platform-header.css", "--rmc-header-control-height")
        and _contains("templates/partials/manager_operator_topbar.html", "rmc-platform-header__toolbar")
        and _contains("templates/partials/manager_operator_topbar.html", 'lockup_layout="inline"')
        and _contains("templates/components/ai_guided_assistant_card.html", "rmc-ai-guided-assistant-card")
        and _exists("static/css/rmc-ai-guided-assistant-card.css")
        and _contains("templates/control_plane_skeleton.html", 'data-rmc-cp-scroll="document"')
        and _contains("apps/schools/middleware.py", "/authentication/documentation/")
        and _contains("templates/components/user_dropdown.html", "manager_help_center")
        and _contains("templates/components/user_dropdown.html", "kb:kb_home")
        and _exists("apps/accounts/operator_account_render.py"),
        "rmc-platform-header + middleware + user_dropdown + operator_account_render",
    )

    if args.run_tests:
        code, tail = _run(
            [
                py,
                "scripts/run_sqlite_memory_tests.py",
                "apps.schools.tests.test_horizontal_nav_rail",
                "apps.siteconfig.tests.test_portal_chrome",
                "apps.siteconfig.tests.test_manager_portal_chrome_contract",
                "apps.siteconfig.tests.test_footer_surface_contract",
                "apps.schools.tests.test_super_admin_surface_parity.SuperAdminSurfaceParityTests.test_manager_admin_login_public_chrome",
                "apps.schools.tests.test_super_admin_surface_parity.SuperAdminSurfaceParityTests.test_super_dashboard_includes_horizontal_nav_rail_stylesheet",
                "apps.schools.tests.test_manager_header_account_paths",
                "--verbosity=1",
            ],
            timeout=900,
        )
        add(
            "proof",
            "django_tests",
            "Nav rail + footer surface + manager HTTP chrome tests",
            code == 0,
            tail or "ok",
        )

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "MANAGER_PORTAL_CHROME_PASS" if not failed else "MANAGER_PORTAL_CHROME_FAIL",
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": len(failed),
        "rows": [asdict(r) for r in rows],
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for row in failed:
        print(
            f"FAIL [{row.area}] {row.check_id}: {row.description} — {row.proof}",
            file=sys.stderr,
        )

    if failed:
        print(f"verify_manager_portal_chrome_completion: {len(failed)} FAIL", file=sys.stderr)
        return 1

    print(
        f"verify_manager_portal_chrome_completion: {payload['verdict']} ({payload['passed']} checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
