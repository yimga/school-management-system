#!/usr/bin/env python3
"""
Extract ONLY purely static <style> blocks (no Django {{ or {%) from templates into
static/css/phase2-static-templates-bundle.css and remove those blocks from the HTML.

Safe for Phase 2: dynamic theme CSS must stay in templates.

Usage (repo root): python scripts/extract_template_styles_phase2.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
OUT = REPO / "static" / "css" / "phase2-static-templates-bundle.css"

EXEMPT_PATH_PARTS = (
    "templates/emails/",
    "emails\\",
    "finance/receipt",
    "reports/_report_styles",
    "reports/term_report",
    "reports/annual_report",
    "report_table_pdf",
    "mock_reportcard_preview",
    "base_branded",
    "report_ready_",
)

SKIP_PREFIXES = (
    "templates/components/",  # consolidated in portal-ui-components.css
)


def exempt_file(rel: str) -> bool:
    r = rel.replace("\\", "/").lower()
    for x in EXEMPT_PATH_PARTS:
        if x.lower() in r:
            return True
    return False


def skip_file(rel: str) -> bool:
    r = rel.replace("\\", "/")
    return any(r.startswith(p.replace("\\", "/")) for p in SKIP_PREFIXES)


def exempt_block(open_tag: str, inner: str) -> bool:
    t = (open_tag + inner).lower()
    if "data-site-custom-css" in t:
        return True
    if "theme_root_variables" in t:
        return True
    if "admin-brand-resolved-tokens" in t:
        return True
    if "root-base-theme-vars" in t:
        return True
    return False


def is_static_css(inner: str) -> bool:
    s = inner.strip()
    if not s:
        return False
    if "{{" in s or "{%" in s:
        return False
    return True


def main() -> int:
    style_inner = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.DOTALL)

    bundle: list[str] = [
        "/**",
        " * Phase 2 — static-only template <style> blocks (no Django tags).",
        " * Regenerate: python scripts/extract_template_styles_phase2.py",
        " */",
        "",
    ]
    stripped_files: list[tuple[str, int]] = []

    for p in sorted(TEMPLATES.rglob("*.html")):
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        if exempt_file(rel) or skip_file(rel):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        text_nc = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        if "<style" not in text_nc.lower():
            continue

        matches = list(style_inner.finditer(text))
        if not matches:
            continue

        static_blocks: list[str] = []
        to_remove: list[tuple[int, int]] = []
        for m in matches:
            open_end = text.index(">", m.start()) + 1
            open_tag = text[m.start() : open_end]
            inner = m.group(1)
            if exempt_block(open_tag, inner):
                continue
            if not is_static_css(inner):
                continue
            end_full = text.find("</style>", m.start())
            if end_full == -1:
                continue
            end_full += len("</style>")
            static_blocks.append(inner.strip())
            to_remove.append((m.start(), end_full))

        if not to_remove:
            continue

        bundle.append(f"/* ========== {rel} ========== */")
        for i, ch in enumerate(static_blocks):
            if len(static_blocks) > 1:
                bundle.append(f"/* block {i + 1} */")
            bundle.append(ch)
            bundle.append("")

        to_remove.sort(key=lambda x: x[0], reverse=True)
        new_text = text
        for start, end in to_remove:
            new_text = new_text[:start] + new_text[end:]
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        p.write_text(new_text.strip() + "\n", encoding="utf-8")
        stripped_files.append((rel, len(to_remove)))

    OUT.write_text("\n".join(bundle).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} — stripped {len(stripped_files)} files")
    for rel, n in stripped_files:
        print(f"  {n}  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
