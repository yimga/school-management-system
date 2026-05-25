#!/usr/bin/env python3
"""
Platform-wide section-nav / page-fold audit — operator + tenant + admin surfaces.

Finds templates that trigger hand-authored or auto-generated horizontal pill rails,
classifies risk (link-style bleed, auto-pill spam, duplicate nav), and writes a ledger.

Usage:
  python scripts/audit_section_nav_platform.py
  python scripts/audit_section_nav_platform.py --strict
  python scripts/audit_section_nav_platform.py --write
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
GENERATED = ROOT / "docs" / "generated" / "section_nav_platform_audit.json"

RE_FOLD_FLAG = re.compile(r'data-rmc-page-fold-nav\s*=\s*["\']required["\']')
RE_SECTION_NAV_OFF = re.compile(r'data-rmc-section-nav\s*=\s*["\']off["\']')
RE_SECTION_NAV_AUTO = re.compile(r'data-rmc-section-nav\s*=\s*["\']auto["\']')
RE_HAND_NAV = re.compile(
    r"<nav[^>]*\brmc-section-nav\b|<nav[^>]*\brmc-page-fold-nav\b|"
    r"cp-hero__actions--toolbar\s+rmc-section-nav|"
    r"<nav[^>]*\bcp-section-nav\b",
    re.I,
)
RE_ANCHOR = re.compile(r"data-rmc-section-anchor")
RE_GHOST_JUMP = re.compile(
    r"cp-btn--ghost[^>]*data-rmc-section-anchor|data-rmc-section-anchor[^>]*cp-btn--ghost",
    re.I,
)
RE_H2_H3_ID = re.compile(r"<h[23][^>]*\bid\s*=", re.I)
RE_H2_H3_ANY = re.compile(r"<h[23]\b", re.I)
RE_EXTENDS = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']')
RE_INCLUDE = re.compile(r'\{%\s*include\s+["\']([^"\']+)["\']')
RE_NAV_LABEL = re.compile(r'data-rmc-section-nav-label\s*=\s*["\']([^"\']+)["\']')
RE_SECTION_NAV_CURATED = re.compile(
    r'data-rmc-section-nav\s*=\s*["\']curated["\']|'
    r"data-rmc-section-nav-curated|rmc_section_nav_curated"
)
RE_SECTION_NAV_SKIP = re.compile(r"data-rmc-section-nav-skip")
RE_DEPRECATED_HORIZONTAL = re.compile(
    r"rmc-section-nav--horizontal\s+rmc-horizontal-nav-rail|"
    r"rmc-horizontal-nav-rail[^\"']*rmc-section-nav--horizontal",
    re.I,
)
RE_TOC_NAV = re.compile(r"rmc-section-nav--toc|rmc-section-nav__toc")

OPERATOR_MARKERS = (
    "control_plane",
    "admin/",
    "super/",
    "schools/super",
    "manager_",
    "siteconfig/operator",
    "migration_cloud/operator",
    "migration_cloud/super",
    "apicenter/super",
    "platform_runtime/",
    "marketplace/",
)
TENANT_MARKERS = (
    "portal_base",
    "backend_base",
    "accounts/",
    "teacher/",
    "parent/",
    "student/",
    "portal/",
    "feedback/",
    "analytics/",
)
SHELL_FILES = {
    "templates/portal_base.html",
    "templates/control_plane_base.html",
    "templates/control_plane_skeleton.html",
    "templates/base.html",
    "templates/admin/base.html",
    "templates/admin/base_site.html",
    "templates/backend_base.html",
    "templates/backend_base_tenant.html",
    "templates/marketing/base_marketing.html",
}


@dataclass
class FileRow:
    path: str
    surface: str
    extends: str | None
    fold_required: bool
    section_nav_off: bool
    section_nav_auto: bool
    hand_nav: bool
    ghost_jump_links: int
    anchor_count: int
    h2_h3_with_id: int
    h2_h3_total: int
    nav_label_attrs: int
    section_nav_curated: bool
    section_nav_skip: bool
    uses_toc_nav: bool
    deprecated_horizontal: bool
    risk: str
    notes: list[str] = field(default_factory=list)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _classify_surface(rel: str, text: str) -> str:
    if rel in SHELL_FILES:
        return "shell"
    lower = rel.lower()
    if "marketing/" in lower:
        return "marketing"
    if any(m in lower for m in OPERATOR_MARKERS):
        return "operator"
    if any(m in lower for m in TENANT_MARKERS):
        return "tenant"
    if "extends" in text:
        m = RE_EXTENDS.search(text)
        if m:
            ext = m.group(1)
            if "control_plane" in ext or "admin/" in ext:
                return "operator"
            if "portal_base" in ext or "backend_base" in ext:
                return "tenant"
    return "other"


def _risk_for(row: FileRow) -> tuple[str, list[str]]:
    notes: list[str] = []
    if row.deprecated_horizontal:
        return "high", ["deprecated horizontal pill rail — migrate to rmc-section-nav--toc"]
    if row.ghost_jump_links:
        return "high", ["cp-btn--ghost section jumps — use rmc_section_nav_curated partial"]

    if row.section_nav_off:
        return "ok", ["explicit data-rmc-section-nav=off"]

    if row.section_nav_skip:
        return "ok", ["data-rmc-section-nav-skip — parent owns TOC"]

    if row.section_nav_curated or row.uses_toc_nav:
        if row.hand_nav:
            return "ok", ["curated TOC section nav (hand-authored)"]
        if row.nav_label_attrs >= 2:
            return "ok", ["curated anchors with data-rmc-section-nav-label"]
        return "ok", ["data-rmc-section-nav=curated or TOC partial"]

    if row.hand_nav and row.anchor_count >= 6:
        notes.append("hand nav with many anchors — verify TOC dropdown styling")
        return "medium", notes

    if row.hand_nav:
        if row.ghost_jump_links:
            return "low", ["curated hand nav (admin ghost jump toolbar)"]
        return "ok", ["curated hand-authored section nav"]

    if row.section_nav_auto:
        auto_candidates = row.anchor_count + row.h2_h3_with_id + max(0, row.h2_h3_total - row.h2_h3_with_id)
        if auto_candidates >= 6:
            notes.append(f"data-rmc-section-nav=auto with {auto_candidates} heading/anchor signals")
            return "high", notes
        if auto_candidates >= 2:
            notes.append(f"data-rmc-section-nav=auto may inject pills ({auto_candidates} signals)")
            return "medium", notes

    if row.anchor_count >= 2 and not row.hand_nav:
        notes.append(f"explicit anchors only ({row.anchor_count}) — auto pills if not off")
        return "medium", notes

    if row.fold_required and not row.hand_nav and row.h2_h3_total >= 4:
        notes.append(
            f"long page ({row.h2_h3_total} headings) — add hand nav or data-rmc-section-nav=off"
        )
        return "low", notes

    if row.fold_required and row.surface != "shell":
        notes.append(
            "data-rmc-page-fold-nav=required without explicit section-nav contract "
            "(off|auto|curated|skip or curated <nav>)"
        )
        return "medium", notes

    return "ok", notes


def scan_templates() -> list[FileRow]:
    rows: list[FileRow] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        if not any(
            needle in text
            for needle in (
                "rmc-section-nav",
                "rmc-page-fold-nav",
                "data-rmc-section-anchor",
                "data-rmc-page-fold-nav",
                "rmc-horizontal-nav-rail",
                "rmc-section-nav--toc",
            )
        ):
            continue

        ext_m = RE_EXTENDS.search(text)
        row = FileRow(
            path=rel,
            surface=_classify_surface(rel, text),
            extends=ext_m.group(1) if ext_m else None,
            fold_required=bool(RE_FOLD_FLAG.search(text)),
            section_nav_off=bool(RE_SECTION_NAV_OFF.search(text)),
            section_nav_auto=bool(RE_SECTION_NAV_AUTO.search(text)),
            hand_nav=bool(RE_HAND_NAV.search(text)),
            ghost_jump_links=len(RE_GHOST_JUMP.findall(text)),
            anchor_count=len(RE_ANCHOR.findall(text)),
            h2_h3_with_id=len(RE_H2_H3_ID.findall(text)),
            h2_h3_total=len(RE_H2_H3_ANY.findall(text)),
            nav_label_attrs=len(RE_NAV_LABEL.findall(text)),
            section_nav_curated=bool(RE_SECTION_NAV_CURATED.search(text)),
            section_nav_skip=bool(RE_SECTION_NAV_SKIP.search(text)),
            uses_toc_nav=bool(RE_TOC_NAV.search(text)),
            deprecated_horizontal=bool(RE_DEPRECATED_HORIZONTAL.search(text)),
            risk="ok",
        )
        row.risk, row.notes = _risk_for(row)
        rows.append(row)
    return rows


def shell_contract_checks() -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    chrome = (ROOT / "templates/partials/rmc_platform_chrome_styles.html").read_text(
        encoding="utf-8", errors="replace"
    )
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8", errors="replace")
    cp = (ROOT / "templates/control_plane_base.html").read_text(encoding="utf-8", errors="replace")
    js = (ROOT / "static/js/rmc-page-fold-standards.js").read_text(encoding="utf-8", errors="replace")

    for name, ok, proof in (
        ("chrome_toc_css", "rmc-section-nav-toc.css" in chrome, "rmc_platform_chrome_styles.html"),
        ("portal_fold_nav", 'data-rmc-page-fold-nav="required"' in portal, "portal_base.html"),
        ("cp_fold_nav", 'data-rmc-page-fold-nav="required"' in cp, "control_plane_base.html"),
        ("auto_nav_toc", "rmc-section-nav--toc" in js, "rmc-page-fold-standards.js"),
        ("curated_partial", (TEMPLATES / "partials/rmc_section_nav_curated.html").is_file(), "rmc_section_nav_curated.html"),
    ):
        checks.append({"check_id": name, "status": "PASS" if ok else "FAIL", "proof": proof})
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write docs/generated JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any high-risk file lacks section_nav_off or hand_nav",
    )
    args = parser.parse_args()

    rows = scan_templates()
    by_surface: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for r in rows:
        by_surface[r.surface] = by_surface.get(r.surface, 0) + 1
        by_risk[r.risk] = by_risk.get(r.risk, 0) + 1

    high = [r for r in rows if r.risk == "high"]
    medium = [r for r in rows if r.risk == "medium"]
    deprecated = [r for r in rows if r.deprecated_horizontal]
    ghost = [r for r in rows if r.ghost_jump_links]
    shell_checks = shell_contract_checks()
    shell_fail = [c for c in shell_checks if c["status"] != "PASS"]

    unmitigated_high = list(high)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(rows),
        "summary": {
            "by_surface": by_surface,
            "by_risk": by_risk,
            "hand_nav_count": sum(1 for r in rows if r.hand_nav),
            "fold_required_count": sum(1 for r in rows if r.fold_required),
            "section_nav_off_count": sum(1 for r in rows if r.section_nav_off),
            "high_risk_count": len(high),
            "medium_risk_count": len(medium),
            "unmitigated_high_risk_count": len(unmitigated_high),
            "deprecated_horizontal_count": len(deprecated),
            "ghost_jump_count": len(ghost),
        },
        "shell_contract": shell_checks,
        "deprecated_horizontal": [asdict(r) for r in deprecated],
        "high_risk": [asdict(r) for r in sorted(high, key=lambda x: -x.anchor_count - x.h2_h3_total)],
        "medium_risk": [asdict(r) for r in sorted(medium, key=lambda x: -x.h2_h3_total)[:40]],
        "files": [asdict(r) for r in rows],
        "rearchitecture": {
            "tier_a_curated": "Hand <nav class='rmc-section-nav'> with short labels; blocks auto-nav.",
            "tier_b_opt_in_auto": "data-rmc-section-nav='auto' on page root when headings are intentional.",
            "tier_c_off": "data-rmc-section-nav='off' on hub/landing pages (help, profile, configure).",
            "label_contract": "data-rmc-section-nav-label on anchor targets; never raw textContent of cards.",
            "css_contract": ".rmc-section-nav a excluded from #cp-main-content accent link rule; .is-active synced.",
        },
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {GENERATED.relative_to(ROOT)}")

    print("SECTION_NAV_PLATFORM_AUDIT")
    print(f"  files_scanned_with_signals: {len(rows)}")
    print(f"  by_surface: {by_surface}")
    print(f"  by_risk: {by_risk}")
    print(f"  hand_nav: {payload['summary']['hand_nav_count']}")
    print(f"  high_risk: {len(high)} (unmitigated: {len(unmitigated_high)})")
    if high[:8]:
        print("  top_high_risk:")
        for r in high[:8]:
            print(f"    - {r.path} ({r.notes[0] if r.notes else r.risk})")

    if shell_fail:
        print("  shell_contract_fail:")
        for c in shell_fail:
            print(f"    - {c['check_id']}: {c['proof']}")

    if args.strict and (unmitigated_high or medium or shell_fail):
        print("SECTION_NAV_PLATFORM_AUDIT_FAIL")
        for r in (unmitigated_high + medium)[:20]:
            print(f"  {r.path}: {r.notes[0] if r.notes else r.risk}")
        for c in shell_fail:
            print(f"  shell:{c['check_id']}")
        return 1

    print("SECTION_NAV_PLATFORM_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
