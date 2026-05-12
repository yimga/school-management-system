#!/usr/bin/env python3
"""Extract purely static <style> blocks from templates into per-shell phase2 bundles.

Bundles produced (one per base shell):
  static/css/phase2-portal-bundle.css        (portal_base / backend_base templates)
  static/css/phase2-base-bundle.css          (templates extending base.html or no extends)
  static/css/phase2-admin-bundle.css         (admin / Unfold templates)
  static/css/phase2-control-plane-bundle.css (manager.runmycampus.com control-plane templates)
  static/css/phase2-studio-bundle.css        (studio_os templates)

Marketing is intentionally carved out into static/css/marketing-static-bundle.css and
is NOT touched by this script.

Behaviour:
  - Walks templates/, finds <style> blocks with no Django tags ({{ or {%).
  - Routes each block to the per-shell bundle owning that template, by walking the
    {% extends %} chain (with directory + Unfold fallbacks).
  - Merges with existing per-shell bundle content: a template's extracted block replaces
    any prior section for the same template; templates without new inline blocks keep
    their existing bundled sections untouched.
  - Strips the extracted <style> blocks from the source templates so they don't ship inline.

Safe for Phase 2: dynamic theme CSS (containing {{ or {%) stays in templates.

Usage (repo root): python scripts/extract_template_styles_phase2.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
CSS_DIR = REPO / "static" / "css"

BUNDLE_KEYS = ("portal", "base", "admin", "control-plane")

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
    "templates/marketing/",
    "templates/schools/marketing_",
)

SKIP_PREFIXES = ("templates/components/", "templates/studio_os/components/")

SHELL_TO_BUNDLE = {
    "portal_base.html": "portal",
    "backend_base.html": "portal",
    "base.html": "base",
    "admin/base_site.html": "admin",
    "control_plane_skeleton.html": "control-plane",
    "control_plane_base.html": "control-plane",
}

MANUAL_OVERRIDES: dict[str, tuple[str, ...]] = {
    "templates/siteconfig/feature_control_panel_content.html": ("portal",),
    "templates/siteconfig/partials/reportcard_builder_inner.html": ("portal",),
    "templates/siteconfig/partials/theme_colors_page_body.html": ("portal", "control-plane"),
}

DIR_FALLBACKS = (
    ("templates/admin/", "admin"),
    ("templates/control_plane", "control-plane"),
    ("templates/siteconfig/console_domains", "control-plane"),
    ("templates/studio_os/", "portal"),
)

EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']\s*%}', re.I)
HEADER_RE = re.compile(r"^/\* =+ (.+?) =+ \*/\s*$", re.M)


def exempt_file(rel: str) -> bool:
    r = rel.replace("\\", "/").lower()
    return any(x.lower() in r for x in EXEMPT_PATH_PARTS)


def skip_file(rel: str) -> bool:
    r = rel.replace("\\", "/")
    return any(r.startswith(p) for p in SKIP_PREFIXES)


def exempt_block(open_tag: str, inner: str) -> bool:
    t = (open_tag + inner).lower()
    return any(
        marker in t
        for marker in (
            "data-site-custom-css",
            "theme_root_variables",
            "admin-brand-resolved-tokens",
            "root-base-theme-vars",
        )
    )


def is_static_css(inner: str) -> bool:
    s = inner.strip()
    return bool(s) and "{{" not in s and "{%" not in s


def directory_fallback(rel: str) -> str | None:
    norm = rel.replace("\\", "/")
    if not norm.startswith("templates/"):
        norm = f"templates/{norm}"
    for prefix, bundle_key in DIR_FALLBACKS:
        if norm.startswith(prefix):
            return bundle_key
    return None


def shell_for_template(rel: str) -> str | None:
    visited: set[str] = set()
    current = rel.lstrip("/").replace("\\", "/")
    if not current.startswith("templates/"):
        current = f"templates/{current}"

    while True:
        if current in visited:
            return directory_fallback(rel)
        visited.add(current)
        path = REPO / current
        if not path.is_file():
            return directory_fallback(rel) or "base"
        text = path.read_text(encoding="utf-8", errors="replace")
        m = EXTENDS_RE.search(text)
        if not m:
            return directory_fallback(rel) or "base"
        target = m.group(1).replace("\\", "/")
        for shell_path, bundle_key in SHELL_TO_BUNDLE.items():
            if target == shell_path or target.endswith("/" + shell_path):
                return bundle_key
        if target.startswith("unfold/") or target.startswith("admin/"):
            return "admin"
        current = target if target.startswith("templates/") else f"templates/{target}"


def parse_existing_bundle(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    headers = list(HEADER_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, h in enumerate(headers):
        rel = h.group(1).strip()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        sections[rel] = text[start:end].strip()
    return sections


def write_bundle(key: str, sections: dict[str, str]) -> None:
    out = CSS_DIR / f"phase2-{key}-bundle.css"
    header = [
        "/**",
        f" * Phase 2 - static-only template <style> blocks for {key} shell.",
        " * Regenerate: python scripts/extract_template_styles_phase2.py",
        f" * Surface: {key}",
        " */",
        "",
    ]
    body_lines = list(header)
    for rel in sorted(sections):
        body_lines.append(f"/* ========== {rel} ========== */")
        body_lines.append(sections[rel])
        body_lines.append("")
    out.write_text("\n".join(body_lines).rstrip() + "\n", encoding="utf-8")
    size_kb = round(out.stat().st_size / 1024, 1)
    print(f"  wrote {out.relative_to(REPO)} ({len(sections)} sections, {size_kb} KB)")


def main() -> int:
    style_inner = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.DOTALL)

    bundles: dict[str, dict[str, str]] = {
        key: parse_existing_bundle(CSS_DIR / f"phase2-{key}-bundle.css") for key in BUNDLE_KEYS
    }

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

        block_content = "\n".join(static_blocks)
        targets = MANUAL_OVERRIDES.get(rel) or (shell_for_template(rel) or "base",)
        for key in targets:
            bundles[key][rel] = block_content

        to_remove.sort(key=lambda x: x[0], reverse=True)
        new_text = text
        for start, end in to_remove:
            new_text = new_text[:start] + new_text[end:]
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        p.write_text(new_text.strip() + "\n", encoding="utf-8")
        stripped_files.append((rel, len(to_remove)))

    for key in BUNDLE_KEYS:
        write_bundle(key, bundles[key])

    if stripped_files:
        print(f"\nStripped {len(stripped_files)} templates of inline static <style> blocks:")
        for rel, n in stripped_files:
            print(f"  {n}  {rel}")
    else:
        print("\nNo new inline static <style> blocks found; bundles preserved as-is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
