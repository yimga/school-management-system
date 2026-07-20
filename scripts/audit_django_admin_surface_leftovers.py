#!/usr/bin/env python3
"""Zero-tolerance leftover scan for Django admin surfaces (operator + tenant).

Finds templates/pages that still violate the approved full-fill / school-config
engine contract. Exit 0 only when findings == 0.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "templates" / "admin"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[tuple[str, str, int, str]] = []

    def add(sev: str, path: Path, line: int, msg: str) -> None:
        findings.append((sev, path.as_posix().replace(str(ROOT).replace("\\", "/") + "/", ""), line, msg))

    banned = [
        (r"Tenant scoped", "Tenant scoped jargon"),
        (r"Tenant Administration", "Tenant Administration jargon"),
        (r"Tenant boundary", "Tenant boundary jargon"),
        (r"skip-link-theme", "legacy skip-link-theme class"),
        (r"Operator workflow hint", "operator wording on tenant banner"),
        (r">Decision console<", "Decision console wording"),
    ]

    for p in ADMIN.rglob("*.html"):
        lines = _read(p).splitlines()
        for i, line in enumerate(lines, 1):
            for pat, label in banned:
                if re.search(pat, line):
                    add("P0", p, i, f"{label}: {line.strip()[:120]}")
            if "studio_os:" in line:
                window = "\n".join(lines[max(0, i - 5) : i + 1])
                # Manager-only templates are OK without gate
                rel = p.as_posix()
                manager_only = "index_superadmin" in rel or "admin_operator_steering" in rel
                if not manager_only and "is_manager_host" not in window:
                    # extra_user_links wraps whole block; check file-level gate
                    file_txt = "\n".join(lines)
                    if "extra_user_links" in rel and file_txt.find("{% if is_manager_host %}") < file_txt.find("studio_os:"):
                        continue
                    if "app_list" in rel and "is_manager_host" in "\n".join(lines[max(0, i - 8) : i]):
                        continue
                    add("P1", p, i, f"unguarded studio_os link: {line.strip()[:120]}")

    core = {
        "change_form.html": 'data-rmc-django-workspace="change-form"',
        "change_list.html": "data-rmc-django-workspace",
        "app_index.html": "data-rmc-django-workspace",
        "index.html": "data-rmc-django-workspace",
        "index_tenant.html": "data-rmc-django-workspace",
        "index_superadmin.html": "data-rmc-django-workspace",
        "object_history.html": 'data-rmc-django-workspace="object-history"',
        "delete_confirmation.html": 'data-rmc-django-workspace="delete-confirm"',
        "delete_selected_confirmation.html": 'data-rmc-django-workspace="delete-confirm"',
    }
    for name, marker in core.items():
        p = ADMIN / name
        if not p.is_file():
            add("P0", p, 0, f"MISSING core template ({name})")
            continue
        if marker not in _read(p):
            add("P0", p, 0, f"missing workspace marker {marker}")

    # Continuous loop: every base_site content page must carry workspace markers
    # (partials / chrome / object-tools exempt).
    skip_names = {
        "base.html",
        "base_site.html",
        "login.html",
        "nav_sidebar.html",
        "sidebar_inner.html",
        "extra_user_links.html",
        "manager_cp_offcanvas.html",
        "app_list.html",
        "change_list_object_tools.html",
        "submit_line.html",
        "filter.html",
        "pagination.html",
        "actions.html",
        "date_hierarchy.html",
        "search_form.html",
        "object_history_form.html",
    }
    skip_parts = (
        "/includes/",
        "/partials/",
        "/components/",
        "/portal/partials/",
        "/compliance/partials/",
    )
    for p in ADMIN.rglob("*.html"):
        posix = p.as_posix().replace("\\", "/")
        if p.name in skip_names or any(s in posix for s in skip_parts):
            continue
        t = _read(p)
        if 'extends "admin/base_site.html"' not in t and "extends 'admin/base_site.html'" not in t:
            continue
        if "{% block content %}" not in t:
            continue
        if "rmc-django-workspace" not in t and "data-rmc-django-workspace" not in t:
            add("P0", p, 0, "base_site content page missing rmc-django-workspace marker")

    base_site = _read(ADMIN / "base_site.html")
    m = re.search(r"\{%\s*block\s+nav-global\s*%\}(.*?)\{%\s*endblock", base_site, re.S)
    if m and "skip-link" in m.group(1):
        add("P0", ADMIN / "base_site.html", 0, "skip-link must not live in nav-global")

    base = _read(ADMIN / "base.html")
    if 'class="skip-link"' not in base:
        add("P0", ADMIN / "base.html", 0, "canvas skip-link missing")
    if 'data-rmc-tenant-admin-chrome="1"' not in base:
        add("P0", ADMIN / "base.html", 0, "tenant single-chrome header marker missing")

    css = _read(ROOT / "static/css/rmc-admin-django-canvas-contract.css")
    if re.search(r"data-rmc-django-tools[\s\S]{0,220}grid-row:\s*3\s*/\s*span\s*(20|40)", css):
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "tools span 20/40 stripe bug regress")
    # Any active grid-row:N (not in comments) invents empty tracks → right void + stripes
    css_nocomment = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if re.search(
        r"\[data-rmc-django-(?:tools|side-panel|table-panel|changelist-rail|form-panel)\][^{]*\{[^}]*grid-row:\s*\d+",
        css_nocomment,
    ) or re.search(
        r"premium-form-frame[^{]*\{[^}]*grid-row:\s*\d+",
        css_nocomment,
    ) or re.search(
        r"\[data-rmc-admin-form-contract=\"premium-form-frame\"\][^{]*\{[^}]*grid-row:\s*\d+",
        css_nocomment,
    ):
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "hardcoded grid-row:N on workspace panes (stripe/right-void)")
    if "2026-07-19-tools-no-span-explode" not in css:
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "tools-no-span-explode seal missing")
    if "2026-07-20-action-nowrap" not in css:
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "action-nowrap save-bleed seal missing")
    if "2026-07-20-grid-row-auto-fullfill" not in css:
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "grid-row-auto-fullfill seal missing")
    if re.search(r"\.rmc-django-action\s*\{[^}]*overflow-wrap:\s*anywhere", css):
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, ".rmc-django-action must not use overflow-wrap:anywhere (save bleed)")
    # Bare Unfold .flex wrappers must not share form-row span-6 half-width
    if re.search(
        r"\.rmc-django-form-body\s*>\s*:is\([^)]*\.flex[^)]*\)\s*\{[^}]*grid-column:\s*span\s*6",
        css,
        re.S,
    ):
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "form-body > .flex must not use grid-column span 6")
    if "a.skip-link:not(:focus)" not in css:
        add("P0", ROOT / "static/css/rmc-admin-django-canvas-contract.css", 0, "skip-link clip until focus missing")

    parity = _read(ROOT / "static/css/admin-cp-parity.css")
    if re.search(
        r"#content-main\.cp-form-frame[^{]*\{[^}]*margin:\s*0\s+auto",
        parity,
        re.S,
    ):
        add("P0", ROOT / "static/css/admin-cp-parity.css", 0, "cp-form-frame must not use margin:0 auto (centers + right void)")

    banner = _read(ADMIN / "includes" / "tenant_admin_decision_banner.html")
    if "studio_os" in banner or "Decision console" in banner or "Operator workflow" in banner:
        add("P0", ADMIN / "includes" / "tenant_admin_decision_banner.html", 0, "tenant banner still operator/Studio")

    login = _read(ROOT / "templates" / "auth" / "tenant_admin_login.html")
    if "Tenant Administration" in login or "Tenant scoped" in login:
        add("P0", ROOT / "templates" / "auth" / "tenant_admin_login.html", 0, "tenant login jargon")

    # Host-gated Product control plane headings must keep else branch
    for p in ADMIN.rglob("change_form.html"):
        t = _read(p)
        if "Product control plane" in t and "Guided school settings" not in t:
            add("P1", p, 0, "Product control plane without Guided school settings tenant branch")

    # Orphan HTML after last {% endblock %} (common leftover sentinel dump)
    for p in ADMIN.rglob("*.html"):
        t = _read(p)
        ends = list(re.finditer(r"\{%\s*endblock(?:\s+\w+)?\s*%\}", t))
        if not ends:
            continue
        tail = t[ends[-1].end() :]
        if "rmc-empty-state-sentinel" in tail:
            add("P1", p, 0, "orphan rmc-empty-state-sentinel after last endblock")
        if re.search(r"<(div|section|span|p|form)\b", tail) and "rmc-empty-state-sentinel" not in tail:
            # Ignore trailing whitespace / comments only
            stripped = re.sub(r"\{#.*?#\}", "", tail, flags=re.S).strip()
            if stripped and "<" in stripped:
                add("P2", p, 0, f"orphan HTML after last endblock: {stripped[:80]!r}")

    findings.sort(key=lambda x: (x[0], x[1], x[2]))
    print(f"DJANGO_ADMIN_SURFACE_LEFTOVERS={'PASS' if not findings else 'FAIL'}")
    print(f"findings={len(findings)} by_sev={dict(Counter(f[0] for f in findings))}")
    for sev, path, line, msg in findings:
        loc = f"{path}:{line}" if line else path
        print(f"  [{sev}] {loc}  {msg}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
