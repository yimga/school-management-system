#!/usr/bin/env python3
"""verify_template_block_target_integrity.py — a child {% block %} that overrides a
CONTENT/body block whose name no ancestor in its {% extends %} chain defines has its
whole body SILENTLY DROPPED by Django: the page returns HTTP 200 and renders the shell
chrome (header, sidebar, breadcrumbs) with an EMPTY main region.

This is the "empty space per URL" class this repo hit with the MAT Group Hub trio
(``schools/mat_group_hub/{dashboard,detail,edit}.html``): each extended
``control_plane_base.html`` but wrapped its body in ``{% block control_plane_body %}``.
The base's content block is named ``cp_content`` — ``control_plane_body`` is defined
NOWHERE — so Django discarded the body and three distinct ``/super/mat-group-hub/*``
URLs each rendered the same blank control-plane shell. It was broken since introduction;
no runtime error, no existing gate caught it (``verify_cross_host_template_reverse``
only inspects ``{% url %}`` reverses, the reference-integrity gates only resolve template
PATHS, not block NAMES).

Pure stdlib (no Django) so it can run in the fast pre-push boundary set. Zero-FP by
construction:
  * Only TOP-LEVEL block overrides are considered (a block nested inside another block
    in the same file is not an override of the base).
  * Only CONTENT/body block names are judged — a curated set plus the ``_body`` /
    ``_content`` suffixes. Chrome/asset/title blocks (``title``, ``page_title``,
    ``extrastyle``, ``extra_js``, ``breadcrumbs`` …) are IGNORED: orphaning them is
    cosmetic (a title falls back, a script doesn't load), not a blank page.
  * A template whose ancestor chain is UNRESOLVABLE — a variable ``{% extends x %}``,
    a base file that can't be found, or a self-referential Django-admin override — is
    SKIPPED (we can't prove the block is orphaned, so we never guess).
  * ``templates/admin/`` (Django-admin overrides, resolved through site-packages) is
    excluded.
  * A ``{# block-target-allow: <reason> #}`` marker on the block line (or the line
    above) opts a deliberate site out.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
MARKER = "block-target-allow"

EXTENDS_STR_RE = re.compile(r"\{%\s*extends\s+([\"'])(.+?)\1\s*%\}")
EXTENDS_VAR_RE = re.compile(r"\{%\s*extends\s+(?![\"'])")
BLOCK_RE = re.compile(r"\{%\s*block\s+([a-zA-Z0-9_]+)\s*%\}")
BLOCK_TOK_RE = re.compile(r"\{%\s*(block\s+[a-zA-Z0-9_]+|endblock(?:\s+[a-zA-Z0-9_]+)?)\s*%\}")

# Block names that carry the visible page BODY. Orphaning one of these drops the page.
CONTENT_BLOCKS = frozenset({
    "content",
    "cp_content",
    "cp_shell_page",
    "cp_shell_canvas_body",
    "cp_shell_landing_sections",
    "backend_page",
    "backend_main",
    "connector_body",
    "control_plane_body",  # the known-bad name — a plausible body block that does not exist
    "main",
    "body",
    "page_body",
    "main_content",
})


def _is_content_block(name: str) -> bool:
    if name in CONTENT_BLOCKS:
        return True
    # *_body / *_content are body sinks; *_title is explicitly not.
    return name.endswith(("_body", "_content")) and not name.endswith("_title")


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _discover_roots(root: str) -> list[str]:
    roots = []
    skip = {".venv", "node_modules", ".git", "site-packages", "staticfiles", "collected_static"}
    for dirpath, dirnames, _ in os.walk(root):
        if skip & set(dirpath.replace("\\", "/").split("/")):
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) == "templates":
            roots.append(dirpath)
    return roots


def _build_index(roots: list[str]) -> tuple[dict[str, str], list[str]]:
    name_index: dict[str, str] = {}
    all_templates: list[str] = []
    for r in roots:
        for dirpath, _, filenames in os.walk(r):
            for fn in filenames:
                if not fn.endswith((".html", ".htm", ".txt", ".xml")):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, r).replace("\\", "/")
                name_index.setdefault(rel, full)  # first root wins (DIRS/app order)
                all_templates.append(full)
    return name_index, all_templates


def _top_level_blocks(src: str) -> set[str]:
    depth = 0
    names: set[str] = set()
    for m in BLOCK_TOK_RE.finditer(src):
        tok = m.group(1)
        if tok.startswith("block"):
            if depth == 0:
                names.add(tok.split()[1])
            depth += 1
        else:
            depth -= 1
    return names


def _ancestor_blocks(path: str, index: dict[str, str], seen: set[str] | None = None):
    """Return (defined_block_names_above, unresolvable). ``unresolvable`` is True when a
    base uses a variable {% extends %}, a base file is missing, or the chain self-cycles
    (Django-admin override) — in which case orphan-ness cannot be proven."""
    if seen is None:
        seen = set()
    src = _read(path)
    m = EXTENDS_STR_RE.search(src)
    if not m:
        return set(), bool(EXTENDS_VAR_RE.search(src))
    base_name = m.group(2)
    base_path = index.get(base_name)
    if base_path is None:
        return set(), True  # base not found -> can't resolve
    if os.path.abspath(base_path) == os.path.abspath(path) or base_path in seen:
        return set(), True  # self-cycle (admin override) -> unresolvable
    seen.add(base_path)
    defined = set(BLOCK_RE.findall(_read(base_path)))
    up, unresolvable = _ancestor_blocks(base_path, index, seen)
    return defined | up, unresolvable


def _has_marker(src: str, block_name: str) -> bool:
    """True if a block-target-allow marker sits on the block's line or the line above."""
    lines = src.splitlines()
    needle = re.compile(r"\{%\s*block\s+" + re.escape(block_name) + r"\s*%\}")
    for i, line in enumerate(lines):
        if needle.search(line):
            window = lines[max(0, i - 1): i + 1]
            if any(MARKER in w for w in window):
                return True
    return False


