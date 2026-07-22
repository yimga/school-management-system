#!/usr/bin/env python3
"""Fail CI when {% include … with %} uses |default:<context_var>.

Django resolves every filter argument in an include ``with=`` clause eagerly.
A missing context variable raises VariableDoesNotExist and 500s the page —
even when the left-hand value is already set. Literal defaults
(``|default:""``, ``|default:None``, ``|default:False``, ``|default:_("…")``)
are safe.

Introduced after production 500s on /super/schools/ and /configuration/
(``Failed lookup for key [ops_surface]`` in rmc_operational_center_frame.html).

Usage:
  python scripts/scan_include_with_default_context_var.py
  python scripts/scan_include_with_default_context_var.py --strict
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# Match |default:identifier that is NOT a safe literal / builtin / gettext.
# Safe: "", '', None, True, False, numbers, _("…"), _('…')
_DEFAULT_VAR_RE = re.compile(
    r"\|\s*default\s*:\s*(?!_?\(|[\"']|None\b|True\b|False\b|\d)"
    r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
)

# Strip Django/HTML comments so retired patterns don't false-positive.
_COMMENT_RE = re.compile(
    r"\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|<!--.*?-->",
    re.DOTALL,
)

# Multi-line {% include … %} blocks (with= may wrap).
_INCLUDE_RE = re.compile(r"\{%\s*include\b.*?%\}", re.DOTALL)


def _scan_text(path: Path, text: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    cleaned = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for match in _INCLUDE_RE.finditer(cleaned):
        block = match.group(0)
        if " with " not in block and "\nwith " not in block:
            # still allow `with` immediately after newline inside tag
            if not re.search(r"\bwith\b", block):
                continue
        for var_match in _DEFAULT_VAR_RE.finditer(block):
            var = var_match.group(1)
            # Dotted paths (invoice.id, thread.description) only fail when the
            # root object is missing — same failure mode as any bare include
            # kwarg. The production 500 class is a missing TOP-LEVEL name used
            # as a default arg (ops_surface, masthead_eyebrow).
            if "." in var:
                continue
            line_no = cleaned.count("\n", 0, match.start() + var_match.start()) + 1
            snippet = " ".join(block.split())[:160]
            findings.append((line_no, var, snippet))
    return findings


def scan() -> list[dict]:
    out: list[dict] = []
    if not TEMPLATES.is_dir():
        return out
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, var, snippet in _scan_text(path, text):
            out.append(
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": line_no,
                    "var": var,
                    "snippet": snippet,
                }
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = scan()
    if args.json:
        import json

        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        if not findings:
            print("include-with-default-context-var: 0 finding(s)")
        else:
            print(f"include-with-default-context-var: {len(findings)} finding(s)")
            for f in findings:
                print(f"  {f['path']}:{f['line']}  |default:{f['var']}  :: {f['snippet']}")
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
