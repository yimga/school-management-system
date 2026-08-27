#!/usr/bin/env python3
"""Gate: every ratchet that runs with ``--compare`` must have a COMMITTED baseline.

WHY THIS EXISTS
---------------
A ratchet gate is a promise that a number can only fall. The promise is kept by a
baseline file in ``var/``. Delete that file and most of these scanners do not
fail -- they fall through to their "write the baseline" branch, author a new one
from whatever they happen to find right now, and exit 0. The gate then passes
forever against a reference it invented, and the regression it exists to catch is
baked into its own definition of normal.

That is not hypothetical: ``scan_rls_table_coverage.py`` had exactly this shape --
``if args.compare or args.update_baseline or not BASELINE_PATH.exists(): <write>``
-- so ``--compare`` on a tree without ``var/`` silently self-anchored and returned
0. It was fixed to refuse; this gate is the general form, so the next scanner with
that shape is caught by structure instead of by somebody noticing.

An untracked baseline is the same failure one step removed: it works on the
machine that generated it and vanishes for everybody else, including CI.

WHAT IT CHECKS
--------------
For every gate in ``pre_push_boundary_check.py`` (both ``GATES`` and
``DJANGO_GATES``) whose argv contains ``--compare``:

  1. the scanner declares a baseline path constant, and
  2. that file EXISTS, and
  3. ``git ls-files`` knows about it.

Gates whose baseline constant cannot be resolved are REPORTED, not failed -- some
comparison gates legitimately hold their reference somewhere else. The count is
printed so it stays visible rather than becoming a silent exemption.

Stdlib only, so it runs in the deps-free CI job and the fast phase of the pre-push
runner.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
RUNNER = SCRIPTS / "pre_push_boundary_check.py"

BASELINE_NAMES = {"BASELINE", "BASELINE_PATH", "BASELINE_FILE", "BASELINE_JSON"}


def _gate_argvs() -> list[tuple[str, list[str]]]:
    """(label, argv) for every gate the pre-push runner declares.

    Parsed, not imported: importing the runner would pull in whatever it imports
    and this gate must stay dependency-free.
    """
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"), filename=str(RUNNER))
    gates: list[tuple[str, list[str]]] = []
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if not names & {"GATES", "DJANGO_GATES"}:
            continue
        if not isinstance(node.value, ast.List):
            continue
        for element in node.value.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                continue
            label_node, argv_node = element.elts
            if not isinstance(label_node, ast.Constant) or not isinstance(argv_node, ast.List):
                continue
            argv = [a.value for a in argv_node.elts if isinstance(a, ast.Constant)]
            gates.append((label_node.value, argv))
    return gates


def _path_parts(node: ast.AST) -> list[str]:
    """String components of a ``REPO_ROOT / "var" / "x.json"`` expression, IN ORDER.

    ``ast.walk`` is breadth-first and gives no ordering guarantee, so collecting
    constants with it produced ``["x.json", "var"]`` and a path that could never
    exist -- the gate then reported every baseline as missing, which is exactly the
    kind of confidently-wrong zero this file exists to prevent. Recurse the BinOp
    left-to-right instead.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _path_parts(node.left) + _path_parts(node.right)
    if isinstance(node, ast.Call):
        # Path("var/x.json") and similar wrappers.
        parts: list[str] = []
        for arg in node.args:
            parts += _path_parts(arg)
        return parts
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []  # a Name such as REPO_ROOT is the anchor, contributing nothing


def _baseline_for(script_name: str) -> pathlib.Path | None:
    """Resolve the scanner's baseline path from its source.

    The shape is always a REPO_ROOT-anchored join with one or two string parts,
    e.g. ``REPO_ROOT / "var" / "security-audit-baseline-x.json"``. Pulling the
    string constants out of the assignment and joining them onto the repo root
    handles every variant in the tree without executing anything.
    """
    path = SCRIPTS / script_name
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id in BASELINE_NAMES for t in node.targets):
            continue
        parts = _path_parts(node.value)
        if not parts:
            continue
        # A single "var/x.json" and a ("var", "x.json") pair both land here.
        joined = REPO_ROOT
        for part in parts:
            joined = joined / part
        return joined
    return None


def _tracked(paths: list[pathlib.Path]) -> set[pathlib.Path]:
    if not paths:
        return set()
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", *[str(p) for p in paths]],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set(paths)  # no git available: do not invent failures
    return {
        (REPO_ROOT / rel).resolve()
        for rel in out.stdout.split("\0")
        if rel
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print every resolved baseline")
    args = parser.parse_args(argv)

    compare_gates = [
        (label, gate_argv)
        for label, gate_argv in _gate_argvs()
        if "--compare" in gate_argv and gate_argv and gate_argv[0].endswith(".py")
    ]

    resolved: dict[str, pathlib.Path] = {}
    unresolved: list[str] = []
    for label, gate_argv in compare_gates:
        baseline = _baseline_for(gate_argv[0])
        if baseline is None:
            unresolved.append(f"{label} ({gate_argv[0]})")
        else:
            resolved[label] = baseline

    tracked = _tracked(sorted(set(resolved.values())))
    missing = {
        label: path for label, path in resolved.items() if not path.is_file()
    }
    untracked = {
        label: path
        for label, path in resolved.items()
        if path.is_file() and path.resolve() not in tracked
    }

    if args.list:
        for label, path in sorted(resolved.items()):
            state = "MISSING" if label in missing else ("UNTRACKED" if label in untracked else "ok")
            print(f"  {state:9s} {label:38s} {path.name}")

    print(
        f"ratchet-baselines: {len(compare_gates)} --compare gate(s); "
        f"{len(resolved)} baseline(s) resolved, {len(unresolved)} unresolved, "
        f"{len(missing)} missing, {len(untracked)} untracked."
    )
    if unresolved:
        print("  no baseline constant found (reported, not failed):")
        for item in sorted(unresolved):
            print(f"    - {item}")

    if missing or untracked:
        for label, path in sorted(missing.items()):
            print(
                f"FAIL: gate {label!r} runs with --compare but its baseline "
                f"{path} does not exist. A comparison run must never author its own "
                "reference -- generate it with the scanner's --update-baseline and "
                "COMMIT it.",
                file=sys.stderr,
            )
        for label, path in sorted(untracked.items()):
            print(
                f"FAIL: gate {label!r} compares against {path}, which git does not "
                "track. It exists only on this machine, so the gate is inert for "
                "everybody else. Commit it.",
                file=sys.stderr,
            )
        return 1

    print("OK: every --compare gate has a committed baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
