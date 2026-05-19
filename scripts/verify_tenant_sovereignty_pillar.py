#!/usr/bin/env python3
"""
Tenant Sovereignty pillar gate — white-label theme cascade, FOUC-safe bootstrap, brand guard.

Mechanical repo-scope proof for pillar 0 of the six-pillar global-dominance mandate.
Writes docs/generated/tenant_sovereignty_pillar_audit.json on --write.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "tenant_sovereignty_pillar_audit.json"

SHELL_TEMPLATES = (
    "templates/portal_base.html",
    "templates/base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
    "templates/marketing/base_marketing.html",
)


@dataclass
class Row:
    check_id: str
    description: str
    status: str
    proof: str


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _theme_bootstrap_sync_in_head(html: str) -> bool:
    """theme-preference-bootstrap.js must load without defer/async (FOUC contract)."""
    for line in html.splitlines():
        if "theme-preference-bootstrap.js" not in line:
            continue
        low = line.lower()
        return "defer" not in low and "async" not in low
    return False


def _js_without_comments(source: str) -> str:
    stripped = re.sub(r"/\*[\s\S]*?\*/", "", source)
    return re.sub(r"//[^\n]*", "", stripped)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write JSON audit artifact.")
    args = parser.parse_args()
    py = sys.executable
    rows: list[Row] = []

    def add(check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, description, "PASS" if ok else "FAIL", proof))

    # Meta bridge on every shell
    for rel in SHELL_TEMPLATES:
        html = _read(rel)
        add(
            f"meta_bridge_{Path(rel).stem}",
            f"{rel} includes rmc_theme_meta.html",
            'partials/rmc_theme_meta.html' in html,
            rel,
        )

    # Synchronous theme bootstrap (tenant FOUC elimination)
    for rel in SHELL_TEMPLATES:
        html = _read(rel)
        add(
            f"bootstrap_sync_{Path(rel).stem}",
            f"{rel} loads theme-preference-bootstrap synchronously in head",
            "theme-preference-bootstrap.js" in html and _theme_bootstrap_sync_in_head(html),
            rel,
        )

    marketing = _read("templates/marketing/base_marketing.html")
    add(
        "marketing_surface_isolation",
        "Marketing shell declares data-surface=marketing (theme key isolation)",
        'data-surface="marketing"' in marketing or "data-surface='marketing'" in marketing,
        "base_marketing.html",
    )

    bootstrap_js = _js_without_comments(_read("static/js/theme-preference-bootstrap.js"))
    add(
        "v3_effective_theme_contract",
        "Bootstrap sets data-theme to effective light|dark (v3 contract)",
        "data-theme-preference" in bootstrap_js
        and 'setAttribute("data-theme", resolved)' in bootstrap_js,
        "theme-preference-bootstrap.js",
    )

    add(
        "brand_guard_module",
        "WCAG AAA brand guard runtime module",
        (ROOT / "apps/siteconfig/brand_guard_runtime.py").is_file()
        and "guard_brand_dict" in _read("apps/siteconfig/brand_guard_runtime.py"),
        "brand_guard_runtime.py",
    )

    ctx = _read("apps/siteconfig/context_processors.py")
    add(
        "brand_guard_context",
        "Context processor applies guard_brand_dict before render",
        "guard_brand_dict" in ctx,
        "context_processors.py",
    )

    add(
        "theme_builder_stack",
        "Shopify-grade theme builder publish/preview/layout APIs",
        (ROOT / "apps/siteconfig/views_theme_builder.py").is_file()
        and "ThemeBuilderPublishAPIView" in _read("apps/siteconfig/views_theme_builder.py"),
        "views_theme_builder.py",
    )

    vectors = ROOT / "docs/generated/tenant_sovereignty_platform_vectors.json"
    add(
        "sot_vectors_json",
        "Tenant sovereignty SOT platform vectors JSON present",
        vectors.is_file(),
        str(vectors.relative_to(ROOT)),
    )

    proc = subprocess.run(
        [py, str(ROOT / "scripts/scan_theme_attribute_contract.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-200:]
    add(
        "theme_attr_contract",
        "No regressions on data-theme=system CSS/JS contract",
        proc.returncode == 0,
        tail or "scan_theme_attribute_contract",
    )

    code_gear, _ = subprocess.run(
        [py, str(ROOT / "scripts/verify_theme_experience_gear.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    ).returncode, ""
    add(
        "theme_experience_gear",
        "Theme experience gear-up gate (builder + hub hero)",
        code_gear == 0,
        "verify_theme_experience_gear",
    )

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "TENANT_SOVEREIGNTY_PASS" if not failed else "TENANT_SOVEREIGNTY_FAIL",
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": len(failed),
        "rows": [asdict(r) for r in rows],
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for row in failed:
        print(
            f"FAIL [{row.check_id}]: {row.description} — {row.proof}",
            file=sys.stderr,
        )

    if failed:
        print(f"verify_tenant_sovereignty_pillar: {len(failed)} FAIL", file=sys.stderr)
        return 1

    print(
        f"verify_tenant_sovereignty_pillar: {payload['verdict']} ({payload['passed']} checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
