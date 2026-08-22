"""Landers must stream canonical rows — not buffer whole files without an allow marker.

``list(canonical_rows)``, list/set/dict comprehensions, ``sorted(canonical_rows)``, or
``for row in list(canonical_rows)`` before the write loop means row heartbeats only
fire during materialisation; a large file can then spend minutes in DB writes with a
frozen ``rows_processed`` counter and trip ``SystemicStallError``. Streaming
``for row in canonical_rows`` (or an explicit ``# lander-stream-allow: <reason>``
plus ``maybe_stall_pulse`` in post-buffer loops) keeps the apply watchdog honest.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LANDERS = REPO_ROOT / "apps" / "migration_cloud" / "landers"
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-lander-row-streaming.json"

ALLOW_MARKER = "# lander-stream-allow:"
NON_LANDER_MODULES = frozenset({"base.py", "__init__.py", "reason_codes.py"})
_CANONICAL_ROWS = "canonical_rows"
_MATERIALIZE_FUNCS = frozenset({"list", "tuple", "sorted"})


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _allowed(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _is_canonical_rows(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Name) and node.id == _CANONICAL_ROWS


def _call_materializes_canonical_rows(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id not in _MATERIALIZE_FUNCS:
        return False
    return bool(node.args) and _is_canonical_rows(node.args[0])


def _comp_materializes_canonical_rows(node: ast.AST) -> bool:
    if not isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
        return False
    if not node.generators:
        return False
    return _is_canonical_rows(node.generators[0].iter)


def _materializes_canonical_rows(node: ast.AST) -> str | None:
    if _call_materializes_canonical_rows(node):
        func = getattr(getattr(node, "func", None), "id", "list")
        return f"{func}(canonical_rows)"
    if _comp_materializes_canonical_rows(node):
        return f"{type(node).__name__}(canonical_rows)"
    if isinstance(node, ast.For) and _call_materializes_canonical_rows(node.iter):
        func = node.iter.func.id  # type: ignore[union-attr]
        return f"for ... in {func}(canonical_rows)"
    return None


def scan_source(path: Path, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    findings: list[dict] = []
    for node in ast.walk(tree):
        kind = _materializes_canonical_rows(node)
        if kind is None:
            continue
        lineno = getattr(node, "lineno", None)
        if lineno is None or _allowed(lines, lineno):
            continue
        findings.append({
            "path": _rel(path),
            "line": lineno,
            "kind": "buffered_canonical_rows",
            "detail": (
                f"{kind} stalls row heartbeats during DB writes — stream or allow + "
                "maybe_stall_pulse"
            ),
        })
    findings.sort(key=lambda f: (f["path"], f["line"]))
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
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(_payload(findings), indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings and args.strict else 0

    if not findings:
        print("lander row-streaming: 0 violation(s) — apply heartbeats stay honest")
        return 0

    print(f"lander row-streaming: {len(findings)} violation(s)", file=sys.stderr)
    for f in findings:
        print(f"  {f['path']}:{f['line']}  [{f['kind']}] {f['detail']}", file=sys.stderr)
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
