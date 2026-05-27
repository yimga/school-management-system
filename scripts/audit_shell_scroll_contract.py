#!/usr/bin/env python3
"""Audit viewport scroll contract across platform shells (canvas vs document)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHELL_TEMPLATES = (
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/base.html",
    "templates/admin/base.html",
    "templates/marketing/base_marketing.html",
)

REQUIRED_CSS = (
    "static/css/rmc-shell-scroll-contract.css",
    "static/css/rmc-isomorphic-grid-sweep.css",
)

RULE_BLOCK = re.compile(r"([^{}]+)\{([^}]*)\}", re.DOTALL)

DOCUMENT_SCROLL_BODY = re.compile(
    r'body\[data-rmc-cp-scroll="document"\]|body\.[^{]*\[data-rmc-cp-scroll="document"\]',
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def audit_css() -> list[str]:
    failures: list[str] = []
    for rel in REQUIRED_CSS:
        if not (ROOT / rel).is_file():
            failures.append(f"missing css: {rel}")

    compact = _read("static/css/rmc-canvas-chrome-compact.css")
    for selector, body in RULE_BLOCK.findall(compact):
        sel = " ".join(selector.split())
        if ".rmc-app-shell__canvas" not in sel:
            continue
        if "canvas-body" in sel:
            continue
        if "document" in sel:
            continue
        if re.search(r"height:\s*auto", body, re.I):
            failures.append(
                "rmc-canvas-chrome-compact.css: height:auto on .rmc-app-shell__canvas "
                f"without document guard ({sel[:96]})"
            )

    sweep = _read("static/css/rmc-isomorphic-grid-sweep.css")
    if "body[data-rmc-cp-scroll=\"document\"]" not in sweep and (
        'body[data-rmc-cp-scroll="document"]' not in sweep
    ):
        failures.append(
            "rmc-isomorphic-grid-sweep.css: missing document-scroll exemption on html/body max-height"
        )

    contract = _read("static/css/rmc-shell-scroll-contract.css")
    if "overflow-y: auto !important" not in contract:
        failures.append("rmc-shell-scroll-contract.css: missing canvas overflow-y:auto repair")
    if "#page:has(.admin-cp-unified-page)" not in contract:
        failures.append("rmc-shell-scroll-contract.css: missing #page admin unwind")

    return failures


def audit_templates() -> list[str]:
    failures: list[str] = []
    for rel in SHELL_TEMPLATES:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "back_to_top.html" not in text:
            failures.append(f"{rel}: missing back_to_top include")
        if "rmc-shell-scroll-contract.css" not in text and rel != "templates/admin/base.html":
            if rel == "templates/admin/base.html":
                site = ROOT / "templates/admin/base_site.html"
                if site.is_file() and "rmc-shell-scroll-contract.css" not in site.read_text(
                    encoding="utf-8", errors="replace"
                ):
                    failures.append("admin shell: missing rmc-shell-scroll-contract.css load")
            else:
                chrome = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
                if not chrome.is_file() or "rmc-shell-scroll-contract.css" not in chrome.read_text(
                    encoding="utf-8", errors="replace"
                ):
                    failures.append(f"{rel}: scroll contract css not wired via chrome partial")

    admin_base = _read("templates/admin/base.html")
    if (
        "</div>\n    {% if is_manager_host %}\n    {% include 'components/back_to_top.html' %}"
        not in admin_base.replace("\r\n", "\n")
    ):
        failures.append(
            "templates/admin/base.html: back-to-top must be outside .rmc-app-shell for manager host"
        )

    btt_js = _read("static/js/_pages/components__back_to_top.js")
    if "ensureBodyMounted" not in btt_js:
        failures.append("components__back_to_top.js: missing ensureBodyMounted()")
    if "THRESHOLD_FOLDS" not in btt_js:
        failures.append("components__back_to_top.js: missing THRESHOLD_FOLDS")
    if "RMCBackToTop" not in btt_js:
        failures.append("components__back_to_top.js: missing RMCBackToTop export")

    btt_tpl = _read("templates/components/back_to_top.html")
    if "rmc-scroll-container.js" not in btt_tpl:
        failures.append("back_to_top.html: must load rmc-scroll-container.js first")
    if "data-rmc-back-to-top-percent" not in btt_tpl:
        failures.append("back_to_top.html: missing scroll progress percent chip")

    fold_js = _read("static/js/rmc-page-fold-standards.js")
    if "RMCBackToTop" not in fold_js:
        failures.append("rmc-page-fold-standards.js: must refresh RMCBackToTop after fold measure")

    return failures


def main() -> int:
    failures = audit_css() + audit_templates()
    if failures:
        print("SHELL_SCROLL_CONTRACT_AUDIT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1
    print("SHELL_SCROLL_CONTRACT_AUDIT_PASS")
    print(f"  shells: {len(SHELL_TEMPLATES)}  css guards: {len(REQUIRED_CSS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
