#!/usr/bin/env python3
"""Fail CI when templates use eager filter args that are bare context vars.

Django resolves every filter *argument* eagerly — even when the left-hand value
is already set. A missing context variable raises VariableDoesNotExist and 500s
the page. Proven on Django 5.2:

    {{ a|default:b }}          # raises if b missing, even when a is set
    {% for x in items|slice:lim %}  # raises if lim missing
    {{ a|add:b }}              # raises if b missing
    {% include "x" with y=a|default:b %}  # same

Covered filters: ``default``, ``default_if_none``, ``slice``, ``add``.

Safe arguments: string/number literals, None/True/False, _("…") / gettext,
and ``forloop.*`` (only valid inside ``{% for %}``).

Loop / ``{% with %}``-bound names that are proven in-scope may carry:

    {# default-fallback-allow: <reason> #}

on the same line or the line above.

Introduced after production 500s on /super/schools/ and /configuration/
(``Failed lookup for key [ops_surface]``). Expanded 2026-07-22 to scan the
entire template tree and additional eager filter families.

Usage:
  python scripts/scan_include_with_default_context_var.py
  python scripts/scan_include_with_default_context_var.py --strict
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Match |default: / |default_if_none: / |slice: / |add: followed by a bare
# context identifier (not a safe literal / builtin / gettext call).
_FILTER_ARG_RE = re.compile(
    r"\|\s*(?:default(?:_if_none)?|slice|add)\s*:\s*"
    r"(?!_?\(|[\"']|None\b|True\b|False\b|\d)"
    r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
)

_COMMENT_RE = re.compile(
    r"\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|<!--.*?-->",
    re.DOTALL,
)

# Same-line or previous-line allow marker (kept in source comments that
# _COMMENT_RE strips — so we scan the raw text for markers).
_ALLOW_RE = re.compile(
    r"\{#\s*default-fallback-allow\s*:\s*[^#]+?#\}|"
    r"<!--\s*default-fallback-allow\s*:\s*[^-]+?-->",
    re.IGNORECASE,
)

_SAFE_ROOTS = frozenset({"True", "False", "None", "forloop"})


def _template_roots() -> list[Path]:
    roots = [ROOT / "templates"]
    apps = ROOT / "apps"
    if apps.is_dir():
        roots.extend(sorted(apps.glob("*/templates")))
    return [r for r in roots if r.is_dir()]


def _line_allowed(raw_lines: list[str], line_idx: int) -> bool:
    """True when this line or the previous non-empty line carries an allow marker."""
    for idx in (line_idx, line_idx - 1):
        if 0 <= idx < len(raw_lines) and _ALLOW_RE.search(raw_lines[idx]):
            return True
    return False


def _scan_text(path: Path, text: str) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    raw_lines = text.splitlines()
    # Strip comments for match positions, but keep newlines so line numbers hold.
    cleaned = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for match in _FILTER_ARG_RE.finditer(cleaned):
        var = match.group(1)
        root = var.split(".", 1)[0]
        if root in _SAFE_ROOTS:
            continue
        # Dotted paths (invoice.id, request.user.role) only fail when the root
        # object is missing — same class as any bare {{ invoice.id }}. The
        # production 500 class is a missing TOP-LEVEL name used as a filter arg
        # (ops_surface, PREVIEW_NOTE, backend_max_items_slice).
        if "." in var:
            continue
        line_no = cleaned.count("\n", 0, match.start()) + 1
        if _line_allowed(raw_lines, line_no - 1):
            continue
        start = max(0, match.start() - 48)
        end = min(len(cleaned), match.end() + 48)
        snippet = " ".join(cleaned[start:end].split())[:160]
        findings.append((line_no, var, snippet))
    return findings


def scan() -> list[dict]:
    out: list[dict] = []
    for base in _template_roots():
        for path in sorted(base.rglob("*.html")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, var, snippet in _scan_text(path, text):
                out.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
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
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        label = "eager-filter-arg-context-var"
        if not findings:
            print(f"{label}: 0 finding(s)")
        else:
            print(f"{label}: {len(findings)} finding(s)")
            for f in findings:
                print(f"  {f['path']}:{f['line']}  |…:{f['var']}  :: {f['snippet']}")
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
