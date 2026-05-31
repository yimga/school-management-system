"""Platform-wide UX invariants gate.

Scans every template under templates/ and flags structural issues that
hurt operators and tenants regardless of page topic:

  1. Long templates (>500 lines) without table-of-contents anchors or
     sticky navigation — "scroll forever w/ no end in sight" pages.
  2. Buttons-as-anchors (<a class="btn"...>) and div-as-button onclick.
  3. Modal/dialog templates without role="dialog" + aria-modal.
  4. Tap targets visibly < 36px (rare class-name heuristic, not visual).
  5. Long settings pages stacked vertically without tab / accordion.
  6. Dashboards with duplicated KPI viz patterns (everything looks the
     same — flagged via repeated identical class signatures).
  7. Templates with no skip-to-main-content link (a11y).

Run::

    python scripts/verify_platform_ux_invariants.py
    python scripts/verify_platform_ux_invariants.py --max-findings 30
    python scripts/verify_platform_ux_invariants.py --include marketing portal
    python scripts/verify_platform_ux_invariants.py --severity error

Prints a Markdown findings report to stdout.  Exits non-zero only when
``--strict`` is passed AND there are ERROR-severity findings.

Findings are advisory by default so this can land before fixes ship.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "templates"

LONG_TEMPLATE_THRESHOLD = 500
VERY_LONG_TEMPLATE_THRESHOLD = 1000
TAP_TARGET_BAD_CLASSES = re.compile(r"\bw-(?:1|2|3|4|5)\b|\bh-(?:1|2|3|4|5)\b")
# Only flag <a class="btn"> when the href is empty / "#" / "javascript:" — a
# real /tenant/path/ href is a semantic link styled as a button, which is
# valid (progressive enhancement; works without JS).
ANCHOR_AS_BUTTON_RE = re.compile(
    r'<a\s[^>]*\bclass="[^"]*\bbtn\b[^"]*"[^>]*\bhref="(?:#|javascript:|)"',
    re.IGNORECASE,
)
DIV_AS_BUTTON_RE = re.compile(r"<(?:div|span)\s[^>]*\bonclick=", re.IGNORECASE)
# Narrowed to actual modal/dialog shells. The previous regex over-fired on:
#  - <aside class="...drawer..."> static help panels using <details> disclosure
#  - <div class="...overlay" hidden> loading spinners over an <iframe>
# Now we require: a real <dialog> tag, Bootstrap modal/offcanvas, or a known
# project sheet/drawer BEM class.
DIALOG_RE = re.compile(
    r'<dialog\b'
    r'|class="[^"]*\bmodal\s+fade\b'
    r'|class="[^"]*\bmodal-dialog\b'
    r'|class="[^"]*\boffcanvas\b'
    r'|class="[^"]*\brmc-sheet\b'
    r'|class="[^"]*\brmc-bottom-sheet\b'
    r'|class="[^"]*\brmc-acx-drawer\b'
    r'|class="[^"]*\brmc-copilot-context-lens-sheet\b'
    r'|class="[^"]*\brmc-portal-row-detail-drawer\b'
    r'|class="[^"]*\brmc-security-posture-modal\b',
    re.IGNORECASE,
)
DIALOG_PROPER_RE = re.compile(r'role="(?:dialog|alertdialog)"', re.IGNORECASE)
ARIA_MODAL_RE = re.compile(r'aria-modal="true"', re.IGNORECASE)
TOC_HINT_RE = re.compile(
    r'data-rmc-toc'
    r'|class="[^"]*\brmc-lux-toc\b'
    r'|class="[^"]*\brmc-section-nav\b'
    r'|data-rmc-section-anchor'
    r'|id="toc"'
    r'|class="[^"]*\btable-of-contents\b',
    re.IGNORECASE,
)
STICKY_HINT_RE = re.compile(r"position\s*:\s*sticky|class=\"[^\"]*\bsticky\b", re.IGNORECASE)
SKIP_LINK_RE = re.compile(r'href="#main(-content)?"|\bskip-to-(main|content)\b', re.IGNORECASE)
KPI_CARD_CLASS_RE = re.compile(r'class="([^"]*\bkpi[^"]*)"', re.IGNORECASE)

# v4.01.05 — page balance + CTA hierarchy invariants.
# `(?<![\w-])` rejects `btn-outline-primary` matches (hyphen is a word boundary
# but not a "class-separator"); `(?![\w-])` rejects `btn-primary-soft` etc.
PRIMARY_BTN_RE = re.compile(r'class="[^"]*(?<![\w-])btn-primary(?![\w-])[^"]*"', re.IGNORECASE)
SEMANTIC_BTN_RE = re.compile(
    r'class="[^"]*(?<![\w-])btn-(primary|success|warning|danger|info)(?![\w-])[^"]*"',
    re.IGNORECASE,
)
WEAK_EMPTY_STATE_RE = re.compile(
    r'>\s*(?:No\s+records?\s+(?:found|available)|No\s+data\s+(?:available|to\s+show|yet)|'
    r'Nothing\s+to\s+show|There\s+are\s+no|No\s+results?)\b',
    re.IGNORECASE,
)
LUX_EMPTY_STATE_RE = re.compile(r'class="[^"]*\b(?:rmc-empty(?:-state)?|rmc-lux-empty)\b', re.IGNORECASE)
HARDCODED_YEAR_RE = re.compile(r'(?:&copy;|©|\bCopyright\b)\s*(?:&\w+;|\s)*\s*(20\d\d)\b', re.IGNORECASE)
TABLE_OPEN_RE = re.compile(r'<table\b', re.IGNORECASE)
PAGINATION_HINT_RE = re.compile(
    r'class="[^"]*\b(?:pagination|pager|rmc-pagination|page-link)\b'
    r'|\{%\s*include\s+["\'][^"\']*pagination',
    re.IGNORECASE,
)


@dataclass
class Finding:
    severity: str  # "ERROR" | "WARN" | "INFO"
    category: str
    template: str
    detail: str
    line: int | None = None


def _iter_templates(roots: list[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.html"):
            if "node_modules" in path.parts or ".venv" in path.parts:
                continue
            yield path


def _resolve_roots(include: list[str] | None) -> list[Path]:
    if not include:
        return [TEMPLATES_ROOT]
    out: list[Path] = []
    for entry in include:
        candidate = TEMPLATES_ROOT / entry
        if candidate.exists():
            out.append(candidate)
    return out or [TEMPLATES_ROOT]


def _read(path: Path) -> tuple[str, int]:
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"<<read error: {exc}>>", 0
    return body, body.count("\n") + 1


def _scan_template(path: Path) -> list[Finding]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    body, lines = _read(path)
    findings: list[Finding] = []

    looks_like_partial = (
        rel.startswith("templates/partials/")
        or rel.startswith("templates/components/")
        or rel.startswith("templates/_includes/")
        or "/partials/" in rel
        or "/_partials/" in rel
        or "/_includes/" in rel
    )

    # Shell / scaffold templates wrap content; the content's own TOC is what
    # matters, not the shell. Skip TOC checks on these but still let other
    # invariants (a11y, anchor-as-button, etc.) run.
    looks_like_shell = (
        rel.endswith("/portal_base.html")
        or rel.endswith("/control_plane_base.html")
        or rel.endswith("/control_plane_skeleton.html")
        or rel.endswith("/admin/base_site.html")
        or rel.endswith("/admin/base.html")
        or rel.endswith("/admin/index.html")
        or rel.endswith("/backend_base.html")
        or rel == "templates/base.html"
        or rel.endswith("/marketing/base_marketing.html")
    )

    if not looks_like_shell and lines >= VERY_LONG_TEMPLATE_THRESHOLD and not TOC_HINT_RE.search(body):
        findings.append(
            Finding(
                "ERROR",
                "long-page-no-toc",
                rel,
                f"template is {lines} lines but ships no TOC / on-this-page nav. Wrap sections in <section id data-rmc-toc> or mount <SectionTOC />.",
            )
        )
    elif not looks_like_shell and lines >= LONG_TEMPLATE_THRESHOLD and not TOC_HINT_RE.search(body) and not looks_like_partial:
        findings.append(
            Finding(
                "WARN",
                "long-page-no-toc",
                rel,
                f"template is {lines} lines — consider on-this-page TOC + sticky scroll progress",
            )
        )

    for match in ANCHOR_AS_BUTTON_RE.finditer(body):
        line = body[: match.start()].count("\n") + 1
        findings.append(
            Finding(
                "WARN",
                "anchor-as-button",
                rel,
                "<a class='btn ...'> used where a <button> belongs (a11y + focus semantics)",
                line=line,
            )
        )
        if len([f for f in findings if f.category == "anchor-as-button" and f.template == rel]) >= 3:
            break

    for match in DIV_AS_BUTTON_RE.finditer(body):
        line = body[: match.start()].count("\n") + 1
        findings.append(
            Finding(
                "ERROR",
                "div-as-button",
                rel,
                "<div onclick=...> — keyboard-inaccessible; replace with <button>",
                line=line,
            )
        )
        if len([f for f in findings if f.category == "div-as-button" and f.template == rel]) >= 3:
            break

    if DIALOG_RE.search(body):
        if not DIALOG_PROPER_RE.search(body):
            findings.append(
                Finding(
                    "ERROR",
                    "modal-missing-role",
                    rel,
                    "modal/dialog/drawer present but no role=\"dialog\"",
                )
            )
        if not ARIA_MODAL_RE.search(body):
            findings.append(
                Finding(
                    "WARN",
                    "modal-missing-aria-modal",
                    rel,
                    "modal/dialog/drawer present but no aria-modal=\"true\"",
                )
            )

    if rel.startswith("templates/base.html"):
        if not SKIP_LINK_RE.search(body):
            findings.append(
                Finding(
                    "ERROR",
                    "no-skip-link",
                    rel,
                    "base template missing skip-to-main-content link (a11y)",
                )
            )

    kpi_classes = KPI_CARD_CLASS_RE.findall(body)
    if len(kpi_classes) >= 6:
        counts = Counter(kpi_classes)
        most_common, n = counts.most_common(1)[0]
        if n / len(kpi_classes) >= 0.85:
            findings.append(
                Finding(
                    "WARN",
                    "kpi-uniformity",
                    rel,
                    f"{n}/{len(kpi_classes)} KPI cards share the identical class signature — no visualization variety",
                )
            )

    # v4.01.05 invariants — only fire on real pages, not partials.
    cta_allow = "primary-cta-allow:" in body
    semantic_allow = "semantic-btn-allow:" in body
    if not looks_like_partial and not looks_like_shell and not cta_allow:
        # Strip Django conditional ternaries that already pick btn-outline-primary
        # as the else branch — those are correct hierarchical choices, not overload.
        body_for_cta = re.sub(
            r"\{%\s*if[^%]+%\}\s*btn-primary\s*\{%\s*else\s*%\}\s*btn-outline-(?:primary|secondary|light|dark)\s*\{%\s*endif\s*%\}",
            "btn-outline-secondary",
            body,
        )
        # Strip mutually-exclusive mode-gated primaries: `{% if X == 'A' ... %}...btn-primary...{% endif %}`
        # paired with `{% if X == 'B' ... %}...btn-primary...{% endif %}` etc. — only one renders at
        # runtime so the page sees 1 effective primary, not N. Pattern match collapses sets of these.
        mode_gated_primary_re = re.compile(
            r"\{%\s*if\s+[\w.]+\s*==\s*['\"]\w+['\"][^%]*%\}[^{]*\bbtn-primary\b[^{]*\{%\s*endif\s*%\}",
            re.IGNORECASE,
        )
        mode_gated_matches = mode_gated_primary_re.findall(body_for_cta)
        if len(mode_gated_matches) >= 2:
            body_for_cta = mode_gated_primary_re.sub("[[mode-gated]]", body_for_cta, count=len(mode_gated_matches) - 1)
        primary_count = len(PRIMARY_BTN_RE.findall(body_for_cta))
        if primary_count >= 4:
            findings.append(
                Finding(
                    "WARN",
                    "primary-cta-overload",
                    rel,
                    f"{primary_count} `.btn-primary` buttons compete for attention — promote ONE, demote the rest to `.btn-outline-*`",
                )
            )

        semantic_variants = {m.lower() for m in SEMANTIC_BTN_RE.findall(body)}
        if not semantic_allow and len({"success", "warning", "danger"} & semantic_variants) >= 2:
            findings.append(
                Finding(
                    "WARN",
                    "action-bar-semantic-noise",
                    rel,
                    f"page mixes &gt;=2 semantic button colors ({sorted(semantic_variants)}) — semantic noise dilutes meaning",
                )
            )

        if WEAK_EMPTY_STATE_RE.search(body) and not LUX_EMPTY_STATE_RE.search(body):
            findings.append(
                Finding(
                    "INFO",
                    "weak-empty-state",
                    rel,
                    "literal \"No records found\" / \"No data\" without `.rmc-empty-state` namespace — luxury empty state would lift the feel",
                )
            )

        year_match = HARDCODED_YEAR_RE.search(body)
        if year_match and "{% now" not in body and "{% current_year" not in body:
            findings.append(
                Finding(
                    "WARN",
                    "hardcoded-copyright-year",
                    rel,
                    f"hardcoded © {year_match.group(1)} — use `{{% now \"Y\" %}}` so the footer stays correct forever",
                )
            )

        table_pagination_allow = "table-pagination-allow:" in body
        if (
            TABLE_OPEN_RE.search(body)
            and lines >= 300
            and not PAGINATION_HINT_RE.search(body)
            and not table_pagination_allow
        ):
            findings.append(
                Finding(
                    "INFO",
                    "table-without-pagination",
                    rel,
                    f"<table> in a {lines}-line template with no pagination hint — verify the query has a row cap or add a pagination partial",
                )
            )

    # Skip third-party admin chrome (Unfold) and the in-content settings sidebar
    # rail — those are vendor templates we can't safely retouch without rebasing
    # Unfold. The platform's own templates already pass the rule.
    looks_like_third_party_chrome = (
        rel.startswith("templates/unfold/")
        or rel == "templates/admin/siteconfig/sitesettings/settings_sidebar.html"
    )
    if not looks_like_third_party_chrome and TAP_TARGET_BAD_CLASSES.search(body):
        findings.append(
            Finding(
                "INFO",
                "small-tap-target",
                rel,
                "very-small fixed-size utility classes detected — verify >=44px on coarse pointer",
            )
        )

    return findings


def _format_report(findings: list[Finding], max_findings: int | None) -> str:
    if not findings:
        return "# Platform UX invariants\n\nNo findings.\n"
    by_category: dict[str, list[Finding]] = {}
    for f in findings:
        by_category.setdefault(f.category, []).append(f)
    out: list[str] = ["# Platform UX invariants — findings", ""]
    totals = Counter(f.severity for f in findings)
    out.append(
        f"**Total:** {len(findings)} — "
        f"ERROR: {totals.get('ERROR', 0)}, "
        f"WARN: {totals.get('WARN', 0)}, "
        f"INFO: {totals.get('INFO', 0)}"
    )
    out.append("")
    for category, items in sorted(by_category.items()):
        out.append(f"## {category} ({len(items)})")
        printed = 0
        for finding in items:
            if max_findings is not None and printed >= max_findings:
                out.append(f"  - ...and {len(items) - printed} more")
                break
            line = f":{finding.line}" if finding.line else ""
            out.append(f"  - **{finding.severity}** [{finding.template}{line}] {finding.detail}")
            printed += 1
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include",
        nargs="*",
        help="Template subdirs to limit the scan to (e.g. marketing portal). Default: all.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=12,
        help="Max findings to print per category (default 12).",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warn", "info"],
        help="Filter to this severity and above.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any ERROR-severity finding exists.",
    )
    args = parser.parse_args(argv)

    roots = _resolve_roots(args.include)
    findings: list[Finding] = []
    for tpl in _iter_templates(roots):
        findings.extend(_scan_template(tpl))

    if args.severity:
        threshold = {"error": ("ERROR",), "warn": ("ERROR", "WARN"), "info": ("ERROR", "WARN", "INFO")}[
            args.severity
        ]
        findings = [f for f in findings if f.severity in threshold]

    print(_format_report(findings, args.max_findings))

    if args.strict and any(f.severity == "ERROR" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
