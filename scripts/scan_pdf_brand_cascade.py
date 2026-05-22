"""Scan: PDF / print templates must route through the per-tenant brand cascade.

The bug class this catches (per-tenant transcripts / report cards / invoices
all rendering with the platform default brand color instead of the school's):

    templates/finance/invoice_pdf.html
        <h1 style="color: #4f46e5;">Invoice</h1>      ← hardcoded RMC indigo
        # — operator's school brand never wins

The v3.57.0 print-v2 layer (`rmc-print-v2.css`) ships `--rmc-print-brand-primary`
and `--rmc-print-brand-accent` cascade hooks. PDF / print templates should
either:
  * Use the `.rmc-print-v2` class wrapper + the `__brand-block` partial
    (preferred), OR
  * Reference brand via `var(--brand-primary)` / `var(--brand-accent)`
    in inline style attributes.

Hardcoded hex / rgb literals in PDF / print templates' inline styles trip
this scanner.

Scope:
  * `templates/**/*.html` whose path contains any of:
      print / pdf / invoice / transcript / receipt / report_card / certificate
    OR whose <body> / wrapper class includes `rmc-print` / `rmc-print-v2`.

Allow markers:
  * `<!-- pdf-brand-cascade-allow: <reason> -->` on the line of the offending
    inline style (e.g. fixed-color legal stamps, watermark).

Zero-tolerance gate from day 1 (v3.57.1, 2026-05-21).

Usage:
    python scripts/scan_pdf_brand_cascade.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "templates"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-pdf-brand-cascade.json"

PRINT_PDF_PATH_SEGMENTS = (
    "print",
    "pdf",
    "invoice",
    "transcript",
    "receipt",
    "report_card",
    "reportcard",
    "certificate",
)

INLINE_STYLE_RE = re.compile(
    r"""style\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
HEX_RGB_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)")
COLOR_PROP_RE = re.compile(
    r"(color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?(?:-color)?)\s*:\s*([^;]+)",
    re.IGNORECASE,
)
RMC_PRINT_WRAPPER_RE = re.compile(r"class\s*=\s*[\"'][^\"']*rmc-print(?:-v2)?\b", re.IGNORECASE)
ALLOW_MARKER = "pdf-brand-cascade-allow:"


def _is_pdf_print_template(path: pathlib.Path, text: str) -> bool:
    parts = [p.lower() for p in path.parts]
    name = path.name.lower()
    for seg in PRINT_PDF_PATH_SEGMENTS:
        if any(seg in p for p in parts) or seg in name:
            return True
    # Fallback: the template wraps its body in .rmc-print* class
    return bool(RMC_PRINT_WRAPPER_RE.search(text))


def scan_file(path: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not _is_pdf_print_template(path, text):
        return []
    lines = text.splitlines()
    findings: list[str] = []
    for i, line in enumerate(lines, 1):
        if ALLOW_MARKER in line:
            continue
        for sm in INLINE_STYLE_RE.finditer(line):
            style_body = sm.group(1)
            for cm in COLOR_PROP_RE.finditer(style_body):
                value = cm.group(2)
                # var(...) values cascade — skip them.
                if "var(" in value and not HEX_RGB_RE.search(
                    re.sub(r"var\([^)]*\)", "", value)
                ):
                    continue
                if HEX_RGB_RE.search(value):
                    findings.append(
                        f"{path.relative_to(REPO_ROOT)}:{i}: "
                        f"{cm.group(1)}: {value.strip()[:80]}"
                    )
                    break
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    if not TEMPLATES_ROOT.exists():
        return findings
    for html in TEMPLATES_ROOT.rglob("*.html"):
        findings.extend(scan_file(html))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_all()
    total = len(findings)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps(
                {"finding_count": total, "findings": findings},
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": total,
                    "baseline": baseline_total,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"pdf-brand-cascade scan: {total} hardcoded color(s) in print/PDF templates")
        print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")
        if len(findings) > 30:
            print(f"  … {len(findings) - 30} more")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
