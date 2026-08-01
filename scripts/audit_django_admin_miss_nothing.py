#!/usr/bin/env python3
"""
MISS-NOTHING Django admin surface audit — operator + tenant, entire tree.

This is the authoritative gate for the layout class we keep re-shipping:
  right void / cramped center column / venetian stripes / stranded TOOLS /
  letter-strip Save / visible skip-link / missing workspace markers.

Covers:
  - Every templates/admin/**/*.html (inheritance + content wipe + clamps)
  - Every admin-family CSS sheet (grid-row, margin:auto, dangerous wrap, clamps)
  - base.html / base_site.html chrome contracts
  - Unfold admin chrome helpers
  - Cache bust + SW + canvas seals
  - Host-agnostic: admin-manager-shell AND admin-premium-shell

Exit 0 only when zero P0/P1 findings.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "templates" / "admin"
UNFOLD = ROOT / "templates" / "unfold"
REPORT = ROOT / "var" / "django_admin_miss_nothing_audit.json"

EXPECTED_CACHE_BUST = "20260801-admin-os-v160-tenant-configuration-operations"
EXPECTED_SW = "sms-v4.06.25-tenant-configuration-operations-2026-08-01"

REQUIRED_SEALS = (
    "2026-07-19-tools-no-span-explode",
    "2026-07-20-action-nowrap",
    "2026-07-20-grid-row-auto-fullfill",
    "2026-07-20-platformwide-no-container",
    "2026-07-20-miss-nothing-label-wrap",
)

WORKSPACE_PARENTS = frozenset(
    {
        "admin/change_form.html",
        "admin/change_list.html",
        "admin/app_index.html",
        "admin/index.html",
        "admin/index_tenant.html",
        "admin/index_superadmin.html",
    }
)

CSS_NAME_KEYS = (
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

# Selectors that must NEVER be the *subject* of overflow-wrap:anywhere.
DANGEROUS_WRAP_SUBJECTS = (
    r"\blabel\b",
    r"\.form-row\b",
    r"\.rmc-django-action\b",
    r"\.submit-row\b",
    r"#content-main\b",
    r"\.cp-form-frame\b",
    r"^button$",
    r"input\[type=[\"']submit[\"']\]",
)


def _selector_subjects(sel: str) -> list[str]:
    """Return subject selector texts (last compound / :is() insides)."""
    subjects: list[str] = []
    # Drop trailing { debris; normalize whitespace
    sel = re.sub(r"\s+", " ", sel).strip().rstrip("{").strip()
    for part in sel.split(","):
        part = part.strip()
        if not part:
            continue
        is_m = re.search(r":is\((.*)\)\s*$", part, re.S)
        if is_m:
            insides = is_m.group(1)
            for piece in insides.split(","):
                piece = piece.strip()
                if piece:
                    subjects.append(piece)
            continue
        # last simple selector in the descendant chain
        subjects.append(part.split()[-1])
    return subjects


def _subjects_are_dangerous(subjects: list[str]) -> str | None:
    for sub in subjects:
        for tok in DANGEROUS_WRAP_SUBJECTS:
            if re.search(tok, sub):
                return tok
    return None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_css(s: str) -> str:
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _admin_css() -> list[Path]:
    out: list[Path] = []
    css_root = ROOT / "static" / "css"
    for p in css_root.rglob("*.css"):
        if any(k in p.name.lower() for k in CSS_NAME_KEYS):
            out.append(p)
    tokens = css_root / "design-tokens.css"
    if tokens.is_file():
        out.append(tokens)
    return sorted(set(out))


def main() -> int:
    findings: list[tuple[str, str, int, str]] = []

    def add(sev: str, path: Path | str, line: int, msg: str) -> None:
        findings.append((sev, _rel(Path(path)) if not isinstance(path, str) else path.replace("\\", "/"), line, msg))

    # ------------------------------------------------------------------ CSS
    for p in _admin_css():
        raw = _read(p)
        css = _strip_css(raw)
        rel = _rel(p)

        for m in re.finditer(r"grid-row\s*:\s*(\d+(?:\s*/\s*span\s*\d+)?)", css):
            add("P0", p, css[: m.start()].count("\n") + 1, f"numeric grid-row:{m.group(1).strip()}")

        for m in re.finditer(
            r"(#content(?:-main)?|\.cp-form-frame|\.rmc-django-workspace|#cp-main-content)"
            r"[^{]{0,160}\{[^}]{0,600}?margin(?:-inline)?\s*:\s*[^;]*\bauto\b",
            css,
            re.S | re.I,
        ):
            add("P0", p, css[: m.start()].count("\n") + 1, "margin:auto on content/form (right void)")

        # Dangerous wrap: only flag when the *subject* is banned (not ancestors).
        for m in re.finditer(r"([^{}@][^{]*)\{([^}]*)\}", css):
            sel, body = m.group(1), m.group(2)
            if not re.search(r"overflow-wrap\s*:\s*anywhere", body):
                continue
            hit = _subjects_are_dangerous(_selector_subjects(sel))
            if hit:
                line = css[: m.start()].count("\n") + 1
                add(
                    "P0",
                    p,
                    line,
                    f"overflow-wrap:anywhere on dangerous subject ({hit}) — letter-strip/cramp risk",
                )

        for m in re.finditer(
            r"(#content(?:-main)?|\.cp-form-frame|\.rmc-django-workspace)"
            r"[^{]{0,120}\{[^}]{0,500}?max-width\s*:\s*((?:\d{3,}(?:\.\d+)?)(?:px|rem))",
            css,
            re.S | re.I,
        ):
            add("P1", p, css[: m.start()].count("\n") + 1, f"max-width clamp {m.group(2)} on content/form")

    # ------------------------------------------------------------------ templates/admin
    skip_parts = ("/includes/", "/partials/", "/widgets/", "/components/")
    skip_names = {
        "base.html",
        "base_site.html",
        "login.html",
        "popup_response.html",
        "actions.html",
        "filter.html",
        "pagination.html",
        "search_form.html",
        "submit_line.html",
        "nav_sidebar.html",
        "date_hierarchy.html",
        "prepopulated_fields_js.html",
        "app_list.html",
    }

    content_pages = 0
    for p in ADMIN.rglob("*.html"):
        posix = _rel(p)
        t = _read(p)

        # max-w clamps in any admin template
        if re.search(r"\bmax-w-(?:3xl|4xl|5xl|6xl|7xl)\b", t):
            add("P1", p, 0, "admin template uses max-w-* clamp")

        # id=content with container/mx-auto anywhere under admin/
        for m in re.finditer(r'<div[^>]*\bid=["\']content["\'][^>]*>', t):
            tag = m.group(0)
            if "mx-auto" in tag or re.search(r"\bcontainer\b", tag):
                add("P0", p, t[: m.start()].count("\n") + 1, "#content has container or mx-auto")

        ext = re.search(r"extends\s+['\"]([^'\"]+)['\"]", t)
        ext_target = ext.group(1) if ext else ""

        # Direct base_site content pages need workspace markers
        if ext_target == "admin/base_site.html" and "{% block content %}" in t:
            if p.name in skip_names or any(s in posix for s in skip_parts):
                continue
            content_pages += 1
            if "rmc-django-workspace" not in t and "data-rmc-django-workspace" not in t:
                add("P0", p, 0, "base_site content page missing workspace marker")

        # Children of workspace parents must not wipe content without block.super
        if ext_target in WORKSPACE_PARENTS and "{% block content %}" in t:
            bm = re.search(
                r"\{%\s*block\s+content\s*%\}(.*?)\{%\s*endblock(?:\s+content)?\s*%\}",
                t,
                re.S,
            )
            body = bm.group(1) if bm else ""
            cleaned = re.sub(r"\{#.*?#\}", "", body, flags=re.S).strip()
            if cleaned and "block.super" not in body:
                add(
                    "P0",
                    p,
                    0,
                    f"overrides content of {ext_target} without {{{{ block.super }}}} (wipes workspace)",
                )

        # Orphan HTML after last endblock
        if p.name not in skip_names and "/includes/" not in posix:
            ends = list(re.finditer(r"\{%\s*endblock(?:\s+\w+)?\s*%\}", t))
            if ends:
                tail = re.sub(r"\{#.*?#\}", "", t[ends[-1].end() :], flags=re.S).strip()
                if "rmc-empty-state-sentinel" in tail or (
                    tail and re.search(r"<(div|section|span|p|form)\b", tail)
                ):
                    add("P1", p, 0, "orphan HTML after last endblock")

    # ------------------------------------------------------------------ chrome contracts
    base = _read(ADMIN / "base.html")
    base_site = _read(ADMIN / "base_site.html")

    content_m = re.search(r'<div id="content"[^>]*>', base)
    if not content_m:
        add("P0", ADMIN / "base.html", 0, "#content root missing")
    else:
        tag = content_m.group(0)
        if "mx-auto" in tag or re.search(r"\bcontainer\b", tag):
            add("P0", ADMIN / "base.html", 0, "#content must not use container/mx-auto")
        if "w-100" not in tag or "max-w-none" not in tag:
            add("P0", ADMIN / "base.html", 0, "#content must be w-100 max-w-none")

    if 'class="skip-link"' not in base:
        add("P0", ADMIN / "base.html", 0, "canvas skip-link missing")
    if "skip-link-theme" in base or "visually-hidden-focusable" in base:
        add("P0", ADMIN / "base.html", 0, "skip-link must not use Bootstrap-only classes")

    ng = re.search(r"\{%\s*block\s+nav-global\s*%\}(.*?)\{%\s*endblock", base_site, re.S)
    if ng and "skip-link" in ng.group(1):
        add("P0", ADMIN / "base_site.html", 0, "skip-link must not live in nav-global")

    if f"?v={EXPECTED_CACHE_BUST}" not in base_site:
        add("P0", ADMIN / "base_site.html", 0, f"cache bust ?v={EXPECTED_CACHE_BUST} missing")
    if "data-rmc-admin-html','unfold'" not in base_site and 'data-rmc-admin-html","unfold"' not in base_site:
        add("P0", ADMIN / "base_site.html", 0, "pre-paint data-rmc-admin-html=unfold missing")

    sw = _read(ROOT / "static" / "js" / "service-worker.js")
    if EXPECTED_SW not in sw:
        add("P0", "static/js/service-worker.js", 0, f"SW must be {EXPECTED_SW}")

    canvas = _read(ROOT / "static" / "css" / "rmc-admin-django-canvas-contract.css")
    for seal in REQUIRED_SEALS:
        if seal not in canvas:
            add("P0", "static/css/rmc-admin-django-canvas-contract.css", 0, f"seal missing: {seal}")

    # skip-link clip present for both hosts
    if "a.skip-link:not(:focus)" not in canvas:
        add("P0", "static/css/rmc-admin-django-canvas-contract.css", 0, "skip-link clip until focus missing")

    parity = _strip_css(_read(ROOT / "static" / "css" / "admin-cp-parity.css"))
    if re.search(r"#content-main\.cp-form-frame[^{]*\{[^}]*margin:\s*0\s+auto", parity, re.S):
        add("P0", "static/css/admin-cp-parity.css", 0, "cp-form-frame margin:0 auto regress")

    # Unfold header must not reintroduce container/mx-auto
    header = UNFOLD / "helpers" / "header.html"
    if header.is_file():
        ht = _read(header)
        if re.search(r"\bcontainer\b", ht) or "mx-auto" in ht:
            add("P0", header, 0, "unfold header must not use container/mx-auto")

    # Core workspace templates exist with markers
    for name, marker in (
        ("change_form.html", 'data-rmc-django-workspace="change-form"'),
        ("change_list.html", "data-rmc-django-workspace"),
        ("app_index.html", 'data-rmc-django-workspace="app-index"'),
        ("index_tenant.html", "data-rmc-django-workspace"),
        ("index_superadmin.html", "data-rmc-django-workspace"),
        ("object_history.html", 'data-rmc-django-workspace="object-history"'),
        ("delete_confirmation.html", 'data-rmc-django-workspace="delete-confirm"'),
        ("delete_selected_confirmation.html", 'data-rmc-django-workspace="delete-confirm"'),
    ):
        tp = ADMIN / name
        if not tp.is_file():
            add("P0", tp, 0, "core template missing")
            continue
        if marker not in _read(tp):
            add("P0", tp, 0, f"missing workspace marker {marker}")

    findings.sort(key=lambda x: (x[0], x[1], x[2]))
    hard = [f for f in findings if f[0] in ("P0", "P1")]
    by = Counter(f[0] for f in findings)
    print(f"DJANGO_ADMIN_MISS_NOTHING={'PASS' if not hard else 'FAIL'}")
    print(
        f"css_files={len(_admin_css())} content_pages={content_pages} "
        f"findings={len(findings)} by_sev={dict(by)}"
    )
    for sev, path, line, msg in findings:
        loc = f"{path}:{line}" if line else path
        print(f"  [{sev}] {loc}  {msg}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "pass": not hard,
                "expected_cache_bust": EXPECTED_CACHE_BUST,
                "expected_sw": EXPECTED_SW,
                "content_pages": content_pages,
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
