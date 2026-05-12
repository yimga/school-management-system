#!/usr/bin/env python3
"""Split phase2-static-templates-bundle.css into per-shell bundles.

For each /* ========== templates/... ========== */ section in the monolith,
walk the template's {% extends %} chain to find its base shell and route the
section to the matching per-shell bundle file.

Reads:
  static/css/phase2-static-templates-bundle.css
Writes:
  static/css/phase2-portal-bundle.css
  static/css/phase2-base-bundle.css
  static/css/phase2-admin-bundle.css
  static/css/phase2-control-plane-bundle.css
  static/css/phase2-studio-bundle.css

Usage (repo root): python scripts/split_phase2_bundle_by_shell.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUNDLE = REPO / "static" / "css" / "phase2-static-templates-bundle.css"
TEMPLATES = REPO / "templates"

SHELL_TO_BUNDLE = {
    "portal_base.html": "portal",
    "backend_base.html": "portal",
    "base.html": "base",
    "admin/base_site.html": "admin",
    "control_plane_skeleton.html": "control-plane",
    "control_plane_base.html": "control-plane",
    "marketing/base_marketing.html": "marketing",
    "studio_os/base_studio_os.html": "studio",
}

EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']\s*%}', re.I)
HEADER_RE = re.compile(r"^/\* =+ (.+?) =+ \*/\s*$", re.M)


MANUAL_OVERRIDES: dict[str, tuple[str, ...]] = {
    "templates/siteconfig/feature_control_panel_content.html": ("portal",),
    "templates/siteconfig/partials/reportcard_builder_inner.html": ("portal",),
    "templates/siteconfig/partials/theme_colors_page_body.html": ("portal", "control-plane"),
    "templates/studio_os/components/loading_empty_states.html": ("portal", "control-plane"),
}

DIR_FALLBACKS = (
    ("templates/admin/", "admin"),
    ("templates/marketing/", "marketing"),
    ("templates/schools/marketing_", "marketing"),
    ("templates/control_plane", "control-plane"),
    ("templates/siteconfig/console_domains", "control-plane"),
    ("templates/evals/", "control-plane"),
    ("templates/compliance/", "control-plane"),
    ("templates/marketplace/", "control-plane"),
    ("templates/emis/", "control-plane"),
    ("templates/studio_os/", "studio"),
)


def directory_fallback(rel: str) -> str | None:
    norm = rel.replace("\\", "/")
    if not norm.startswith("templates/"):
        norm = f"templates/{norm}"
    for prefix, bundle_key in DIR_FALLBACKS:
        if norm.startswith(prefix):
            return bundle_key
    return None


def shell_for_template(rel: str) -> str | None:
    """Walk {% extends %} chain to find owning base shell. Falls back to directory heuristic."""
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


def main() -> int:
    if not BUNDLE.is_file():
        print(f"ERROR: {BUNDLE} not found")
        return 1

    bundle_text = BUNDLE.read_text(encoding="utf-8")
    headers = list(HEADER_RE.finditer(bundle_text))
    if not headers:
        print("ERROR: no section headers found in bundle")
        return 1

    sections: list[tuple[str, str]] = []
    for i, h in enumerate(headers):
        rel = h.group(1).strip()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(bundle_text)
        content = bundle_text[start:end].strip()
        sections.append((rel, content))

    bundles: dict[str, list[str]] = {
        "portal": [],
        "base": [],
        "admin": [],
        "control-plane": [],
        "marketing": [],
        "studio": [],
    }
    unrouted: list[str] = []

    for rel, content in sections:
        norm = rel.replace("\\", "/")
        if not norm.startswith("templates/"):
            norm = f"templates/{norm}"
        if norm in MANUAL_OVERRIDES:
            for bundle_key in MANUAL_OVERRIDES[norm]:
                bundles[bundle_key].append(f"/* ========== {rel} ========== */\n{content}\n")
            continue
        bundle_key = shell_for_template(rel)
        if bundle_key is None:
            unrouted.append(rel)
            bundle_key = "base"
        bundles[bundle_key].append(f"/* ========== {rel} ========== */\n{content}\n")

    for key, items in bundles.items():
        if key == "marketing":
            if items:
                print(f"  SKIP marketing — {len(items)} sections; already covered by marketing-static-bundle.css carve-out")
            continue
        out = REPO / "static" / "css" / f"phase2-{key}-bundle.css"
        header = [
            "/**",
            f" * Phase 2 - static-only template <style> blocks for {key} shell.",
            " * Regenerate: python scripts/extract_template_styles_phase2.py",
            f" * Surface: {key}",
            " */",
            "",
        ]
        body = "\n".join(header) + "\n" + "\n".join(items)
        out.write_text(body.rstrip() + "\n", encoding="utf-8")
        line_count = body.count("\n")
        size_kb = round(len(body.encode("utf-8")) / 1024, 1)
        print(f"  wrote {out.relative_to(REPO)} ({line_count}L, {len(items)} sections, {size_kb} KB)")

    if unrouted:
        print(f"\nWARN: {len(unrouted)} sections could not be routed (defaulted to base):")
        for r in unrouted:
            print(f"  {r}")

    print(f"\nTotal sections processed: {len(sections)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
