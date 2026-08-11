#!/usr/bin/env python3
"""Platform-wide Django admin layout landmine sweep.

Catches classes the leftovers/canvas seals historically missed:
- numeric grid-row (empty tracks → stripe / right-void / stranded TOOLS)
- margin:auto on content/form frames (centered cramped column)
- overflow-wrap:anywhere on actions (letter-strip Save)
- content pages extending base_site without workspace markers
- cache-bust / SW drift for the current full-fill wave

Exit 0 only when zero P0/P1 findings.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_TPL = ROOT / "templates" / "admin"
REPORT = ROOT / "var" / "admin-surface-platformwide-sweep.json"

# Bump together with base_site ?v= and SW CACHE_VERSION on each layout wave.
EXPECTED_CACHE_BUST = "20260811-experience-runtime-v172"
EXPECTED_SW = "sms-v4.06.34-experience-runtime-2026-08-11"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_css_comments(s: str) -> str:
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def _admin_css_files() -> list[Path]:
    keys = (
        "admin",
        "django",
        "canvas",
        "unfold",
        "parity",
        "changelist",
        "workspace",
        "backoffice",
        "manager-shell",
    )
    out: list[Path] = []
    css_root = ROOT / "static" / "css"
    for p in css_root.rglob("*.css"):
        name = p.name.lower()
        if any(k in name for k in keys):
            out.append(p)
    tokens = css_root / "design-tokens.css"
    if tokens.is_file():
        out.append(tokens)
    return sorted(set(out))


def main() -> int:
    findings: list[tuple[str, str, int, str]] = []

    def add(sev: str, path: Path | str, line: int, msg: str) -> None:
        rel = Path(path)
        try:
            loc = rel.relative_to(ROOT).as_posix()
        except ValueError:
            loc = str(path).replace("\\", "/")
        findings.append((sev, loc, line, msg))

    css_files = _admin_css_files()
    canvas_family = (
        "rmc-admin-django-canvas",
        "admin-cp-parity",
        "admin-manager",
        "rmc-admin-workspace",
        "rmc-admin-changelist",
        "admin-cp-",
        "phase2-admin",
    )

    for p in css_files:
        raw = _read(p)
        css = _strip_css_comments(raw)
        rel = p.relative_to(ROOT).as_posix()
        in_family = any(k in rel for k in canvas_family)

        if in_family:
            for m in re.finditer(r"grid-row\s*:\s*(\d+(?:\s*/\s*span\s*\d+)?)", css):
                line = css[: m.start()].count("\n") + 1
                add("P0", p, line, f"numeric grid-row:{m.group(1).strip()}")

        for m in re.finditer(
            r"(#content(?:-main)?|\.cp-form-frame|\.rmc-django-workspace|#cp-main-content)"
            r"[^{]{0,140}\{[^}]{0,500}?margin(?:-inline)?\s*:\s*[^;]*\bauto\b",
            css,
            re.S | re.I,
        ):
            line = css[: m.start()].count("\n") + 1
            add("P0", p, line, "margin auto on admin content/form (centers → right void)")

        for m in re.finditer(
            r"(\.rmc-django-action|\.submit-row\b|a\.default\b|\.deletelink)"
            r"[^{]{0,80}\{[^}]*overflow-wrap\s*:\s*anywhere",
            css,
            re.S,
        ):
            line = css[: m.start()].count("\n") + 1
            add("P0", p, line, "overflow-wrap:anywhere on action/button (letter-strip)")

        if in_family:
            for m in re.finditer(
                r"(#content(?:-main)?|\.cp-form-frame|\.rmc-django-workspace)"
                r"[^{]{0,100}\{[^}]{0,400}?max-width\s*:\s*((?:\d{3,}(?:\.\d+)?)(?:px|rem))",
                css,
                re.S | re.I,
            ):
                line = css[: m.start()].count("\n") + 1
                add("P1", p, line, f"max-width clamp {m.group(2)} on content/form")

    # Templates extending base_site with content block
    skip_names = {
        "base.html",
        "base_site.html",
        "login.html",
        "popup_response.html",
        "prepopulated_fields_js.html",
        "actions.html",
        "date_hierarchy.html",
        "filter.html",
        "pagination.html",
        "search_form.html",
        "submit_line.html",
        "nav_sidebar.html",
    }
    skip_parts = (
        "/includes/",
        "/partials/",
        "/widgets/",
        "/auth/",
        "/components/",
        "/unfold/",
    )
    content_pages = 0
    for p in ADMIN_TPL.rglob("*.html"):
        posix = p.as_posix().replace("\\", "/")
        if p.name in skip_names or any(s in posix for s in skip_parts):
            continue
        t = _read(p)
        if 'extends "admin/base_site.html"' not in t and "extends 'admin/base_site.html'" not in t:
            continue
        if "{% block content %}" not in t:
            continue
        content_pages += 1
        if "rmc-django-workspace" not in t and "data-rmc-django-workspace" not in t:
            add("P0", p, 0, "base_site content page missing workspace marker")
        ends = list(re.finditer(r"\{%\s*endblock(?:\s+\w+)?\s*%\}", t))
        if ends:
            tail = re.sub(r"\{#.*?#\}", "", t[ends[-1].end() :], flags=re.S).strip()
            if "rmc-empty-state-sentinel" in tail or (
                tail and re.search(r"<(div|section|span|p|form)\b", tail)
            ):
                add("P1", p, 0, "orphan HTML after last endblock")

    base_site = _read(ADMIN_TPL / "base_site.html")
    m = re.search(r"\{%\s*block\s+nav-global\s*%\}(.*?)\{%\s*endblock", base_site, re.S)
    if m and "skip-link" in m.group(1):
        add("P0", ADMIN_TPL / "base_site.html", 0, "skip-link must not live in nav-global")
    if f"?v={EXPECTED_CACHE_BUST}" not in base_site:
        add("P0", ADMIN_TPL / "base_site.html", 0, f"cache bust ?v={EXPECTED_CACHE_BUST} missing")
    if "data-rmc-admin-html','unfold'" not in base_site and 'data-rmc-admin-html","unfold"' not in base_site:
        add("P0", ADMIN_TPL / "base_site.html", 0, "pre-paint data-rmc-admin-html=unfold missing")

    sw = _read(ROOT / "static" / "js" / "service-worker.js")
    if EXPECTED_SW not in sw:
        add("P0", ROOT / "static" / "js" / "service-worker.js", 0, f"SW must be {EXPECTED_SW}")

    canvas = _read(ROOT / "static" / "css" / "rmc-admin-django-canvas-contract.css")
    for seal in (
        "2026-07-20-grid-row-auto-fullfill",
        "2026-07-20-action-nowrap",
        "2026-07-19-tools-no-span-explode",
        "2026-07-20-platformwide-no-container",
        "2026-07-20-miss-nothing-label-wrap",
    ):
        if seal not in canvas:
            add("P0", ROOT / "static" / "css" / "rmc-admin-django-canvas-contract.css", 0, f"seal missing: {seal}")

    parity = _read(ROOT / "static" / "css" / "admin-cp-parity.css")
    if re.search(
        r"#content-main\.cp-form-frame[^{]*\{[^}]*margin:\s*0\s+auto",
        _strip_css_comments(parity),
        re.S,
    ):
        add("P0", ROOT / "static" / "css" / "admin-cp-parity.css", 0, "cp-form-frame margin:0 auto regress")

    # base.html must never put Tailwind container / mx-auto on #content
    base = _read(ADMIN_TPL / "base.html")
    content_m = re.search(r'<div id="content"[^>]*>', base)
    if not content_m:
        add("P0", ADMIN_TPL / "base.html", 0, '#content root missing')
    else:
        tag = content_m.group(0)
        if "mx-auto" in tag or re.search(r'\bcontainer\b', tag):
            add("P0", ADMIN_TPL / "base.html", 0, "#content must not use container or mx-auto (right void)")
        if "w-100" not in tag or "max-w-none" not in tag:
            add("P0", ADMIN_TPL / "base.html", 0, "#content must be w-100 max-w-none")

    # Inherited overflow-wrap:anywhere on the form frame = letter-strip Save/labels
    ws10 = _read(ROOT / "static" / "css" / "rmc-admin-workspace-10x.css")
    ws10_nc = _strip_css_comments(ws10)
    if re.search(
        r"#content-main\[data-rmc-admin-form-contract=\"premium-form-frame\"\]\s*\{[^}]*overflow-wrap\s*:\s*anywhere",
        ws10_nc,
        re.S,
    ):
        add("P0", ROOT / "static" / "css" / "rmc-admin-workspace-10x.css", 0, "#content-main form frame must not set overflow-wrap:anywhere")
    if re.search(
        r"premium-form-frame[^\n]{0,200}:is\([^)]*\blabel\b[^)]*\)\s*\{[^}]*overflow-wrap\s*:\s*anywhere",
        ws10_nc,
        re.S,
    ):
        add("P0", ROOT / "static" / "css" / "rmc-admin-workspace-10x.css", 0, "label must not use overflow-wrap:anywhere under form frame")

    # Admin templates must not clamp with max-w-5xl etc on primary banners
    for p in ADMIN_TPL.rglob("*.html"):
        t = _read(p)
        if re.search(r"\bmax-w-(?:3xl|4xl|5xl|6xl|7xl)\b", t):
            add("P1", p, 0, "admin template uses max-w-* clamp — prefer w-100 max-w-none")

    findings.sort(key=lambda x: (x[0], x[1], x[2]))
    by = Counter(f[0] for f in findings)
    hard = [f for f in findings if f[0] in ("P0", "P1")]
    print(f"DJANGO_ADMIN_PLATFORMWIDE_SWEEP={'PASS' if not hard else 'FAIL'}")
    print(f"css_files={len(css_files)} content_pages={content_pages} findings={len(findings)} by_sev={dict(by)}")
    for sev, path, line, msg in findings:
        loc = f"{path}:{line}" if line else path
        print(f"  [{sev}] {loc}  {msg}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "pass": not hard,
                "css_files": len(css_files),
                "content_pages": content_pages,
                "expected_cache_bust": EXPECTED_CACHE_BUST,
                "expected_sw": EXPECTED_SW,
                "findings": [
                    {"sev": a, "path": b, "line": c, "msg": d} for a, b, c, d in findings
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if not hard else 1


if __name__ == "__main__":
    sys.exit(main())
