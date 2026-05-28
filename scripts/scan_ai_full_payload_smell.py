#!/usr/bin/env python
"""Full-payload smell scanner for AI calls (v4.00.0 zero-tolerance gate).

Flags any non-test code path that awaits a full AI completion via
``invoke_with_request`` / ``_call_litellm`` / urllib ``read()`` against the
LiteLLM proxy when a viewport context is available. The rule: any view or
service that has access to ``request.rmc_viewport`` MUST use the streaming
gateway (``services.ai_gateway_stream.stream_litellm``) instead of the
non-streaming entry point.

Heuristic implementation: a function that mentions BOTH ``rmc_viewport``
(or ``X-RMC-Viewport``) AND a non-streaming AI call is flagged. Mentioning
streaming + non-streaming together is fine (the streaming path is the
canonical path; the non-streaming one is the rules/fallback chain).
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-ai-full-payload-smell.json"

EXCLUDE_DIR_NAMES = {"__pycache__", "node_modules", "migrations", "tests", "management"}
EXCLUDE_PATH_SEGMENTS = ("services/ai_gateway.py", "services/ai_gateway_stream.py")

NON_STREAMING_MARKERS = ("_call_litellm", "invoke_with_request")
STREAMING_MARKERS = ("stream_litellm", "stream_to_channel_group")
VIEWPORT_MARKERS = ("rmc_viewport", "X-RMC-Viewport", "X_RMC_VIEWPORT")


def _iter_python_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(seg in rel for seg in EXCLUDE_PATH_SEGMENTS):
            continue
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        yield path


def _function_targets(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for root in SCAN_DIRS:
        for path in _iter_python_files(root):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            for fn in _function_targets(tree):
                try:
                    src = ast.unparse(fn)
                except AttributeError:
                    continue
                has_viewport = any(m in src for m in VIEWPORT_MARKERS)
                if not has_viewport:
                    continue
                has_non_streaming = any(m in src for m in NON_STREAMING_MARKERS)
                if not has_non_streaming:
                    continue
                has_streaming = any(m in src for m in STREAMING_MARKERS)
                if has_streaming:
                    continue
                findings.append({
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "line": fn.lineno,
                    "function": fn.name,
                    "reason": "viewport-aware AI call must use stream_litellm, not the blocking gateway",
                })
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "code paths that have a viewport context AND call the AI gateway "
            "must use the streaming entry point (services.ai_gateway_stream)"
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
    print(f"ai_full_payload_smell scan: {len(findings)} smell(s)")
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
        print("\nNEW non-streaming AI calls in viewport-aware code paths:")
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
