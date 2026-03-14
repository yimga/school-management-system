#!/usr/bin/env python3
"""
Phase H — Full codebase and live UX verification audit.

RUNMYCAMPUS §11 Phase H: Links, buttons, shortcuts, dashboards, no 404/500,
responsive layout, in-frame, well-labeled. This script performs static and
optional runtime checks to support the Phase H completion gate.

Usage:
  python scripts/phase_h_audit.py              # static checks only (no Django)
  python scripts/phase_h_audit.py --live       # static + URL reverse checks (requires Django)
  python scripts/phase_h_audit.py --verbose    # print each check performed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"


def check_viewport_and_frame(failures: list[str], verbose: bool = False) -> None:
    """Require viewport meta and overflow containment in base shells (Phase H responsive gate)."""
    # Base shell used by tenant/auth pages
    base = TEMPLATES / "base.html"
    if verbose:
        print("  check: base.html viewport and overflow")
    if not base.exists():
        failures.append("templates/base.html missing")
        return
    text = base.read_text(encoding="utf-8", errors="replace")
    if "viewport" not in text and "width=device-width" not in text:
        failures.append("base.html: missing viewport meta (required for responsive)")
    if "overflow" not in text and "app-container" not in text:
        failures.append("base.html: missing overflow containment or .app-container (frame check)")

    # Control plane shell (manager / super / admin)
    cp = TEMPLATES / "control_plane_skeleton.html"
    if verbose:
        print("  check: control_plane_skeleton.html viewport and overflow")
    if not cp.exists():
        failures.append("templates/control_plane_skeleton.html missing")
    else:
        cp_text = cp.read_text(encoding="utf-8", errors="replace")
        if "viewport" not in cp_text and "width=device-width" not in cp_text:
            failures.append("control_plane_skeleton.html: missing viewport meta")
        if "overflow" not in cp_text:
            failures.append("control_plane_skeleton.html: missing overflow containment")


def check_skip_links(failures: list[str], verbose: bool = False) -> None:
    """Require skip-to-main link in base shells (Phase H accessibility / well-labeled)."""
    if verbose:
        print("  check: skip-link in base shells")
    for label, path in (
        ("base.html", TEMPLATES / "base.html"),
        ("control_plane_skeleton.html", TEMPLATES / "control_plane_skeleton.html"),
    ):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if "skip" not in text or ("main" not in text and "content" not in text):
            failures.append(f"{label}: missing skip-to-main-content link (a11y)")


def check_error_templates(failures: list[str], verbose: bool = False) -> None:
    """Require 403/404/500 templates (tenant + control-plane) and that they extend a base."""
    if verbose:
        print("  check: error templates (tenant + control-plane)")
    errors_dir = TEMPLATES / "errors"
    # Tenant-facing error pages
    for name in ("403.html", "404.html", "500.html"):
        path = errors_dir / name
        if not path.exists():
            failures.append(f"templates/errors/{name} missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "extends" not in text:
            failures.append(f"errors/{name}: should extend base or control-plane template")
    # Control-plane error pages (manager host: config.urls uses these when public_host_kind == 'manager')
    for name in ("403_control_plane.html", "404_control_plane.html", "500_control_plane.html"):
        path = errors_dir / name
        if not path.exists():
            failures.append(f"templates/errors/{name} missing (required for manager host)")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "extends" not in text:
            failures.append(f"errors/{name}: should extend control_plane_skeleton or base")


def check_responsive_css(
    failures: list[str], warnings: list[str], verbose: bool = False
) -> None:
    """Ensure key responsive/fluid assets exist; report missing as warnings (Phase H responsive)."""
    candidates = [
        "css/platform-responsive-touch.css",
        "css/dashboard-responsive.css",
        "css/accessibility.css",
    ]
    if verbose:
        print("  check: responsive/accessibility CSS assets")
    for rel in candidates:
        path = STATIC / rel
        if not path.exists():
            warnings.append(f"static/{rel} missing (recommended for responsive/a11y)")


def run_url_reverse_checks(failures: list[str], verbose: bool = False) -> None:
    """Run Django URL reverse for Phase H critical names; requires Django."""
    if verbose:
        print("  check: URL reverse for critical names")
    import os
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.urls import reverse, NoReverseMatch

    critical = [
        "home",
        "health",
        "healthz",
        "accounts:login",
        "accounts:backend_dashboard",
        "portal:parent_dashboard",
        "finance:dashboard",
        "analytics:dashboard",
        "compliance:dashboard",
        "evals:teacher_dashboard",
        "payroll:dashboard",
        "automation:outcomes_console",
        "communication:group_list",
        "requests:dashboard",
        "academics:teacher_syllabus_hub",
        "studio_os:shell",
        "studio_os:experience",
        "studio_os:automation",
        "studio_os:output",
        "studio_os:launch",
        "studio_os:control",
        "super:dashboard",
        "siteconfig:console_domains_hub",
        "marketing_landing",
        "public_support_hub",
        "public_verify_hub",
        "global_login_discovery",
    ]
    for name in critical:
        try:
            reverse(name)
        except NoReverseMatch as e:
            failures.append(f"URL reverse({name!r}): {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase H UX verification audit (RUNMYCAMPUS §11 Phase H)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run URL reverse checks (requires Django)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each check performed",
    )
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []
    if args.verbose:
        print("Phase H audit: running static checks...")
    check_viewport_and_frame(failures, verbose=args.verbose)
    check_skip_links(failures, verbose=args.verbose)
    check_error_templates(failures, verbose=args.verbose)
    check_responsive_css(failures, warnings, verbose=args.verbose)
    if args.live:
        if args.verbose:
            print("Phase H audit: running live URL reverse checks...")
        run_url_reverse_checks(failures, verbose=args.verbose)

    if failures:
        print("Phase H audit FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    # Always report warnings (recommended responsive/a11y assets) so CI and logs surface them
    if warnings:
        for w in warnings:
            print(f"  warning: {w}", file=sys.stderr)
    mode = "static + live" if args.live else "static"
    print(f"Phase H audit ({mode}) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
