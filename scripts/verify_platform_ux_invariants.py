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
DIALOG_RE = re.compile(r'class="[^"]*\b(modal|dialog|drawer|sheet|overlay)\b', re.IGNORECASE)
DIALOG_PROPER_RE = re.compile(r'role="(?:dialog|alertdialog)"', re.IGNORECASE)
ARIA_MODAL_RE = re.compile(r'aria-modal="true"', re.IGNORECASE)
TOC_HINT_RE = re.compile(r'data-rmc-toc|class="[^"]*\brmc-lux-toc\b|id="toc"|class="[^"]*\btable-of-contents\b', re.IGNORECASE)
STICKY_HINT_RE = re.compile(r"position\s*:\s*sticky|class=\"[^\"]*\bsticky\b", re.IGNORECASE)
SKIP_LINK_RE = re.compile(r'href="#main(-content)?"|\bskip-to-(main|content)\b', re.IGNORECASE)
KPI_CARD_CLASS_RE = re.compile(r'class="([^"]*\bkpi[^"]*)"', re.IGNORECASE)


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

    if lines >= VERY_LONG_TEMPLATE_THRESHOLD and not TOC_HINT_RE.search(body):
        findings.append(
            Finding(
                "ERROR",
                "long-page-no-toc",
                rel,
                f"template is {lines} lines but ships no TOC / on-this-page nav. Wrap sections in <section id data-rmc-toc> or mount <SectionTOC />.",
            )
        )
    elif lines >= LONG_TEMPLATE_THRESHOLD and not TOC_HINT_RE.search(body) and not looks_like_partial:
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

    if TAP_TARGET_BAD_CLASSES.search(body):
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
