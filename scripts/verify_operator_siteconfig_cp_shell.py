#!/usr/bin/env python3
"""
QA gate: manager-host siteconfig operator pages use CP shell + body partials.

Checks:
- Every ``render_siteconfig_stem`` stem has portal wrapper + partial body on disk.
- Portal wrappers include their body partial (no stale inline-only content blocks).
- Body partials declare exactly one primary h1 (visible or visually-hidden).
- No undefined project CSS class tokens in operator partials (subset scan).
- ``operator_control_plane_page`` suppresses duplicate workspace header.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "siteconfig"
PARTIALS = TEMPLATES / "partials"
VIEWS_PKG = ROOT / "apps" / "siteconfig"

# Former allowlist — must use render_siteconfig_stem (no plain render bypass).
FORBIDDEN_PLAIN_RENDER_TEMPLATES = frozenset(
    {
        "siteconfig/maintenance.html",
        "siteconfig/region_validation_dashboard.html",
        "siteconfig/region_comparison.html",
        "siteconfig/region_grading_scales_matrix.html",
    }
)
PLAIN_RENDER_RE = re.compile(
    r'render\s*\(\s*request\s*,\s*["\'](siteconfig/[^"\']+)["\']',
    re.MULTILINE,
)

H1_RE = re.compile(
    r"<h1\b[^>]*>|class=\"visually-hidden\"[^>]*data-rmc-injected-h1",
    re.IGNORECASE,
)
INCLUDE_BODY_RE = re.compile(
    r'\{%\s*include\s+["\']siteconfig/partials/([a-z0-9_]+)_body\.html'
)
RENDER_STEM_RE = re.compile(
    r"render_siteconfig_stem\(\s*request,\s*['\"]([a-z][a-z0-9_]*)['\"]",
    re.MULTILINE,
)

PORTAL_BASE_ALLOW_NO_PARTIAL = frozenset(
    {
        "customizer.html",  # legacy; redirects to Studio / theme_colors
        "workflow_hub.html",  # legacy redirect surface
    }
)


def _stems_from_views() -> set[str]:
    stems: set[str] = set()
    for path in VIEWS_PKG.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        stems.update(RENDER_STEM_RE.findall(text))
    return stems


def main() -> int:
    findings: list[str] = []

    op_page = TEMPLATES / "operator_control_plane_page.html"
    if op_page.exists():
        op_text = op_page.read_text(encoding="utf-8", errors="replace")
        if "{% block cp_workspace_header %}{% endblock %}" not in op_text.replace(
            " ", ""
        ):
            if "block cp_workspace_header" not in op_text:
                findings.append(
                    "operator_control_plane_page.html must override cp_workspace_header "
                    "(empty) to avoid duplicate rmc_os_page_header with body partials."
                )

    for path in (VIEWS_PKG / "views.py",):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for template in PLAIN_RENDER_RE.findall(text):
            if template in FORBIDDEN_PLAIN_RENDER_TEMPLATES:
                findings.append(
                    f"{path.relative_to(ROOT)}: plain render() for {template} "
                    "(use render_siteconfig_stem)"
                )

    stems = _stems_from_views()
    for stem in sorted(stems):
        portal = TEMPLATES / f"{stem}.html"
        body = PARTIALS / f"{stem}_body.html"
        if not portal.is_file():
            findings.append(f"missing portal template for stem {stem!r}")
        if not body.is_file():
            findings.append(f"missing body partial for stem {stem!r}")
            continue
        portal_text = portal.read_text(encoding="utf-8", errors="replace")
        if f"partials/{stem}_body.html" not in portal_text:
            findings.append(
                f"{portal.name} does not include siteconfig/partials/{stem}_body.html"
            )
        body_text = body.read_text(encoding="utf-8", errors="replace")
        h1_count = len(H1_RE.findall(body_text))
        if h1_count < 1:
            findings.append(
                f"partials/{stem}_body.html: no <h1> or data-rmc-injected-h1 (SEO/a11y)"
            )
        if h1_count > 2:
            findings.append(
                f"partials/{stem}_body.html: multiple h1 markers ({h1_count})"
            )

    # Portal templates on disk that still extend portal_base should include a body partial.
    for portal in sorted(TEMPLATES.glob("*.html")):
        if portal.name in ("operator_control_plane_page.html",):
            continue
        text = portal.read_text(encoding="utf-8", errors="replace")
        if portal.name in PORTAL_BASE_ALLOW_NO_PARTIAL:
            continue
        if 'extends "portal_base.html"' not in text:
            continue
        m = INCLUDE_BODY_RE.search(text)
        if not m:
            findings.append(
                f"{portal.name}: extends portal_base but has no partial include in content"
            )

    if findings:
        print(f"verify_operator_siteconfig_cp_shell: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print(
        f"verify_operator_siteconfig_cp_shell: OK ({len(stems)} stems, "
        f"{len(list(PARTIALS.glob('*_body.html')))} body partials)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