def scan(root: str) -> list[dict]:
    roots = _discover_roots(root)
    index, all_templates = _build_index(roots)
    findings: list[dict] = []
    for path in all_templates:
        rel = os.path.relpath(path, root).replace("\\", "/")
        if rel.startswith("templates/admin/") or "/admin/" in rel:
            continue  # Django-admin overrides — inheritance resolved via site-packages
        src = _read(path)
        if not EXTENDS_STR_RE.search(src):
            continue
        top = _top_level_blocks(src)
        orphan_content = {b for b in top if _is_content_block(b)}
        if not orphan_content:
            continue
        ancestors, unresolvable = _ancestor_blocks(path, index)
        if unresolvable:
            continue
        for bn in sorted(orphan_content):
            if bn in ancestors:
                continue
            if _has_marker(src, bn):
                continue
            base = EXTENDS_STR_RE.search(src).group(2)
            findings.append({
                "file": rel,
                "block": bn,
                "extends": base,
                "reason": (
                    f"{{% block {bn} %}} is a content/body block that '{base}' (and its "
                    f"ancestors) does not define; Django drops this body -> blank page. "
                    f"Fill the base's real content block, or add {{# {MARKER}: <reason> #}}"
                ),
            })
    return sorted(findings, key=lambda f: (f["file"], f["block"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=REPO_ROOT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    findings = scan(args.root)
    count = len(findings)
    if args.json:
        print(json.dumps({
            "finding_count": count,
            "findings": findings,
            "rule": (
                "every top-level {% block %} overriding a content/body block name must "
                "resolve to a block DEFINED in the template's {% extends %} ancestor "
                "chain; otherwise Django silently drops the body and the page renders "
                "an empty shell. Guard deliberate cases with # block-target-allow."
            ),
        }, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}  ->  {{% block {f['block']} %}}  (extends {f['extends']})")
        print(f"\ntemplate-block-target-integrity findings: {count}")

    if args.strict and count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
