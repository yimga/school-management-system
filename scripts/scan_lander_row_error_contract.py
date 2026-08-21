"""Every Migration Cloud lander must KEEP the row it rejected, and say WHY.

Step 1 of ``docs/MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC.md``, and the gate that
spec asks for by name: *"Enforce with a gate that fails when a lander appends a
bare string."*

**You cannot replay a row you did not keep.** That single sentence is why this is
a zero-tolerance gate rather than a style preference. Bundle 84 held 442 rows for
review and nobody could review them, because 29 of 35 lander files threw the
offending row away and kept only an English sentence plus a ``row_index`` that
was the position in the ERROR LIST, not in the source file. No remediator,
however good, can act on that — the evidence is gone.

Three findings, each a distinct way the evidence is lost:

``bare_error_append``
    ``result.errors.append(msg)`` — the row is discarded. Use
    ``_helpers.record_row_error(result, row, msg, reason_code=...)``.

``bare_quarantine_increment``
    ``result.quarantined += 1`` outside ``record_row_error`` — a row counted as
    held with no durable record at all, so the board's total exceeds what the
    review table can ever show.

``undeclared_reason_code``
    ``record_row_error(...)`` with no ``reason_code=``. The class is then guessed
    by substring-matching the message, which sent 60 of 106 sites to
    ``lander_error`` — "a person must look at this" — when 11 were plainly a
    missing field or an unresolvable reference. A wrong class is not a cosmetic
    problem: it is the difference between a row that resolves itself and a row
    that waits for a human who never comes.

Stdlib AST only, no Django, so this runs in the deps-free boundary job.

Mark a reviewed exception with ``# lander-contract-allow: <reason>`` on the
offending line or the line above.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LANDERS = REPO_ROOT / "apps" / "migration_cloud" / "landers"
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-lander-row-error-contract.json"

ALLOW_MARKER = "# lander-contract-allow:"

#: ``record_row_error`` / ``record_row_note`` are the contract's own
#: implementation — they are the ONE place allowed to touch the raw fields.
CONTRACT_FUNCTIONS = frozenset({"record_row_error", "record_row_note"})

#: Not landers: the abstract contract, the package export surface, the vocabulary.
NON_LANDER_MODULES = frozenset({"base.py", "__init__.py", "reason_codes.py"})


def _rel(path: Path) -> str:
    """Repo-relative POSIX path, or the path as given when it is outside the repo.

    Tolerant on purpose: the tests drive ``scan_source`` with synthetic paths, and
    a scanner that raises on one is a scanner whose detection logic cannot be
    tested without a real file tree.
    """
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _allowed(lines: list[str], lineno: int) -> bool:
    """True when the site (or the line above it) carries the allow marker."""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    """Map every line inside a function to that function's name."""
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                owner[line] = node.name
    return owner


def _is_result_errors_append(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "append"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "errors"
    )


def _is_quarantine_increment(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Attribute)
        and node.target.attr == "quarantined"
    )


def _is_record_row_error(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_row_error"
    )


def scan_source(path: Path, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A file that does not parse is verify_python_files_parse's finding, not
        # ours. Reporting it twice buries the one that says how to fix it.
        return []
    lines = source.splitlines()
    owner = _enclosing_functions(tree)
    findings: list[dict] = []

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            continue
        if owner.get(lineno) in CONTRACT_FUNCTIONS:
            continue
        if _allowed(lines, lineno):
            continue

        if _is_result_errors_append(node):
            findings.append({
                "path": _rel(path),
                "line": lineno,
                "kind": "bare_error_append",
                "detail": "row discarded — use record_row_error(result, row, msg, reason_code=...)",
            })
        elif _is_quarantine_increment(node):
            findings.append({
                "path": _rel(path),
                "line": lineno,
                "kind": "bare_quarantine_increment",
                "detail": "row counted as held with no durable record — use record_row_error",
            })
        elif _is_record_row_error(node):
            if not any(kw.arg == "reason_code" for kw in node.keywords):
                findings.append({
                    "path": _rel(path),
                    "line": lineno,
                    "kind": "undeclared_reason_code",
                    "detail": "class guessed by matching English — pass reason_code=",
                })

    findings.sort(key=lambda f: (f["path"], f["line"], f["kind"]))
    return findings


def scan() -> list[dict]:
    findings: list[dict] = []
    if not LANDERS.is_dir():
        return findings
    for path in sorted(LANDERS.glob("*.py")):
        if path.name in NON_LANDER_MODULES:
            continue
        findings.extend(scan_source(path, path.read_text(encoding="utf-8")))
    return findings


def _payload(findings: list[dict]) -> dict:
    return {"finding_count": len(findings), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(_payload(findings), indent=2) + "\n", encoding="utf-8"
        )
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings and args.strict else 0

    if not findings:
        print("lander row-error contract: 0 violation(s) — every held row keeps "
              "its source row and declares why")
        return 0

    print(f"lander row-error contract: {len(findings)} violation(s)", file=sys.stderr)
    for f in findings:
        print(f"  {f['path']}:{f['line']}  [{f['kind']}] {f['detail']}", file=sys.stderr)
    print(
        "\nA row you did not keep is a row you cannot replay. Route per-row "
        "failures through apps.migration_cloud.landers._helpers.record_row_error "
        f"with a reason_code, or mark a reviewed site '{ALLOW_MARKER} <reason>'.",
        file=sys.stderr,
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
