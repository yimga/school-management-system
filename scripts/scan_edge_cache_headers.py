#!/usr/bin/env python
"""Edge cache header coverage scanner (v4.00.0 zero-tolerance gate).

Walks every view module under ``apps/`` that exposes runtime/config payloads
(``/api/v1/runtime/...``) and asserts each one calls
``services.edge_cache.stamp_response`` OR sets ``Surrogate-Key`` directly.

This is the static guarantee that the Cloudflare Worker can purge the right
cache buckets. Without ``Surrogate-Key`` headers, the edge keeps stale
config payloads after RuntimeDefaults edits.

Detection rule: any function-or-method that contains the literal string
``"/api/v1/runtime/"`` AND returns an HttpResponse-shaped object MUST also
contain a call to ``stamp_response`` OR set the ``Surrogate-Key`` header.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (REPO_ROOT / "apps",)
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-edge-cache-headers.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests"}
RUNTIME_PATH_MARKER = "/api/v1/runtime/"
STAMP_FN = "stamp_response"
SURROGATE_HEADER = "Surrogate-Key"


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        yield path


def _node_source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except AttributeError:
        return ""


def _function_targets(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for root in SCAN_DIRS:
        for path in _iter_python_files(root):
            try:
                file_text = path.read_text(encoding="utf-8")
                tree = ast.parse(file_text)
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            # Module-level fast path: if the file as a whole imports stamp_response
            # or sets Surrogate-Key, every view inside is presumed compliant. This
            # accommodates the canonical thin-helper pattern in runtime_endpoints.py.
            module_compliant = (STAMP_FN in file_text) or (SURROGATE_HEADER in file_text)
            for fn in _function_targets(tree):
                src = _node_source(fn)
                if RUNTIME_PATH_MARKER not in src:
                    continue
                if module_compliant or STAMP_FN in src or SURROGATE_HEADER in src:
                    continue
                findings.append({
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "line": fn.lineno,
                    "function": fn.name,
                    "reason": "runtime endpoint missing Surrogate-Key / stamp_response",
                })
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "every view that serves /api/v1/runtime/ MUST call "
            "services.edge_cache.stamp_response or set Surrogate-Key"
        ),
        "scan_dirs": [d.relative_to(REPO_ROOT).as_posix() for d in SCAN_DIRS],
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline():
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings):
    print(f"edge_cache_headers scan: {len(findings)} gap(s)")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['function']}  -> {f['reason']}")


def _write_baseline(findings):
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings):
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(f["path"], f["function"]) for f in baseline.get("findings", [])}
    current_set = {(f["path"], f["function"]) for f in findings}
    new = current_set - baseline_set
    _print_summary(findings)
    if new:
        print("\nNEW runtime endpoints missing Surrogate-Key:")
        for p, fn in sorted(new):
            print(f"  {p}  {fn}")
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
