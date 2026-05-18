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
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

REQUIRED_STATIC = [
    "static/js/shell-data-dashboard-page.js",
    "static/css/design-tokens.css",
    "static/css/design-system-phase2-enforcement.css",
    "static/css/design-system-unified.css",
    "static/marketing/css/tokens-marketing.css",
    # `dashboard-header-component.css` + `theme-toggle-component.css` retired
    # 2026-05-12 — their consumer templates (dashboard_header.html and
    # theme_toggle.html) were orphans after portal_base.html migrated to the
    # rich user_dropdown.html which has its own embedded theme toggle.
    "static/css/studio-mode-rail.css",
    "static/css/studio-workspace.css",
    "static/css/studio-shell-layout.css",
    "static/css/studio-system-config-console.css",
    "static/css/control-plane-skeleton-root.css",
    "static/css/admin-base-site-shell.css",
    "static/css/portal-base-shell.css",
    "static/css/admin-nav-bridge-tenant.css",
    "static/css/studio-control-mode-canvas.css",
    "static/css/root-base-shell.css",
    "static/css/portal-ui-components.css",
    "static/css/phase2-portal-bundle.css",
    "static/css/phase2-base-bundle.css",
    "static/css/phase2-admin-bundle.css",
    "static/css/phase2-control-plane-bundle.css",
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

FORBIDDEN_INLINE_STYLE_TEMPLATES: list[str] = []

HIGH_IMPACT_TEMPLATES = [
    "templates/marketplace/tenant_app_catalog.html",
    "templates/portal/student_attendance_export.html",
    "templates/teacher/marks_list.html",
    "templates/parent/dashboard.html",
    "templates/accounts/backend_dashboard.html",
]

GOVERNED_CORE_CSS = [
    "static/css/design-tokens-luxury.css",
    "static/css/design-system-unified.css",
    "static/css/platform-high-end.css",
    "static/css/design-system-phase2-enforcement.css",
]

AUDIT_JSON = "docs/generated/design_system_audit.json"
AUDIT_MD = "docs/generated/design_system_audit.md"

_SPACING_PROP = re.compile(
    r"^\s*(?:margin|padding|gap|row-gap|column-gap|"
    r"padding-(?:top|right|bottom|left|block|inline)|"
    r"margin-(?:top|right|bottom|left|block|inline))\s*:\s*"
    r"(?!var\()(-?\d*\.?\d+(?:px|rem|em|vh|vw|%)\b)",
    re.IGNORECASE,
)
_RADIUS_PROP = re.compile(
    r"^\s*border-radius(?:-[a-z-]+)?\s*:\s*(?!var\()"
    r"(-?\d*\.?\d+(?:px|rem|em|%)\b)",
    re.IGNORECASE,
)
_SHADOW_PROP = re.compile(
    r"^\s*box-shadow\s*:\s*(?!var\()(.+);",
    re.IGNORECASE,
)
_VAR_DEF = re.compile(r"^\s*--[a-zA-Z0-9-_]+\s*:")


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
    parser.add_argument(
        "--refresh-design-system-audit",
        action="store_true",
        help="Refresh baseline raw-literal counts in docs/generated/design_system_audit.json.",
    )
    return parser.parse_args(argv)


def _scan_raw_literals(css_path: Path) -> dict[str, int]:
    out = {
        "raw_spacing_literals": 0,
        "raw_radius_literals": 0,
        "raw_shadow_literals": 0,
        "forbidden_600ms_literals": 0,
    }
    if not css_path.is_file():
        return out
    text = css_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip()
        if not s or _VAR_DEF.match(s):
            continue
        if _SPACING_PROP.search(s):
            out["raw_spacing_literals"] += 1
        if _RADIUS_PROP.search(s):
            out["raw_radius_literals"] += 1
        m_shadow = _SHADOW_PROP.search(s)
        if m_shadow and re.search(r"\d", m_shadow.group(1)):
            out["raw_shadow_literals"] += 1
        if "600ms" in s:
            out["forbidden_600ms_literals"] += 1
    return out


def _iter_high_impact_templates(repo: Path) -> list[Path]:
    files: list[Path] = []
    for rel in HIGH_IMPACT_TEMPLATES:
        p = repo / rel
        if p.is_file():
            files.append(p)
    files.extend(sorted((repo / "templates" / "siteconfig").glob("*evidence*.html")))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in files:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def _validate_component_contract(text: str, rel: str) -> list[str]:
    errors: list[str] = []
    has_table = "<table" in text
    table_strict = rel.startswith("templates/siteconfig/") or rel in {
        "templates/teacher/marks_list.html",
    }
    if has_table and table_strict:
        if "table-responsive" not in text:
            errors.append(f"{rel}: table found without .table-responsive wrapper")
        if "table-family" not in text:
            errors.append(f"{rel}: table found without .table-family class")

    # Guard against raw buttons without a design-system class.
    for m in re.finditer(r"<button\b([^>]*)>", text, re.IGNORECASE):
        attrs = m.group(1) or ""
        class_m = re.search(r'class\s*=\s*"([^"]*)"', attrs, re.IGNORECASE)
        if not class_m:
            errors.append(f"{rel}: <button> missing class attribute")
            break
        classes = class_m.group(1).split()
        if (
            "btn" not in classes
            and "search-trigger" not in classes
            and "backend-role-home-command" not in classes
        ):
            errors.append(f"{rel}: <button> missing design-system button class")
            break

    has_form_controls = ("form-control" in text) or ("form-select" in text)
    if has_form_controls:
        if (
            "form-system" not in text
            and "data-rmc-form-grammar" not in text
            and "ui-premium-surface" not in text
        ):
            errors.append(f"{rel}: form controls found outside standardized form grammar")
    return errors


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

    # High-impact component contract checks.
    for p in _iter_high_impact_templates(repo):
        rel = str(p.relative_to(repo)).replace("\\", "/")
        text = _read(p)
        errors.extend(_validate_component_contract(text, rel))

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

    audit_json_path = repo / AUDIT_JSON
    audit_md_path = repo / AUDIT_MD
    audit_json_path.parent.mkdir(parents=True, exist_ok=True)

    current_literal_counts: dict[str, dict[str, int]] = {}
    for rel in GOVERNED_CORE_CSS:
        current_literal_counts[rel] = _scan_raw_literals(repo / rel)

    prior_baseline: dict[str, dict[str, int]] = {}
    if audit_json_path.is_file():
        try:
            old = json.loads(audit_json_path.read_text(encoding="utf-8"))
            prior_baseline = old.get("raw_literal_baseline", {}) or {}
        except (ValueError, OSError):
            prior_baseline = {}

    if args.refresh_design_system_audit or not prior_baseline:
        baseline_literal_counts = current_literal_counts
    else:
        baseline_literal_counts = prior_baseline

    for rel, counts in current_literal_counts.items():
        baseline = baseline_literal_counts.get(rel, {})
        for key, val in counts.items():
            b = int(baseline.get(key, 0))
            if val > b:
                errors.append(
                    f"{rel}: {key} increased ({val} > baseline {b})"
                )

    token_conflicts = {
        "spacing": [
            "--token-space-* / --spacing-*",
            "--luxury-gap*",
            "--lux-space-*",
        ],
        "typography": [
            "--font-size-* / --type-*",
            "--luxury-font-*",
            "--lux-type-*",
        ],
        "radius": [
            "--radius-*",
            "--platform-premium-radius*",
            "--luxury-btn-radius / --lux-radius-*",
        ],
        "shadow": [
            "--shadow-*",
            "--platform-premium-shadow*",
            "--luxury-shadow-* / --lux-shadow-*",
        ],
        "color": [
            "--color-*",
            "--luxury-*",
            "--lux-color-*",
        ],
        "motion": [
            "--transition-* / --motion-*",
            "--luxury-motion-*",
            "--lux-motion-*",
        ],
    }

    audit_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": not errors,
        "governed_css_files": GOVERNED_CORE_CSS,
        "raw_literal_current": current_literal_counts,
        "raw_literal_baseline": baseline_literal_counts,
        "token_conflicts_found": token_conflicts,
        "errors": errors,
    }
    audit_json_path.write_text(
        json.dumps(audit_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit_md_path.write_text(
        "\n".join(
            [
                "# Design System Audit",
                "",
                f"**OK:** {not errors}",
                "",
                "## Governed CSS files",
                "",
                *[f"- `{p}`" for p in GOVERNED_CORE_CSS],
                "",
                "## Raw literal counts (current)",
                "",
                *[
                    f"- `{p}`: spacing={c['raw_spacing_literals']}, radius={c['raw_radius_literals']}, shadow={c['raw_shadow_literals']}, 600ms={c['forbidden_600ms_literals']}"
                    for p, c in current_literal_counts.items()
                ],
                "",
                "## Token conflicts found",
                "",
                *[
                    f"- **{k}**: {', '.join(v)}"
                    for k, v in token_conflicts.items()
                ],
                "",
            ]
        ),
        encoding="utf-8",
    )

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
    print(f"  - design system audit written: {audit_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
