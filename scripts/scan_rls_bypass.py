#!/usr/bin/env python
"""RLS bypass scanner.

Flags raw-SQL-ish call sites in ``apps/`` and ``services/`` that escape
the ORM's tenant-isolation safety net. Specifically:

* ``QuerySet.raw(...)``
* ``QuerySet.extra(...)``
* ``Manager.raw(...)``
* ``RawSQL(...)``
* ``connection.cursor()`` / ``cursor.execute()``

These call sites *can* be safe — when the caller has already entered an
``apps.schools.rls_context.set_rls_school_id(...)`` block or when the
operation is intentionally cross-tenant (digests, observability,
platform analytics). To make that decision auditable, the scanner
requires an explicit allowlist comment on (or directly above) the call
line::

    # rls-bypass-allow: cross-tenant by design (friction digest)

Anything without that comment becomes a finding. Baseline lives in
``var/security-audit-baseline-rls-bypass.json``; CI wires this scanner
the same way as the other architectural-boundary gates.

Output mirrors ``scan_bare_except.py`` / ``scan_tenant_queryset_safety.py``:

* default run: print summary + write baseline.
* ``--compare``: exit 1 if any **new** finding (relative to baseline)
  is present; exit 0 otherwise.
* ``--json``: print the baseline payload as JSON.

Design note: this is a textual/AST scanner, not a runtime guard. The
runtime guard is Postgres RLS itself. The scanner exists so that PR
authors must justify every raw-SQL path in writing.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (REPO_ROOT / "apps", REPO_ROOT / "services")
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-rls-bypass.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations"}
EXCLUDE_FILE_SUFFIXES = ("_test.py", "_tests.py")

# Files explicitly carved out — these define / wrap the RLS surface itself.
ALWAYS_ALLOWED_PATHS = frozenset({
    "apps/schools/rls_context.py",
    "apps/schools/repositories/rls_context_repository.py",
    "apps/schools/migrations",  # Django immutable history; RLS DDL emits raw SQL by design
})

# Tokens that, when found in the source line OR the line above, exempt the
# call from being a finding. Matches the comment styles other scanners use.
ALLOW_COMMENT_PREFIX = "# rls-bypass-allow:"

# AST patterns flagged.
FLAGGED_METHODS = frozenset({"raw", "extra", "execute"})
FLAGGED_NAMES = frozenset({"RawSQL"})


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if "tests" in rel_parts:
            continue
        if path.name.endswith(EXCLUDE_FILE_SUFFIXES):
            continue
        rel_posix = path.relative_to(REPO_ROOT).as_posix()
        if any(rel_posix.startswith(allowed) for allowed in ALWAYS_ALLOWED_PATHS):
            continue
        yield path


def _is_allowed(source_lines: list[str], lineno: int) -> bool:
    """Allowlist if the same line or the line above carries the marker."""
    if 1 <= lineno <= len(source_lines):
        if ALLOW_COMMENT_PREFIX in source_lines[lineno - 1]:
            return True
    if 2 <= lineno <= len(source_lines):
        if ALLOW_COMMENT_PREFIX in source_lines[lineno - 2]:
            return True
    return False


def _find_calls(tree: ast.AST, source_lines: list[str]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        marker = _classify_call(node)
        if marker is None:
            continue
        lineno = getattr(node, "lineno", 0) or 0
        if _is_allowed(source_lines, lineno):
            continue
        hits.append((lineno, marker))
    return hits


def _classify_call(node: ast.Call) -> str | None:
    func = node.func
    # Attribute calls: .raw(...) / .extra(...) / .execute(...)
    if isinstance(func, ast.Attribute):
        attr = func.attr
        if attr in FLAGGED_METHODS:
            if attr == "execute":
                # Only cursor.execute(...) is interesting; module-level
                # `something.execute()` calls are usually safe (`subprocess`,
                # `concurrent.futures`, etc). We require the receiver to be
                # a `cursor`-named binding to reduce false positives.
                receiver = func.value
                if isinstance(receiver, ast.Name) and "cursor" in receiver.id.lower():
                    return ".execute() (cursor)"
                if isinstance(receiver, ast.Attribute) and "cursor" in receiver.attr.lower():
                    return ".execute() (cursor)"
                return None
            return f".{attr}()"
    # Bare name calls: RawSQL(...)
    if isinstance(func, ast.Name) and func.id in FLAGGED_NAMES:
        return f"{func.id}()"
    return None


def _scan() -> list[dict]:
    findings: list[dict] = []
    for root in SCAN_DIRS:
        for path in _iter_python_files(root):
            rel = path.relative_to(REPO_ROOT).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            source_lines = source.splitlines()
            for lineno, marker in _find_calls(tree, source_lines):
                findings.append({"path": rel, "line": lineno, "call": marker})
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Raw-SQL / cursor.execute / .raw() / .extra() / RawSQL() callsites "
            "must either run inside set_rls_school_id() or carry an "
            "'# rls-bypass-allow: <reason>' comment."
        ),
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "allow_comment_prefix": ALLOW_COMMENT_PREFIX,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"RLS-bypass scan: {len(findings)} unallowlisted callsite(s)")
    for finding in findings[:50]:
        print(f"  {finding['path']}:{finding['line']}  {finding['call']}")
    if len(findings) > 50:
        print(f"  …and {len(findings) - 50} more")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(item["path"], item["line"]) for item in baseline.get("findings", [])}
    current_set = {(item["path"], item["line"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW RLS-bypass callsites introduced:")
        for path, line in sorted(new):
            print(f"  {path}:{line}")
        print(
            "\nTo allow: add  # rls-bypass-allow: <reason>  on (or directly "
            "above) the line, or wrap the call in set_rls_school_id()."
        )
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line in sorted(removed):
            print(f"  {path}:{line}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        dest="update_baseline",
        help=(
            "Rewrite the baseline from the current tree, then exit 0. "
            "Deliberate and auditable; the default run never writes."
        ),
    )
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    if args.update_baseline:
        _print_summary(findings)
        _write_baseline(findings)
        return 0
    # Default is READ-ONLY and fails on findings.
    #
    # It used to print a summary, REWRITE the baseline and return 0. Running the
    # bare script therefore reported success and destroyed the evidence of drift
    # in the same command -- an auditor checking this gate by hand silently
    # re-baselined it. That is how a genuinely new callsite sat unnoticed.
    _print_summary(findings)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
