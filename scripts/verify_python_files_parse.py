#!/usr/bin/env python
"""Every Python file in the tree must actually parse.

The cheapest possible gate against the most catastrophic failure: a module that does not
compile cannot be imported at all. Celery autodiscovers ``<app>.tasks`` for every installed
app, Django imports ``<app>.models`` / ``admin`` / ``apps`` at startup, and any
``from apps.x import y`` against a broken module is an ImportError 500 on whatever path
touches it first.

WHY THIS EXISTS. On 2026-08-19 ``apps/accounts/tasks.py`` was found **truncated
mid-statement** on ``main`` — a commit had removed the last three lines of the file, leaving
``return {`` unclosed. The module could not be imported. Nothing caught it:

  * ``scan_import_reference_integrity`` AST-parses a target module to resolve symbols, but
    treats a parse failure as *opaque* and skips the check — it is biased toward false
    negatives by design, so a broken file is silently excused rather than reported.
  * ``verify_get_model_integrity`` and the other runtime verifiers only reach modules that
    Django successfully imported.
  * The test suite only imports what a selected test happens to touch, so the breakage
    surfaced as five unrelated collection errors in a directory nobody was running.

Every one of those is reasonable in isolation. Together they left the single most basic
invariant — *the source compiles* — unenforced. This gate closes that, in about a second,
with no dependencies.

Zero tolerance: there is no baseline and no allow-marker, because a file that does not
parse is never intentional.

Exit codes: 0 clean, 1 one or more files do not parse.
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Everything that ships or runs. `scripts/` is included deliberately: a broken gate script
# is a gate that silently stops gating.
SCAN_ROOTS = ("apps", "services", "config", "scripts")

# Directories that legitimately hold files Python should not be asked to parse.
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "migrations_backup",
}


def _iter_python_files(roots):
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            yield path


def scan(roots=SCAN_ROOTS):
    """Return ``(checked, findings)`` where a finding is ``(relpath, lineno, message)``."""
    findings = []
    checked = 0
    for path in _iter_python_files(roots):
        checked += 1
        try:
            with io.open(path, encoding="utf8") as fh:
                source = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            findings.append((path.relative_to(REPO_ROOT).as_posix(), 0, f"unreadable: {exc}"))
            continue
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                (
                    path.relative_to(REPO_ROOT).as_posix(),
                    exc.lineno or 0,
                    exc.msg or "syntax error",
                )
            )
        except ValueError as exc:  # e.g. source containing null bytes
            findings.append((path.relative_to(REPO_ROOT).as_posix(), 0, str(exc)))
    return checked, findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--roots",
        nargs="*",
        default=list(SCAN_ROOTS),
        help="directories to scan (default: %s)" % " ".join(SCAN_ROOTS),
    )
    args = parser.parse_args(argv)

    checked, findings = scan(tuple(args.roots))
    if not findings:
        print(f"python-parse: {checked} file(s) checked, 0 do not parse")
        return 0

    print(f"python-parse: {checked} file(s) checked, {len(findings)} DO NOT PARSE")
    for rel, lineno, msg in findings:
        print(f"  {rel}:{lineno}: {msg}")
    print("")
    print("A module that does not compile cannot be imported at all. Fix the file;")
    print("there is no baseline and no allow-marker for this gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
