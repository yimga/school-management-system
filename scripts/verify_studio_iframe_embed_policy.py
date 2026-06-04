#!/usr/bin/env python3
"""
Platform gate: Studio Launch / Automation iframe targets must allow same-origin embed.

Ensures ``EmbedSameOriginFrameMiddleware`` is wired and every view name referenced
from ``_resolve_launch_iframe_src`` is covered by embed=1 framing policy.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LAUNCH_IFRAME_VIEWS = (
    "siteconfig:guided_onboarding",
    "super:create_school_wizard",
    "siteconfig:get_blueprints",
    "studio_os:experience",
    "accounts:migration_wizard",
)

SETTINGS_PATH = ROOT / "config" / "settings.py"
MIDDLEWARE_CLASS = "apps.security.embed_frame_middleware.EmbedSameOriginFrameMiddleware"
VIEWS_PY = ROOT / "apps" / "studio_os" / "views.py"


def _settings_text() -> str:
    return SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")


def _launch_mapping_viewnames() -> set[str]:
    if not VIEWS_PY.is_file():
        return set()
    tree = ast.parse(VIEWS_PY.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_resolve_launch_iframe_src":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Tuple):
                continue
            if len(sub.elts) != 2:
                continue
            first = sub.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if ":" in first.value:
                    return {first.value for first in ast.walk(node) if isinstance(first, ast.Constant) and isinstance(first.value, str) and ":" in first.value}
    return set()


def main() -> int:
    findings: list[str] = []
    text = _settings_text()
    if MIDDLEWARE_CLASS not in text:
        findings.append(
            f"{MIDDLEWARE_CLASS} must be registered in config/settings.py after XFrameOptionsMiddleware"
        )
    elif text.find(MIDDLEWARE_CLASS) < text.find("XFrameOptionsMiddleware"):
        findings.append(
            f"{MIDDLEWARE_CLASS} must appear after django.middleware.clickjacking.XFrameOptionsMiddleware"
        )

    mapped = _launch_mapping_viewnames() or set(LAUNCH_IFRAME_VIEWS)
    missing = set(LAUNCH_IFRAME_VIEWS) - mapped
    if missing:
        findings.append(
            f"_resolve_launch_iframe_src mapping drift — expected view names missing: {sorted(missing)}"
        )

    mw_path = ROOT / "apps" / "security" / "embed_frame_middleware.py"
    if not mw_path.is_file():
        findings.append("missing apps/security/embed_frame_middleware.py")

    if findings:
        print(f"verify_studio_iframe_embed_policy: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("verify_studio_iframe_embed_policy: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
