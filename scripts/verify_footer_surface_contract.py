#!/usr/bin/env python3
"""
Platform footer surface contract — prevents marketing mega-footer on wrong shells.

Surfaces:
  - operator-compact: manager login + control plane (rmc_operator_footer_compact.html)
  - tenant-standard / tenant-minimal: portal_base + PORTAL_FOOTER_PARTIAL
  - marketing-full: runmycampus.com only (marketing_footer.html via base_marketing.html)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "footer_surface_contract_audit.json"
TEMPLATES = ROOT / "templates"

FORBIDDEN_INCLUDE = "corporate_footer_bundle.html"
FORBIDDEN_MARKUP = "mkt-footer-command"
FORBIDDEN_STYLE_INCLUDE = "corporate_footer_styles.html"

FORBIDDEN_PATHS = [
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/portal_base.html",
    "templates/backend_base_manager.html",
    "templates/backend_base_tenant.html",
    "templates/backend_base.html",
    "templates/auth/manager_login.html",
    "templates/auth/admin_login.html",
    "templates/auth/login.html",
    "templates/auth/school_picker.html",
    "templates/components/dashboard_footer.html",
    "templates/components/footer.html",
    "templates/components/portal_footers/minimal.html",
    "templates/base.html",
    "templates/admin/base_site.html",
]

REQUIRED_MARKERS = [
    ("templates/control_plane_skeleton.html", "rmc_operator_footer_compact.html"),
    ("templates/control_plane_skeleton.html", 'data-rmc-footer-surface="operator-compact"'),
    ("templates/admin/base.html", "rmc_operator_footer_compact.html"),
    ("templates/admin/base.html", 'data-rmc-footer-surface="operator-compact"'),
    ("templates/admin/base_site.html", "rmc-footer-surfaces.css"),
    ("templates/base.html", "rmc-footer-surfaces.css"),
    ("templates/base.html", "rmc_operator_footer_compact.html"),
    ("templates/portal_base.html", "PORTAL_FOOTER_PARTIAL"),
    ("templates/portal_base.html", "rmc-footer-surfaces.css"),
    ("templates/portal_base.html", "rmc_operator_footer_compact.html"),
    ("templates/portal_base.html", "SHOW_MANAGER_CORPORATE_FOOTER"),
    ("templates/portal_base.html", 'data-rmc-footer-surface="operator-compact"'),
    ("static/css/rmc-footer-surfaces.css", "operator-compact"),
    ("static/css/rmc-footer-surfaces.css", "tenant-standard"),
    ("apps/siteconfig/portal_chrome.py", '"marketing" not in fp.lower()'),
]


@dataclass
class Row:
    check_id: str
    description: str
    status: str
    proof: str


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _non_marketing_template_paths() -> list[Path]:
    paths: list[Path] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith("marketing/"):
            continue
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    for rel in FORBIDDEN_PATHS:
        text = _read(rel)
        add(
            f"forbid_bundle_{rel.replace('/', '_')}",
            f"{rel} must not include marketing corporate footer bundle",
            FORBIDDEN_INCLUDE not in text,
            rel,
        )

    for rel in FORBIDDEN_PATHS:
        if rel in ("templates/base.html",):
            continue
        text = _read(rel)
        add(
            f"forbid_mkt_command_{rel.replace('/', '_')}",
            f"{rel} must not embed marketing mega-footer markup",
            FORBIDDEN_MARKUP not in text,
            rel,
        )

    for rel in FORBIDDEN_PATHS:
        text = _read(rel)
        add(
            f"forbid_mkt_styles_{rel.replace('/', '_')}",
            f"{rel} must not pull marketing-shell footer CSS bundle",
            FORBIDDEN_STYLE_INCLUDE not in text,
            rel,
        )

    for rel, needle in REQUIRED_MARKERS:
        add(
            f"require_{needle[:20].replace(' ', '_')}_{rel.replace('/', '_')}",
            f"{rel} wires {needle!r}",
            needle in _read(rel),
            rel,
        )

    sweep_bundle: list[str] = []
    sweep_command: list[str] = []
    sweep_styles: list[str] = []
    for path in _non_marketing_template_paths():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_INCLUDE in text:
            sweep_bundle.append(rel)
        if FORBIDDEN_MARKUP in text:
            sweep_command.append(rel)
        if FORBIDDEN_STYLE_INCLUDE in text:
            sweep_styles.append(rel)

    add(
        "sweep_non_marketing_no_bundle",
        "No non-marketing template includes corporate_footer_bundle.html",
        not sweep_bundle,
        ", ".join(sweep_bundle[:5]) or f"{len(_non_marketing_template_paths())} templates scanned",
    )
    add(
        "sweep_non_marketing_no_mkt_command",
        "No non-marketing template embeds mkt-footer-command",
        not sweep_command,
        ", ".join(sweep_command[:5]) or "clean",
    )
    add(
        "sweep_non_marketing_no_corporate_footer_styles",
        "No non-marketing template includes corporate_footer_styles.html",
        not sweep_styles,
        ", ".join(sweep_styles[:5]) or "clean",
    )

    add(
        "marketing_base_uses_full_footer",
        "Marketing shell includes full marketing_footer.html (not bundle wrapper)",
        "marketing_footer.html" in _read("templates/marketing/base_marketing.html")
        and FORBIDDEN_INCLUDE
        not in _read("templates/marketing/base_marketing.html"),
        "templates/marketing/base_marketing.html",
    )

    add(
        "login_suppresses_skeleton_duplicate",
        "Manager login pages override skeleton footer block",
        "block cp_shell_footer" in _read("templates/auth/manager_login.html")
        and "block cp_shell_footer" in _read("templates/auth/admin_login.html"),
        "manager_login + admin_login",
    )

    add(
        "footer_surfaces_css",
        "Platform footer surface stylesheet exists",
        (ROOT / "static/css/rmc-footer-surfaces.css").is_file(),
        "static/css/rmc-footer-surfaces.css",
    )

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass": len(failed) == 0,
        "templates_scanned": len(_non_marketing_template_paths()),
        "rows": [asdict(r) for r in rows],
    }
    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for row in rows:
        print(f"[{row.status}] {row.check_id}: {row.description}")
    print(f"\nFOOTER_SURFACE_CONTRACT: {len(rows) - len(failed)}/{len(rows)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
