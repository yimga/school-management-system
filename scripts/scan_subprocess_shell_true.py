#!/usr/bin/env python
"""``subprocess(..., shell=True)`` / ``os.system`` boundary scanner.

Flags command-injection-prone invocations under ``apps/`` and
``services/``:

  - ``subprocess.run(...)`` / ``subprocess.call(...)`` /
    ``subprocess.Popen(...)`` / ``subprocess.check_output(...)`` /
    ``subprocess.check_call(...)`` invoked with ``shell=True``.
  - ANY ``os.system(...)`` call (the function itself is a single
    string passed through ``/bin/sh`` — there is no safe form).

Why this matters: passing ``shell=True`` (or using ``os.system``)
hands argument parsing to the shell. Anywhere a tenant-controlled,
operator-supplied, or otherwise non-constant string flows in, the
result is RCE. The safe form is the list-of-args invocation
``subprocess.run(["cmd", arg1, arg2], shell=False)`` — and
``shell=False`` is already the default, so simply omitting the kwarg
is fine.

Allowlist: trusted hardcoded shell pipelines (e.g. a known-safe
``"foo | bar"`` literal with no interpolation) can be marked with
``# shell-true-allow: <reason>`` on the call line. Use very sparingly.

Output mirrors the other boundary scanners.
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-subprocess-shell.json"

SUBPROCESS_FUNCS = frozenset(
    {"run", "call", "Popen", "check_output", "check_call"}
)

ALLOW_MARKER = "shell-true-allow:"


def _iter_py_files():
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            yield path


def _is_allowlisted(source_lines: list[str], lineno: int, end_lineno: int) -> bool:
    for ln in range(lineno, end_lineno + 1):
        idx = ln - 1
        if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
            return True
    return False


def _snippet(source_lines: list[str], lineno: int) -> str:
    idx = lineno - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx].strip()[:200]
    return ""


def _attr_chain(node: ast.expr) -> list[str]:
    """Return dotted-attribute components for ``a.b.c`` -> ['a','b','c']."""
    parts: list[str] = []
    cur: ast.expr | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return list(reversed(parts))


def _classify_call(call: ast.Call) -> tuple[str, str] | None:
    """Return (kind, label) if the call is dangerous, else None.

    kind in {"os.system", "subprocess.shell_true"}.
    """
    chain = _attr_chain(call.func)
    if not chain:
        return None
    last = chain[-1]

    # os.system(...) — always dangerous.
    if last == "system" and "os" in chain:
        return ("os.system", "os.system")

    # subprocess.<func>(..., shell=True)
    if last in SUBPROCESS_FUNCS:
        # Accept call whether it's `subprocess.run(...)` or just `run(...)`
        # if the chain root is `subprocess`. We're lenient and treat any
        # call whose last attr matches as a subprocess candidate; the
        # shell=True kwarg gate keeps false positives low.
        for kw in call.keywords:
            if kw.arg == "shell":
                v = kw.value
                if isinstance(v, ast.Constant) and v.value is True:
                    return ("subprocess.shell_true", f"subprocess.{last}(shell=True)")
        return None

    return None


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            classification = _classify_call(node)
            if classification is None:
                continue
            kind, label = classification
            end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
            if _is_allowlisted(source_lines, node.lineno, end_lineno):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": node.lineno,
                    "kind": kind,
                    "label": label,
                    "snippet": _snippet(source_lines, node.lineno),
                }
            )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "subprocess(..., shell=True) and os.system() are command-injection risks; use list-of-args form",
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "subprocess_funcs": sorted(SUBPROCESS_FUNCS),
        "allow_marker": ALLOW_MARKER,
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
    print(f"subprocess-shell-true scan: {len(findings)} dangerous call(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  [{finding['kind']}]  {finding['snippet']}")


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
    baseline_set = {
        (item["path"], item["line"], item["kind"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["line"], item["kind"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW shell=True / os.system calls introduced:")
        for path, line, kind in sorted(new):
            print(f"  {path}:{line}  [{kind}]")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line, kind in sorted(removed):
            print(f"  {path}:{line}  [{kind}]")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
