#!/usr/bin/env python3
"""Replace page_header / inline CP headers with rmc_operational_center_frame."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
FRAME = "rmc_operational_center_frame.html"

PAGE_HEADER_RE = re.compile(
    r'\{%\s*include\s+"studio_os/components/page_header\.html"\s+with\s+(.+?)\s*%\}',
    re.DOTALL,
)
CP_HERO_RE = re.compile(
    r'<section class="cp-hero cp-hero-compact mb-4">\s*<div class="cp-hero-grid">\s*<div>\s*'
    r'<div class="cp-eyebrow">([^<]*)</div>\s*'
    r'<h1 class="cp-hero-title">([^<]*)</h1>\s*'
    r'<p class="cp-hero-copy">\s*([\s\S]*?)\s*</p>',
    re.DOTALL,
)
ORPHAN_HERO_TAIL_RE = re.compile(
    r'\s*</div>\s*</div>\s*<div class="cp-hero-actions">[\s\S]*?</section>\s*',
    re.DOTALL,
)
INLINE_CP_HEADER_RE = re.compile(
    r'<header class="mb-4[^"]*"[^>]*>\s*<div class="min-w-0">\s*'
    r'<p class="text-uppercase[^"]*">[^<]*</p>\s*'
    r'<h1 class="h2[^"]*">([^<]*)</h1>\s*'
    r'<p class="mb-0">\s*([\s\S]*?)\s*</p>',
    re.DOTALL,
)
REGISTRY_HEADER_RE = re.compile(
    r'<header class="mb-4">\s*'
    r'<p class="small text-muted mb-1">[\s\S]*?</p>\s*'
    r'<h1 class="h3 mb-2">([\s\S]*?)</h1>\s*'
    r'<p class="text-muted mb-0">([\s\S]*?)</p>\s*</header>',
    re.DOTALL,
)
CONFIG_MODULE_HEADER_RE = re.compile(
    r'<header class="mb-4">\s*'
    r'<p class="small text-muted mb-1">[\s\S]*?</p>\s*'
    r'<h1 class="h3 mb-2">([\s\S]*?)</h1>\s*'
    r'<p class="text-muted mb-0">([\s\S]*?)</p>\s*</header>',
    re.DOTALL,
)
INLINE_H4_RE = re.compile(
    r'<h1 class="h4">([^<]*)</h1>\s*'
    r'<p class="text-secondary small">([^<]*)</p>',
    re.DOTALL,
)
INLINE_H1_RE = re.compile(
    r'(<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">\s*)'
    r'<h1 class="h5 mb-0">([^<]*)</h1>',
    re.DOTALL,
)

FIELD_ORDER = ("title", "subtitle", "action_url", "action_text", "eyebrow")
ALLOW_LANDING = {
    "templates/schools/super_dashboard.html",
    "templates/customersuccess/super_dashboard.html",
}
CP_PREFIXES = (
    "templates/schools/super_",
    "templates/marketplace/",
    "templates/platform_runtime/",
    "templates/observability/",
    "templates/orchestration/",
    "templates/migration_cloud/",
)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _slug_from_path(path: Path) -> str:
    name = path.stem
    if name.startswith("super_"):
        return name[6:]
    return name.replace("-", "_")


def _extract_fields(with_clause: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for i, key in enumerate(FIELD_ORDER):
        start_pat = f"{key}="
        idx = with_clause.find(start_pat)
        if idx < 0:
            continue
        start = idx + len(start_pat)
        end = len(with_clause)
        for next_key in FIELD_ORDER[i + 1 :]:
            nidx = with_clause.find(f" {next_key}=", start)
            if nidx >= 0:
                end = min(end, nidx)
        fields[key] = with_clause[start:end].strip()
    return fields


def _frame_include(slug: str, fields: dict[str, str]) -> str:
    title = fields.get("title", '_("Operations")')
    purpose = fields.get("subtitle", '""')
    primary_url = fields.get("action_url", '""')
    primary_label = fields.get("action_text", '""')
    return (
        '{% include "components/rmc_operational_center_frame.html" with '
        f'os_center_key="{slug}" center_eyebrow=_("Platform operators") '
        f"center_title={title} center_purpose={purpose} "
        f"primary_url={primary_url} primary_label={primary_label} "
        'status_badge_text=_("Operational") nav_groups=operational_nav_groups %}'
    )


def _ensure_workspace_header(text: str) -> str:
    if "extends \"control_plane_base\"" not in text or "cp_workspace_header" in text:
        return text
    needle = "{% block cp_content %}"
    if needle not in text:
        return text
    return text.replace(
        needle,
        '{% block cp_workspace_header %}{% endblock %}\n\n{% block cp_content %}',
        1,
    )


def _inject_after_phase8(text: str, slug: str) -> str:
    inc = _frame_include(slug, {"title": '_("Operations")', "subtitle": '""', "action_url": '""', "action_text": '""'})
    if "{% phase8_dashboard_declaration" not in text:
        return text
    return re.sub(
        r"(\{% phase8_dashboard_declaration[^%]+%\})\s*",
        r"\1\n  " + inc + "\n  ",
        text,
        count=1,
    )


def _fix_py4(text: str) -> str:
    if 'data-page-archetype="operational-workbench"' not in text:
        return text
    text = text.replace("container-fluid py-4", "container-fluid py-2")
    text = text.replace('class="container-fluid py-4"', 'class="container-fluid py-2"')
    if "container py-4" in text:
        text = text.replace("container py-4", "container-fluid py-2")
        text = text.replace('class="container py-4"', 'class="container-fluid py-2"')
    return text


def _ensure_workbench_markers(text: str) -> str:
    if 'data-page-archetype="operational-workbench"' in text and 'data-rmc-operational-workbench="1"' not in text:
        text = text.replace(
            'data-page-archetype="operational-workbench"',
            'data-page-archetype="operational-workbench" data-rmc-operational-workbench="1" data-rmc-static-chrome="1"',
            1,
        )
    return text


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    slug = _slug_from_path(path)

    text = _ensure_workspace_header(text)
    text = _ensure_workbench_markers(text)
    text = _fix_py4(text)

    m = PAGE_HEADER_RE.search(text)
    if m:
        fields = _extract_fields(m.group(1))
        text = PAGE_HEADER_RE.sub(_frame_include(slug, fields), text, count=1)

    m = CP_HERO_RE.search(text)
    if m:
        title_raw = m.group(2).strip()
        purpose_raw = re.sub(r"\s+", " ", m.group(3).strip())
        fields = {
            "title": f'"{title_raw}"' if not title_raw.startswith("_(") else title_raw,
            "subtitle": f'"{purpose_raw}"' if purpose_raw else '""',
            "action_url": '""',
            "action_text": '""',
        }
        text = CP_HERO_RE.sub(_frame_include(slug, fields) + "\n  ", text, count=1)
        text = ORPHAN_HERO_TAIL_RE.sub("\n  ", text, count=1)

    m = INLINE_CP_HEADER_RE.search(text)
    if m and FRAME not in text:
        title = m.group(1).strip()
        purpose = re.sub(r"\s+", " ", m.group(2).strip())
        fields = {"title": title, "subtitle": purpose, "action_url": '""', "action_text": '""'}
        text = INLINE_CP_HEADER_RE.sub(_frame_include(slug, fields) + "\n  ", text, count=1)

    m = REGISTRY_HEADER_RE.search(text)
    if m and FRAME not in text:
        title = m.group(1).strip()
        purpose = m.group(2).strip()
        fields = {"title": title, "subtitle": purpose, "action_url": '""', "action_text": '""'}
        text = REGISTRY_HEADER_RE.sub(_frame_include(slug, fields) + "\n  ", text, count=1)

    m = CONFIG_MODULE_HEADER_RE.search(text)
    if m and FRAME not in text:
        title = m.group(1).strip()
        purpose = m.group(2).strip()
        fields = {"title": title, "subtitle": purpose, "action_url": '""', "action_text": '""'}
        text = CONFIG_MODULE_HEADER_RE.sub(_frame_include(slug, fields) + "\n  ", text, count=1)

    m = INLINE_H4_RE.search(text)
    if m and FRAME not in text:
        title = m.group(1).strip()
        purpose = m.group(2).strip()
        fields = {"title": title, "subtitle": purpose, "action_url": '""', "action_text": '""'}
        text = INLINE_H4_RE.sub(_frame_include(slug, fields) + "\n  ", text, count=1)

    m = INLINE_H1_RE.search(text)
    if m and FRAME not in text:
        title = m.group(2).strip()
        fields = {"title": title, "subtitle": '""', "action_url": '""', "action_text": '""'}
        repl = _frame_include(slug, fields) + "\n  " + m.group(1)
        text = INLINE_H1_RE.sub(repl, text, count=1)

    if FRAME not in text and 'data-page-archetype="operational-workbench"' in text:
        text = _inject_after_phase8(text, slug)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def _iter_cp_targets() -> list[Path]:
    paths: list[Path] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        if rel in ALLOW_LANDING:
            continue
        if not any(rel.startswith(p) for p in CP_PREFIXES):
            if not rel.startswith("templates/schools/billing_dashboard"):
                continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-page-archetype="operational-workbench"' not in text:
            continue
        if FRAME in text:
            continue
        paths.append(path)
    return paths


def main() -> int:
    n = 0
    for path in _iter_cp_targets():
        if patch_file(path):
            n += 1
            print("patched", path.relative_to(ROOT))
    mig = ROOT / "templates/schools/super_migration_cloud.html"
    if mig.exists():
        t = mig.read_text(encoding="utf-8")
        t2 = re.sub(
            r'\s*\{% include "studio_os/components/page_header\.html"[^%]+%\}\s*',
            "\n",
            t,
            count=1,
        )
        if t2 != t:
            mig.write_text(t2, encoding="utf-8", newline="\n")
            print("patched", mig.relative_to(ROOT), "(removed duplicate header)")
            n += 1
    # py-4-only pass on all operational workbenches
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        if rel in ALLOW_LANDING:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-page-archetype="operational-workbench"' not in text:
            continue
        fixed = _fix_py4(text)
        fixed = _ensure_workbench_markers(fixed)
        if fixed != text:
            path.write_text(fixed, encoding="utf-8", newline="\n")
            print("py-2", path.relative_to(ROOT))
            n += 1
    print(f"apply_super_operational_frame: {n} changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
