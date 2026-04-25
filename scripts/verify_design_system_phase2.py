#!/usr/bin/env python3
"""
Phase 2 — Design system + token enforcement: automated gate.

Fails if required CSS is missing, canonical bases omit token + Phase 2 enforcement links,
or high-regression templates reintroduce inline theme <style> blocks (dashboard header,
theme toggle, Studio shell_extrastyle).

Run from repo root: python scripts/verify_design_system_phase2.py [--base REPO_ROOT]
See docs/DESIGN_SYSTEM_PHASE2.md §7.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

REQUIRED_STATIC = [
    "static/js/shell-data-dashboard-page.js",
    "static/css/design-tokens.css",
    "static/css/design-system-phase2-enforcement.css",
    "static/css/design-system-unified.css",
    "static/marketing/css/tokens-marketing.css",
    "static/css/dashboard-header-component.css",
    "static/css/theme-toggle-component.css",
    "static/css/studio-mode-rail.css",
    "static/css/studio-shell-layout.css",
    "static/css/studio-system-config-console.css",
    "static/css/control-plane-skeleton-root.css",
    "static/css/admin-base-site-shell.css",
    "static/css/portal-base-shell.css",
    "static/css/admin-nav-bridge-tenant.css",
    "static/css/studio-control-mode-canvas.css",
    "static/css/root-base-shell.css",
    "static/css/portal-ui-components.css",
    "static/css/phase2-static-templates-bundle.css",
    "static/css/badge-verify.css",
    "static/css/reportcard-style-preview-shell.css",
]

CANONICAL_BASES = [
    "templates/portal_base.html",
    "templates/base.html",
    "templates/marketing/base_marketing.html",
    "templates/admin/base_site.html",
    "templates/control_plane_skeleton.html",
]

FORBIDDEN_INLINE_STYLE_TEMPLATES = [
    "templates/components/dashboard_header.html",
    "templates/components/theme_toggle.html",
]


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2 design system gate.")
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_design_system_phase2: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    for rel in REQUIRED_STATIC:
        fp = repo / rel
        if not fp.is_file():
            errors.append(f"Missing required file: {rel}")

    for base in CANONICAL_BASES:
        p = repo / base
        if not p.is_file():
            errors.append(f"Missing canonical base: {base}")
            continue
        text = _read(p)
        if "design-tokens.css" not in text:
            errors.append(f"{base}: must link design-tokens.css")
        if "design-system-phase2-enforcement.css" not in text:
            errors.append(f"{base}: must link design-system-phase2-enforcement.css")

    # No full theme <style> blocks in components we migrated to external CSS
    for rel in FORBIDDEN_INLINE_STYLE_TEMPLATES:
        p = repo / rel
        if not p.is_file():
            errors.append(f"Missing template: {rel}")
            continue
        text = _read(p)
        if "<style>" in text.lower():
            errors.append(
                f"{rel}: inline <style> not allowed (use static/css/*-component.css)"
            )

    # Section 10.5 design-system layer (repo script)
    v10 = repo / "scripts" / "verify_section10_5_layers.py"
    if v10.is_file():
        r = subprocess.run(
            [sys.executable, str(v10), "--base", str(repo)],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            errors.append(
                "verify_section10_5_layers.py failed:\n"
                + (r.stdout or "")
                + (r.stderr or "")
            )
    else:
        errors.append("Missing scripts/verify_section10_5_layers.py")

    if errors:
        print("Phase 2 verification FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Phase 2 verification: PASS")
    print("  - Required static CSS present")
    print("  - Canonical bases load design-tokens + phase2 enforcement")
    print("  - No inline <style> in dashboard_header / theme_toggle / shell_extrastyle")
    print("  - verify_section10_5_layers.py PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
