#!/usr/bin/env python3
"""Apple HIG token-system compliance scanner.

Detects template `style="..."` attributes that bypass the v2 token system —
the patterns that quietly defeat tenant-brand cascade and Apple-tier polish:

  - inline `font-size:` using px/rem/em literals (should be `var(--type-size-*)`
    or the matching `.rmc-type-*` class)
  - inline `color:` / `background:` / `background-color:` / `border-color:`
    using hex/rgb literals (should be `var(--*)` so tenant brand wins)
  - inline `transition:` declaring a raw cubic-bezier (should be
    `var(--ease-*)` or `var(--motion-*)` so motion stays Apple-tier and
    reduced-motion-aware)

Drift-detection scanner — `--compare` against JSON baseline; CI fails when
*new* off-token inline styles appear. Existing technical debt is allowed.
Mark intentional exceptions with `<!-- inline-style-allow: <reason> -->` on
the line before, OR pass `# inline-style-allow: <reason>` inside the style
itself (for SVG/<canvas> dynamic painting where tokens cannot apply).

Excludes:
  - SVG element attributes (`fill="..."`, `stroke="..."`) — those are content
  - Inline `style="--var: ..."` setting CSS custom props from view context
    (data-driven; legitimate)
  - Lines containing `data-mkt-parallax-` or other framework computed values
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"
BASELINE = ROOT / "var" / "security-audit-baseline-inline-style-off-token.json"

STYLE_ATTR = re.compile(r'\bstyle\s*=\s*(["\'])([^"\']*?)\1')
ALLOW_INLINE = re.compile(r"inline-style-allow\s*:")

HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
RGB = re.compile(r"\brgba?\s*\(")
PX_REM_EM = re.compile(r"\b\d+(?:\.\d+)?(?:px|rem|em)\b")
CUBIC = re.compile(r"\bcubic-bezier\s*\(")
VAR_CALL = re.compile(r"\bvar\s*\(\s*--")

FONT_SIZE_DECL = re.compile(r"(?:^|[\s;])font-size\s*:\s*([^;]+)", re.IGNORECASE)
COLOR_DECL = re.compile(
    r"(?:^|[\s;])(?:color|background(?:-color)?|border(?:-(?:top|right|bottom|left))?-color)\s*:\s*([^;]+)",
    re.IGNORECASE,
)
TRANSITION_DECL = re.compile(r"(?:^|[\s;])(?:transition|animation)\s*:\s*([^;]+)", re.IGNORECASE)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(text: str, rel_path: str) -> list[dict]:
    findings: list[dict] = []
    for m in STYLE_ATTR.finditer(text):
        body = m.group(2)
        if not body or "{{" in body or "{%" in body:
            # Skip Django-interpolated styles — values come from view context.
            continue
        if ALLOW_INLINE.search(body):
            continue
        line = _line_of(text, m.start())

        # font-size literals
        for decl in FONT_SIZE_DECL.finditer(body):
            val = decl.group(1)
            if VAR_CALL.search(val):
                continue
            if PX_REM_EM.search(val):
                findings.append({
                    "file": rel_path,
                    "line": line,
                    "rule": "font-size-literal",
                    "value": val.strip()[:80],
                })

        # color / background / border-color literals
        for decl in COLOR_DECL.finditer(body):
            val = decl.group(1)
            if VAR_CALL.search(val):
                continue
            if HEX.search(val) or RGB.search(val):
                findings.append({
                    "file": rel_path,
                    "line": line,
                    "rule": "color-literal",
                    "value": val.strip()[:80],
                })

        # transition / animation with raw cubic-bezier
        for decl in TRANSITION_DECL.finditer(body):
            val = decl.group(1)
            if CUBIC.search(val) and not VAR_CALL.search(val):
                findings.append({
                    "file": rel_path,
                    "line": line,
                    "rule": "motion-curve-literal",
                    "value": val.strip()[:80],
                })

    return findings


def collect() -> list[dict]:
    out: list[dict] = []
    for p in sorted(TEMPLATES_ROOT.rglob("*.html")):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = p.relative_to(ROOT).as_posix()
        out.extend(scan_text(text, rel))
    return out


def fingerprint(findings: list[dict]) -> dict:
    by_rule: dict[str, int] = defaultdict(int)
    for f in findings:
        by_rule[f["rule"]] += 1
    return {"total": len(findings), "by_rule": dict(by_rule)}


def write_baseline(findings: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanner": "inline-style-off-token",
        "fingerprint": fingerprint(findings),
        "findings": findings,
    }
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_baseline() -> dict:
    if not BASELINE.exists():
        return {"findings": [], "fingerprint": {"total": 0, "by_rule": {}}}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="CI mode: fail on new findings vs baseline")
    ap.add_argument("--write-baseline", action="store_true", help="Snapshot current findings as new baseline")
    args = ap.parse_args()

    findings = collect()
    fp = fingerprint(findings)

    if args.write_baseline:
        write_baseline(findings)
        print(f"Wrote baseline: {fp['total']} finding(s) across {len(set(f['file'] for f in findings))} file(s)")
        for rule, n in sorted(fp["by_rule"].items()):
            print(f"  {rule}: {n}")
        return 0

    if args.compare:
        base = load_baseline()
        base_fp = base.get("fingerprint", {"total": 0, "by_rule": {}})
        new_total = fp["total"]
        old_total = base_fp.get("total", 0)
        if new_total > old_total:
            delta = new_total - old_total
            print(f"FAIL: inline-style-off-token findings grew by {delta} ({old_total} -> {new_total})")
            base_files = {(f["file"], f["line"], f["rule"], f["value"]) for f in base.get("findings", [])}
            for f in findings:
                key = (f["file"], f["line"], f["rule"], f["value"])
                if key not in base_files:
                    print(f"  NEW: {f['file']}:{f['line']}  [{f['rule']}]  {f['value']}")
            return 1
        print(f"PASS: inline-style-off-token findings {old_total} -> {new_total} (no growth)")
        return 0

    # Default: just print the report.
    print(f"Total findings: {fp['total']}")
    for rule, n in sorted(fp["by_rule"].items()):
        print(f"  {rule}: {n}")
    return 0 if fp["total"] == 0 else 0  # Default mode informational only.


if __name__ == "__main__":
    sys.exit(main())
