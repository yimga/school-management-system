#!/usr/bin/env python
"""An internal identifier must never be shown to a human as if it were words.

A support engineer opened Tenant 360 and read this, verbatim:

    Exact next confirmations: funding_type, learner_scale, connectivity,
    operating_model

The banner promises exactness and then hands over four dict keys. It is not a
cosmetic complaint: the same page rendered "Inputcompleteness" two lines above,
and the lifecycle strip on every tenant page rendered "dailyoperations". Three
files, one mistake.

RULE A — ``|cut`` on a word separator
-------------------------------------
Django's ``cut`` filter DELETES the character. It has no notion of a separator,
so ``daily_operations|cut:"_"`` is ``dailyoperations``: less readable than the
slug it replaced, and now beyond rescue by CSS ``text-transform: capitalize``,
which capitalises whitespace-delimited words and no longer has any whitespace to
work with. There is no input for which cutting ``_`` or ``-`` out of a token
produces the right answer, which is what makes this a zero-baseline rule rather
than a style preference.

Both fixes are one edit: ``|humanize_token`` for an open set whose token
explains itself (``input_completeness`` -> "Input completeness"), or a curated
registry for a closed vocabulary, where casing was never the problem —
"Conception" means no more to a head teacher than "conception" does.

RULE B — a closed vocabulary with an unlabelled member
------------------------------------------------------
Rule A only sees the mistake once someone has already made it in a template.
The deeper version is a state machine that ships a 15th state and no words for
it: the humanizer catches the fall, the chip reads "Purge scheduled" instead of
something a school can act on, and nobody notices because nothing is broken.

So each registered vocabulary declares its members and its labels side by side,
and this rule reads both out of the source with ``ast`` and reports any member
with no label — and any label for a member that no longer exists, which is how a
registry rots quietly after a rename. Deps-free, no Django import: the check
must run in the boundary job, and a gate that needs the app registry to tell you
a label is missing is a gate that stops running the day the app registry breaks.

Deliberately NOT in scope
-------------------------
* ``{{ key }}`` inside a ``<code>`` block on an operator inspector. Showing the
  real key to someone debugging is correct, and flagging 70 of those would bury
  the six real defects — the way a gate gets switched off.
* Rendering a raw token in a ``data-`` attribute. It is a DOM hook, not copy.
* An unparseable Python file. ``verify_python_files_parse`` owns that, and
  saying it twice buries the report that explains how to fix it.

Flags: ``--json``, ``--strict``, ``--update-baseline``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "var" / "security-audit-baseline-raw-token-in-ui.json"

# ---------------------------------------------------------------------------
# RULE A
# ---------------------------------------------------------------------------

#: ``|cut:"_"`` / ``| cut :'-'`` — any spacing, either quote, either separator.
CUT_SEPARATOR = re.compile(r"\|\s*cut\s*:\s*(?P<q>[\"'])(?P<sep>[_-])(?P=q)")

#: Reviewed exception, written where a reviewer reads it rather than in a
#: baseline file where it becomes invisible.
ALLOW_MARKER = re.compile(r"raw-token-allow:\s*[A-Za-z0-9]")


def _template_dirs() -> list[Path]:
    dirs = [ROOT / "templates"]
    apps = ROOT / "apps"
    if apps.is_dir():
        for app in sorted(apps.iterdir()):
            candidate = app / "templates"
            if candidate.is_dir():
                dirs.append(candidate)
    return [d for d in dirs if d.is_dir()]


def _rel(path: Path) -> str:
    """Repo-relative POSIX path, tolerant of paths outside the tree (tests)."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_template(path: Path) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[dict[str, object]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        match = CUT_SEPARATOR.search(line)
        if not match:
            continue
        previous = lines[index - 2] if index >= 2 else ""
        if ALLOW_MARKER.search(line) or ALLOW_MARKER.search(previous):
            continue
        findings.append(
            {
                "kind": "cut_separator",
                "path": _rel(path),
                "line": index,
                "separator": match.group("sep"),
                "detail": (
                    f"`cut:\"{match.group('sep')}\"` deletes the separator and "
                    "jams the words together; use `|humanize_token` or a "
                    "curated label registry."
                ),
            }
        )
    return findings


