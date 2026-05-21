#!/usr/bin/env python3
"""
Inventory inline <style> blocks in templates/ for Phase 1–2 drift tracking.

Exempt categories (intentional):
- emails/, finance/receipt.html, reports PDF / _report_styles, noscript, data-site-custom-css,
  admin-brand-resolved-tokens, mock previews, offline/auth one-offs (optional tighten over time).

Exit 0 always (reporting only). Run: python scripts/report_template_inline_styles.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"

# Entire-file <style> is Django-injected admin / dashboard theme :root (cannot live in static CSS).
PHASE2_SERVER_THEME_STYLE_FILES = frozenset(
    {
        "templates/admin/index.html",
        "templates/admin/index_tenant.html",
        "templates/admin/admin_dashboard.html",
        "templates/accounts/backend_dashboard.html",
        "templates/customersuccess/guided_onboarding.html",
    }
)

EXEMPT_SUBSTRINGS = (
    "templates/emails/",
    "templates/emails\\",
    "report_ready_",
    "base_branded.html",
    "finance/receipt.html",
    "reports/_report_styles.html",
    "reports/term_report",
    "reports/annual_report",
    "siteconfig/report_table_pdf.html",
    "mock_reportcard_preview.html",
    "data-site-custom-css",
    "admin-brand-resolved-tokens",
    "<noscript><style>",
    "offline.html",
)


def _is_exempt(rel: str, snippet: str) -> bool:
    rel.replace("\\", "/") + " " + snippet[:200].lower()
    if "noscript" in snippet.lower() and "<style" in snippet.lower():
        return True
    for x in EXEMPT_SUBSTRINGS:
        if x.lower() in (rel.replace("\\", "/") + snippet).lower():
            return True
    return False


def _strip_html_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def _block_exempt(rel: str, block_inner: str) -> bool:
    b = block_inner.lower()
    if "data-site-custom-css" in b:
        return True
    if "theme_root_variables" in b:
        return True
    if "root-base-theme-vars" in b:
        return True
    if "admin-brand-resolved-tokens" in b:
        return True
    if "badge-verify-theme-vars" in b:
        return True
    if "reportcard-preview-theme-vars" in b:
        return True
    return _is_exempt(rel, block_inner)


def main() -> int:
    if not TEMPLATES.is_dir():
        print("No templates/", file=sys.stderr)
        return 1

    style_re = re.compile(r"<style\b[^>]*>", re.I)
    files_with_style: list[tuple[str, int, bool]] = []

    for p in sorted(TEMPLATES.rglob("*.html")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        text = _strip_html_comments(raw)
        matches = list(style_re.finditer(text))
        if not matches:
            continue
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        if rel in PHASE2_SERVER_THEME_STYLE_FILES:
            files_with_style.append((rel, len(matches), True))
            continue
        exempt_count = 0
        for m in matches:
            end = text.find("</style>", m.start())
            open_tag = text[m.start() : m.end()]
            inner = text[m.end() : end] if end != -1 else ""
            if _block_exempt(rel, open_tag + inner):
                exempt_count += 1
        files_with_style.append((rel, len(matches), exempt_count == len(matches)))

    flagged = [f for f in files_with_style if not f[2]]
    exempt_only = [f for f in files_with_style if f[2]]

    print("Template inline <style> inventory")
    print(f"  Total .html files with <style>: {len(files_with_style)}")
    print(f"  Flagged (non-exempt blocks): {len(flagged)}")
    print(f"  Exempt-only files: {len(exempt_only)}")
    print()
    print("--- Flagged (migrate to static/css or document) ---")
    for rel, n, _ in sorted(flagged):
        print(f"  {n}x  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
