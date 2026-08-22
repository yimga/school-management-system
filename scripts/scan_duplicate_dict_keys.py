#!/usr/bin/env python3
"""Detect dict literals that declare the same constant key twice.

Python keeps the LAST value for a repeated key and silently discards the
earlier one. There is no warning, no error, and no runtime symptom at the
point of the mistake -- the entry simply is not there. When the two values
differ, that is silent data loss; when they match, it is dead source that
will drift apart the next time one copy is edited.

Caught by the first run of this scanner (2026-08-22), over 8717 tracked
Python files:

  * apps/platform_runtime/workflow_registry.py declared "parent-portal-pay-all"
    twice. The surviving copy was a paste of the neighbouring
    "parent-portal-pay-invoice" entry with only key/title/purpose/route
    changed, so the pay-all workflow resolved with NO steps (its "How it
    works" panel, built from ``workflow.steps`` in workflow_guidance.py, was
    empty), pointed parents at the single-invoice help article, and declared
    the single-invoice audit event.

  * scripts/verify_ux_completion.py declared
    "templates/marketplace/app_catalog.html" twice. The shadowed entry's two
    markers were therefore never checked, and one of them had in fact
    regressed out of the template -- a gate hole that reported PASS.

  * Four further exact-repeat keys: dead source, no behaviour change.

ZERO BASELINE. There is deliberately no baseline file: nothing to rot, and no
bare invocation that can rewrite the evidence it was meant to report. Any
finding fails.

Semantics note: keys are compared with Python's own equality, so ``1``,
``1.0`` and ``True`` collide exactly as they do in a real dict literal.

Enumeration note: the corpus is ``git ls-files`` -- tracked content, i.e. what
actually deploys. A brand-new *untracked* file is invisible until it is added
(``git add -N`` is enough to make it visible here).
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ast.Constant covers str / bytes / int / float / complex / bool / None.
# Tuple keys are hashable too, but only when every element is itself constant.


def _key_value(node: ast.expr):
    """Return (ok, value) for a constant-valued key node."""
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.Tuple):
        parts = []
        for element in node.elts:
            ok, value = _key_value(element)
            if not ok:
                return False, None
            parts.append(value)
        return True, tuple(parts)
    return False, None


def _display_path(path: Path) -> str:
    """Repo-relative when possible; an explicit path outside the repo is legal."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / name for name in out.split("\0") if name]


def scan_file(path: Path) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Syntax is another gate's job; a file we cannot parse is not a finding here.
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict = defaultdict(list)
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:  # ``**spread`` -- no literal key
                continue
            ok, value = _key_value(key_node)
            if not ok:
                continue
            try:
                seen[value].append((key_node, value_node))
            except TypeError:  # unhashable, cannot be a real dict key either
                continue
        for value, occurrences in seen.items():
            if len(occurrences) < 2:
                continue
            segments = [
                " ".join((ast.get_source_segment(source, v) or "").split())
                for _, v in occurrences
            ]
            findings.append(
                {
                    "path": _display_path(path),
                    "dict_line": node.lineno,
                    "key": value,
                    "lines": [k.lineno for k, _ in occurrences],
                    "identical": len(set(segments)) == 1,
                    "kept_line": occurrences[-1][0].lineno,
                    "segments": segments,
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional explicit files to scan (default: every tracked *.py).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Accepted for parity with the sibling zero-baseline scanners, which are "
            "informational unless asked to fail. This one has no baseline to compare "
            "against and no baseline file it could rewrite, so a bare run ALREADY "
            "exits 1 on any finding and the flag changes nothing. It exists so the CI "
            "line reads like its neighbours -- and so that dropping it can never "
            "silently turn the gate off."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    args = parser.parse_args()

    files = [Path(p).resolve() for p in args.paths] if args.paths else tracked_python_files()

    findings: list[dict] = []
    for path in files:
        findings.extend(scan_file(path))

    if args.json:
        # default=repr: a bytes key is a legal dict key and is not JSON-serialisable.
        print(
            json.dumps(
                {"finding_count": len(findings), "findings": findings},
                indent=2,
                default=repr,
            )
        )
        return 1 if findings else 0

    if not findings:
        print(f"PASS: no duplicate dict keys in {len(files)} Python file(s).")
        return 0

    shadowing = [f for f in findings if not f["identical"]]
    repeats = [f for f in findings if f["identical"]]

    print(f"FAIL: {len(findings)} dict literal(s) declare a key twice.")
    print(f"  {len(shadowing)} with DIFFERENT values (silent data loss)")
    print(f"  {len(repeats)} exact repeats (dead source)")
    print()

    for finding in sorted(findings, key=lambda f: (not f["identical"], f["path"], f["dict_line"])):
        severity = "REPEAT " if finding["identical"] else "SHADOW "
        lines = ", ".join(str(n) for n in finding["lines"])
        print(f"{severity} {finding['path']}  key={finding['key']!r}")
        print(f"          declared at line(s) {lines}; Python keeps line {finding['kept_line']}")
        if not finding["identical"]:
            for line, segment in zip(finding["lines"], finding["segments"]):
                marker = "KEPT   " if line == finding["kept_line"] else "DROPPED"
                print(f"          {marker} L{line}: {segment[:110]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