# ---------------------------------------------------------------------------
# RULE B
# ---------------------------------------------------------------------------

#: module path -> (members constant, labels constant). The members constant may
#: be a tuple/list/frozenset of string literals OR of module-level names bound
#: to string literals; the labels constant is a dict keyed the same way.
VOCABULARIES: dict[str, tuple[str, str]] = {
    "apps/platform_runtime/tenant_operational_lifecycle.py": (
        "ALL_OPERATIONAL_STATES",
        "OPERATIONAL_STATE_LABELS",
    ),
    "apps/schools/onboarding_recommendations.py": (
        "CRITICAL_EVIDENCE_KEYS",
        "CRITICAL_EVIDENCE_LABELS",
    ),
}


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bindings, for resolving tuple members."""
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                out[target.id] = value.value
    return out


def _resolve(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _named_assignment(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return node.value
    return None


def scan_vocabulary(
    path: Path, members_name: str, labels_name: str
) -> list[dict[str, object]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        # verify_python_files_parse owns unparseable files; see module docstring.
        return []
    constants = _string_constants(tree)
    members_node = _named_assignment(tree, members_name)
    labels_node = _named_assignment(tree, labels_name)
    rel = _rel(path)
    findings: list[dict[str, object]] = []
    if members_node is None or labels_node is None:
        missing = members_name if members_node is None else labels_name
        findings.append(
            {
                "kind": "vocabulary_constant_missing",
                "path": rel,
                "line": 0,
                "member": missing,
                "detail": (
                    f"`{missing}` is registered in scan_raw_token_in_ui."
                    "VOCABULARIES but is not defined in this module — a rename "
                    "left the gate pointing at nothing."
                ),
            }
        )
        return findings

    members: list[str] = []
    if isinstance(members_node, (ast.Tuple, ast.List, ast.Set)):
        for element in members_node.elts:
            resolved = _resolve(element, constants)
            if resolved is not None:
                members.append(resolved)
    labels: set[str] = set()
    if isinstance(labels_node, ast.Dict):
        for key in labels_node.keys:
            resolved = _resolve(key, constants)
            if resolved is not None:
                labels.add(resolved)

    for member in members:
        if member not in labels:
            findings.append(
                {
                    "kind": "unlabelled_vocabulary_member",
                    "path": rel,
                    "line": getattr(members_node, "lineno", 0),
                    "member": member,
                    "detail": (
                        f"`{member}` is in {members_name} with no entry in "
                        f"{labels_name}; it would reach a person as a slug."
                    ),
                }
            )
    for orphan in sorted(labels - set(members)):
        findings.append(
            {
                "kind": "orphan_vocabulary_label",
                "path": rel,
                "line": getattr(labels_node, "lineno", 0),
                "member": orphan,
                "detail": (
                    f"`{orphan}` has a label in {labels_name} but is not in "
                    f"{members_name} — a stale label outliving its member."
                ),
            }
        )
    return findings


# ---------------------------------------------------------------------------


def scan_repository() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for directory in _template_dirs():
        for path in sorted(directory.rglob("*.html")):
            findings.extend(scan_template(path))
    for rel, (members_name, labels_name) in sorted(VOCABULARIES.items()):
        path = ROOT / rel
        if not path.is_file():
            findings.append(
                {
                    "kind": "vocabulary_module_missing",
                    "path": rel,
                    "line": 0,
                    "member": rel,
                    "detail": (
                        "Registered in VOCABULARIES but absent from the tree; "
                        "update the registry or restore the module."
                    ),
                }
            )
            continue
        findings.extend(scan_vocabulary(path, members_name, labels_name))
    findings.sort(key=lambda f: (str(f["path"]), int(f["line"]), str(f["kind"])))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline (only when a violation is genuinely removed)",
    )
    args = parser.parse_args(argv)

    findings = scan_repository()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"finding_count": len(findings), "findings": findings}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        for finding in findings:
            print(f"{finding['path']}:{finding['line']}: {finding['kind']} — {finding['detail']}")
        print(f"\nraw-token-in-ui: {len(findings)} finding(s)")

    if findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
