#!/usr/bin/env python3
"""Verify custom template tags/filters are loaded before use.

Django does NOT inherit ``{% load %}`` through ``{% extends %}`` — each template
must declare every library it uses. Missing loads surface at render time as
``TemplateSyntaxError: Invalid block tag: 'trans_term'`` (500 on first hit).

This gate AST-scans ``apps/*/templatetags/*.py`` to build a registry of custom
tag/filter names → required ``{% load lib %}`` module, then walks project
templates for usages without a matching load in the same file.

Built-in Django tags/filters are excluded (only registered custom names are
checked). Templates may opt out with ``# template-tag-load-allow: <reason>``
on the usage line or the line above.

Companion: ``audit_template_render_safety.py`` (structural leaks); this gate
closes the missing-``{% load %}`` class that compile-time tag resolution catches.
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-template-tag-loads.json"

ALLOW_MARKER = "template-tag-load-allow:"

TEMPLATE_ROOTS = [REPO_ROOT / "templates"]
for app_tpl in (REPO_ROOT / "apps").glob("*/templates"):
    TEMPLATE_ROOTS.append(app_tpl)

EXCLUDE_PARTS = {"node_modules", "staticfiles", ".git", "venv", ".venv"}

# Django built-ins that appear in templates but need no {% load %}.
_DJANGO_BUILTIN_TAGS = frozenset(
    {
        "autoescape", "block", "comment", "csrf_token", "debug", "extends",
        "filter", "firstof", "for", "if", "ifchanged", "ifequal", "ifnotequal",
        "include", "load", "localize", "lorem", "now", "regroup", "resetcycle",
        "spaceless", "static", "templatetag", "url", "verbatim", "widthratio",
        "with", "empty", "elif", "else", "endif", "endfor", "endblock",
        "endcomment", "endfilter", "endautoescape", "endlocalize", "endspaceless",
        "endverbatim", "endwith", "trans", "blocktrans", "blocktranslate",
        "endblocktrans", "endblocktranslate", "plural", "language", "endlanguage",
        "cache", "endcache", "timezone", "endtimezone",
    }
)

_TAG_USE_RE = re.compile(r"{%\s*-?\s*([a-zA-Z_][a-zA-Z0-9_-]*)")
_FILTER_USE_RE = re.compile(r"\|\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*(?:\:|%|\})")
_LOAD_RE = re.compile(r"{%\s*load\s+([^%]+?)%}")
_COMMENT_BLOCK_RE = re.compile(r"{%\s*comment\s+.*?%\s*.*?{%\s*endcomment\s+%}", re.DOTALL)
_HASH_COMMENT_RE = re.compile(r"{#.*?#}", re.DOTALL)


def _strip_comments(text: str) -> str:
    text = _COMMENT_BLOCK_RE.sub("", text)
    text = _HASH_COMMENT_RE.sub("", text)
    return text


def _iter_templates() -> list[Path]:
    out: list[Path] = []
    for root in TEMPLATE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.html"):
            if any(part in EXCLUDE_PARTS for part in path.parts):
                continue
            out.append(path)
    return sorted(out)


def _registered_names(module_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return (tag_name -> load_module, filter_name -> load_module)."""
    tags: dict[str, str] = {}
    filters: dict[str, str] = {}
    load_name = module_path.stem
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return tags, filters

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "register"
            ):
                continue
            method = func.attr
            explicit_name = None
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    explicit_name = str(kw.value.value)
            reg_name = explicit_name or node.name
            if method in ("simple_tag", "tag", "inclusion_tag"):
                tags[reg_name] = load_name
            elif method == "filter":
                filters[reg_name] = load_name
    return tags, filters


def _build_registry() -> tuple[dict[str, str], dict[str, str]]:
    tag_to_lib: dict[str, str] = {}
    filter_to_lib: dict[str, str] = {}
    for module in sorted((REPO_ROOT / "apps").glob("*/templatetags/*.py")):
        if module.name == "__init__.py":
            continue
        tags, filters = _registered_names(module)
        for name, lib in tags.items():
            tag_to_lib.setdefault(name, lib)
        for name, lib in filters.items():
            filter_to_lib.setdefault(name, lib)
    return tag_to_lib, filter_to_lib


def _has_allow_marker(lines: list[str], line_no: int) -> bool:
    idx = line_no - 1
    if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
        return True
    if idx > 0 and ALLOW_MARKER in lines[idx - 1]:
        return True
    return False


def _parse_loads(text: str) -> set[str]:
    loaded: set[str] = set()
    for m in _LOAD_RE.finditer(text):
        chunk = m.group(1)
        for token in chunk.split():
            token = token.strip()
            if token and not token.startswith("from"):
                loaded.add(token)
    return loaded


def scan(
    tag_to_lib: dict[str, str], filter_to_lib: dict[str, str]
) -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_templates():
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text = _strip_comments(raw)
        lines = raw.splitlines()
        loaded = _parse_loads(text)
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")

        for m in _TAG_USE_RE.finditer(text):
            name = m.group(1)
            if name in _DJANGO_BUILTIN_TAGS:
                continue
            lib = tag_to_lib.get(name)
            if not lib or lib in loaded:
                continue
            line_no = raw.count("\n", 0, m.start()) + 1
            if _has_allow_marker(lines, line_no):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": line_no,
                    "kind": "tag",
                    "name": name,
                    "required_load": lib,
                }
            )

        for m in _FILTER_USE_RE.finditer(text):
            name = m.group(1)
            lib = filter_to_lib.get(name)
            if not lib or lib in loaded:
                continue
            line_no = raw.count("\n", 0, m.start()) + 1
            if _has_allow_marker(lines, line_no):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": line_no,
                    "kind": "filter",
                    "name": name,
                    "required_load": lib,
                }
            )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Compare to baseline JSON")
    parser.add_argument("--write-baseline", action="store_true", help="Write baseline JSON")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args(argv)

    tag_to_lib, filter_to_lib = _build_registry()
    findings = scan(tag_to_lib, filter_to_lib)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "findings": findings,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Custom tag/filter registry: {len(tag_to_lib)} tags, {len(filter_to_lib)} filters")
        print(f"Findings: {len(findings)}")
        for f in findings[:50]:
            print(
                f"  {f['path']}:{f['line']} — {f['kind']} `{f['name']}` "
                f"needs {{% load {f['required_load']} %}}"
            )
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")

    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline -> {BASELINE_PATH}")

    if args.compare and BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        expected = int(baseline.get("finding_count", 0))
        if len(findings) != expected:
            print(
                f"DRIFT: found {len(findings)} findings, baseline expects {expected}",
                file=sys.stderr,
            )
            return 1
    elif args.compare and len(findings) > 0:
        return 1

    return 0 if len(findings) == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
