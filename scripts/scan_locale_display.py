#!/usr/bin/env python3
"""Zero-tolerance gate: hardcoded currency symbol glued to an interpolated value.

Tenant-facing money must render through the locale-aware ``|format_currency``
filter (``apps/siteconfig/templatetags/region_format.py``) / ``format_currency_tenant``
tag, or — for the platform's OWN reporting currency — the
``apps.siteconfig.currency.platform_currency_symbol()`` helper. It must NEVER be
a hardcoded currency-symbol literal glued straight onto a value: a school
billing in XAF/NGN/KES must not see the platform-default ``"$"`` on its own
invoices, statements, receipts, or emails. This is the regression that the
operator-revenue burndown (``a7f815b8f``) + tenant currency-resolution fix
(``b084a85d4``) closed by hand; this gate stops it coming back.

It flags the high-signal shapes (chosen to keep false positives at zero):

  Python  an f-string whose literal segment ENDS in a currency symbol that is
          immediately followed by an interpolation -- e.g.
              f"${amount}"   f"${total:,.2f}"   f"₦{x:.0f}"   f"{label}: ${v}"
          a glyph glued to a printf conversion that is the LEFT operand of % --
              "$%.2f" % value      "₦%d" % qty
          a glyph glued to a str.format field on the formatted literal --
              "${}".format(value)  "${:,.2f}".format(total)
  template a currency symbol glued to a Django variable, in any .html OR an
           email/SMS .txt body -- e.g.   ${{ amount }}   ₦{{ invoice.total }}

The % / .format detectors are AST-anchored to the real ``%`` operation / the
real ``.format()`` receiver, so a shell-style ``"${HOME}"`` literal, a regex, or
a docstring never false-positives. It deliberately does NOT flag ``"$" + str(x)``
concat (too ambiguous for a zero-FP static gate). JS template literals
(``${expr}``, single brace) never match the template pattern (Django needs ``{{``).

Mark intentional symbol-only sites (genuine USD-only platform contexts, fixtures,
docs) with ``# locale-display-allow: <reason>`` (Python, same line or line above)
or ``<!-- locale-display-allow: <reason> -->`` (template, same line or above).

Run:
  python scripts/scan_locale_display.py
  python scripts/scan_locale_display.py --compare
  python scripts/scan_locale_display.py --write-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-locale-display.json"

# Python source roots (mirrors the sibling money / currency gates).
PY_SCAN_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "services",
    REPO_ROOT / "config",
)

# Django template roots (project-level + every app-local templates/ tree).
HTML_SCAN_ROOTS = (
    REPO_ROOT / "templates",
    REPO_ROOT / "apps",
)

SKIP_DIR_NAMES = {
    "migrations",
    "tests",
    "node_modules",
    "__pycache__",
    ".git",
    "staticfiles",
}

# Single-character currency glyphs. Single-char (not "FCFA"/"R$"/"kr") keeps the
# glued-to-interpolation signal unambiguous and false positives at zero.
CURRENCY_SYMBOLS = "$€£₦¥₹₵₱₩฿₪₫"

ALLOW_MARKER = "locale-display-allow:"

# A currency glyph immediately before a Django variable open (optional space).
HTML_PATTERN = re.compile(r"[" + re.escape(CURRENCY_SYMBOLS) + r"]\s*\{\{")

# A currency glyph glued to a printf conversion (``"$%.2f" % x``) or to a
# ``str.format`` field (``"${}".format(x)``). Only consulted on the literal that
# is the actual left operand of ``%`` / the actual receiver of ``.format()`` (AST
# anchored), so a shell-style ``"${HOME}"`` or a regex never false-positives.
_SYM_CLASS = "[" + re.escape(CURRENCY_SYMBOLS) + "]"
PRINTF_MONEY = re.compile(_SYM_CLASS + r"%[#0\- +]*\d*(?:\.\d+)?[sdifeEgGxXr]")
FORMAT_MONEY = re.compile(_SYM_CLASS + r"\{[^{}]*\}")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _skipped(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def _has_allow_marker(lines: list[str], line_no: int) -> bool:
    for idx in (line_no - 1, line_no - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _ends_in_symbol(text: str) -> bool:
    return bool(text) and text[-1] in CURRENCY_SYMBOLS


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_python_text(rel: str, text: str) -> list[dict[str, str | int]]:
    """Flag a currency glyph hardcoded onto an interpolated/formatted value:

    * f-string whose literal segment ENDS in a glyph before an interpolation
      (``f"${amount}"``),
    * ``"$%.2f" % value`` printf formatting (glyph glued to the conversion),
    * ``"${}".format(value)`` (glyph glued to the format field).
    """
    findings: list[dict[str, str | int]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return findings
    lines = text.splitlines()
    seen: set[int] = set()

    def record(line_no: int) -> None:
        if line_no in seen or _has_allow_marker(lines, line_no):
            return
        seen.add(line_no)
        snippet = (
            lines[line_no - 1].strip()[:160] if 0 <= line_no - 1 < len(lines) else ""
        )
        findings.append({"path": rel, "line": line_no, "snippet": snippet})

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            values = node.values
            for i, part in enumerate(values[:-1]):
                txt = _const_str(part)
                if (
                    txt is not None
                    and _ends_in_symbol(txt)
                    and isinstance(values[i + 1], ast.FormattedValue)
                ):
                    record(getattr(node, "lineno", 1))
                    break  # one finding per f-string
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            txt = _const_str(node.left)
            if txt is not None and PRINTF_MONEY.search(txt):
                record(getattr(node, "lineno", 1))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "format":
                txt = _const_str(func.value)
                if txt is not None and FORMAT_MONEY.search(txt):
                    record(getattr(node, "lineno", 1))

    findings.sort(key=lambda item: int(item["line"]))
    return findings


def _scan_html_text(rel: str, text: str) -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    lines = text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        if HTML_PATTERN.search(line) and not _has_allow_marker(lines, line_no):
            findings.append(
                {"path": rel, "line": line_no, "snippet": line.strip()[:160]}
            )
    return findings


def scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    seen_py: set[Path] = set()
    for root in PY_SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if _skipped(path) or path in seen_py:
                continue
            seen_py.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            findings.extend(_scan_python_text(_rel(path), text))

    # Django templates: every .html, plus email/SMS .txt bodies (scoped to a
    # templates/ path so requirements.txt / fixtures / data files never match).
    seen_tpl: set[Path] = set()
    for root in HTML_SCAN_ROOTS:
        if not root.is_dir():
            continue
        for pattern in ("*.html", "*.txt"):
            for path in root.rglob(pattern):
                if _skipped(path) or path in seen_tpl:
                    continue
                rel = _rel(path)
                if pattern == "*.txt" and "templates/" not in rel:
                    continue
                seen_tpl.add(path)
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                findings.extend(_scan_html_text(rel, text))

    findings.sort(key=lambda item: (str(item["path"]), int(item["line"])))
    return findings


def _load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        return {"finding_count": 0, "findings": [], "generated_at": None}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare", action="store_true", help="Fail when findings != baseline"
    )
    parser.add_argument(
        "--write-baseline", action="store_true", help="Rewrite baseline JSON"
    )
    args = parser.parse_args(argv)

    findings = scan()
    count = len(findings)

    if args.write_baseline:
        payload = {
            "finding_count": count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings": findings,
        }
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"Wrote baseline: {count} finding(s) -> "
            f"{BASELINE_PATH.relative_to(REPO_ROOT)}"
        )
        return 0

    if args.compare:
        baseline = _load_baseline()
        expected = int(baseline.get("finding_count", 0))
        if count != expected:
            print(
                f"LOCALE_DISPLAY_FAIL: {count} finding(s), baseline {expected}",
                file=sys.stderr,
            )
            for item in findings[:20]:
                print(
                    f"  {item['path']}:{item['line']}  {item['snippet']}",
                    file=sys.stderr,
                )
            if count > 20:
                print(f"  … and {count - 20} more", file=sys.stderr)
            return 1
        print(f"LOCALE_DISPLAY_PASS ({count} finding(s), baseline {expected})")
        return 0

    print(f"locale-display: {count} finding(s)")
    for item in findings:
        print(f"  {item['path']}:{item['line']}  {item['snippet']}")
    return 0 if count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
