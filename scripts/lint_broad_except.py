#!/usr/bin/env python3
"""
Flag broad except usage.

Supports:
- full scan report mode
- baseline-enforced allowlist mode for high-risk files

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "tests"}
ALLOWED_PREFIXES = (
    "apps/platform_runtime/runtime_resolver.py",
    "apps/siteconfig/management/",
    "apps/compliance/management_commands.py",
    "scripts/",
)
PATTERNS = (
    re.compile(r"\bexcept\s+Exception\b"),
    re.compile(r"\bexcept\s+BaseException\b"),
)


DEFAULT_UNLISTED_BASELINE = ROOT / "var" / "broad-except-unlisted-baseline.json"


def _load_unlisted_baseline(path: str | None) -> dict[str, int]:
    """Counts for files the curated allowlist does not name.

    Until 2026-08-28 there was no such thing, and the consequence was not
    subtle: the allowlist branch iterated the ALLOWLIST's keys and asked
    `counts.get(path, 0)` for each, so a file absent from the list was never
    examined at all. 189 files were named -- 147 of them carrying zero broad
    excepts -- while 921 files carrying 3227 of them were invisible, and a new
    module with `except Exception:` AND `except BaseException:` passed cleanly.

    The curated allowlist stays what it is: a human policy artifact with an
    issue link and a review date, for the high-risk paths somebody argued
    about. This is the machine ratchet underneath it, so that "not on the list"
    means "must not grow" instead of "not looked at".
    """
    target = pathlib.Path(path) if path else DEFAULT_UNLISTED_BASELINE
    if not target.is_file():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    counts = raw.get("counts", raw)
    return {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}


def _count_broad_lines(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if any(pattern.search(line) for pattern in PATTERNS):
            count += 1
    return count


@lru_cache(maxsize=None)
def _tracked_file_relpaths(base: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not create false positives."""
    if not (base / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            cwd=str(base),
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    relpaths: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relpaths.add(Path(raw.decode("utf-8")).as_posix())
        except UnicodeDecodeError:
            continue
    return frozenset(relpaths)


def _iter_candidate_python_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        scan_prefixes = ("apps/", "config/")
        for rel in sorted(tracked):
            if not rel.startswith(scan_prefixes) or not rel.endswith(".py"):
                continue
            py_path = base / Path(rel)
            if not py_path.is_file():
                continue
            if any(part in SKIP_DIRS for part in py_path.parts):
                continue
            yield py_path
        return
    for root_name in ("apps", "config"):
        root = base / root_name
        if not root.is_dir():
            continue
        for py_path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in py_path.parts):
                continue
            yield py_path


def _scan_counts(base: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for py_path in _iter_candidate_python_files(base):
        rel = py_path.relative_to(base).as_posix()
        if rel.startswith("apps/") and ("/tests/" in rel or "/test_" in rel):
            continue
        if any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count = _count_broad_lines(text)
        if count:
            counts[rel] = count
    return counts


def _merge_allowlisted_services_counts(base: Path, counts: dict[str, int], allowlist: dict[str, int]) -> None:
    """Baseline may include services/*.py (e.g. ai_gateway); scan only allowlisted paths."""
    for rel in allowlist:
        if not rel.startswith("services/"):
            continue
        py_path = base / rel
        if not py_path.is_file():
            continue
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        counts[rel] = _count_broad_lines(text)


def _load_allowlist(path: str | None) -> dict[str, int]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = payload.get("allowed_counts", {})
    if not isinstance(allowed, dict):
        raise ValueError("allowlist must contain an 'allowed_counts' object")
    return {str(key).replace("\\", "/"): int(value) for key, value in allowed.items()}


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag broad except usage.")
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 when violations are found."
    )
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0.")
    parser.add_argument(
        "--allowlist", help="JSON file of file -> allowed broad-except count."
    )
    parser.add_argument(
        "--unlisted-baseline",
        help="JSON ratchet for files the allowlist does not name (default: "
        "var/broad-except-unlisted-baseline.json). Absent from both means 0 allowed.",
    )
    parser.add_argument(
        "--update-unlisted-baseline",
        action="store_true",
        help="Rewrite the unlisted ratchet from the current tree. Freezes today's "
        "population; it can only fall from there.",
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repo base path (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_broad_except: {exc}", file=sys.stderr)
        return 1
    if not (base / "apps").is_dir():
        return 0

    counts = _scan_counts(base)
    allowlist = _load_allowlist(args.allowlist)

    if args.update_unlisted_baseline:
        target = pathlib.Path(args.unlisted_baseline or DEFAULT_UNLISTED_BASELINE)
        payload = {
            "rule": "files NOT named by scripts/allowlists/broad_except_allowlist.json "
            "may not carry more broad excepts than recorded here; absent means 0",
            "counts": {p: c for p, c in sorted(counts.items()) if p not in allowlist and c},
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"lint_broad_except: unlisted ratchet written to {target} "
              f"({len(payload['counts'])} file(s))")
        return 0

    if allowlist:
        _merge_allowlisted_services_counts(base, counts, allowlist)
        violations: list[tuple[str, int, int]] = []
        for path, allowed_count in sorted(allowlist.items()):
            actual = counts.get(path, 0)
            if actual > allowed_count:
                violations.append((path, actual, allowed_count))
        # And now everything the curated list does NOT name. Without this the
        # gate cannot see a new file, which is the direction it exists to
        # protect.
        unlisted = _load_unlisted_baseline(getattr(args, "unlisted_baseline", None))
        for path in sorted(counts):
            if path in allowlist:
                continue
            actual = counts[path]
            allowed_count = unlisted.get(path, 0)
            if actual > allowed_count:
                violations.append((path, actual, allowed_count))
        if not violations:
            print("lint_broad_except: baseline respected for high-risk paths.")
            return 0
        print("lint_broad_except: broad except baseline exceeded:\n")
        for path, actual, allowed_count in violations:
            print(f"  {path}: {actual} > allowed {allowed_count}")
        return 0 if args.exit_zero else 1

    if not counts:
        print(
            "lint_broad_except: No broad except Exception/BaseException in non-allowed paths."
        )
        return 0

    items = sorted(counts.items())
    print("lint_broad_except: Broad except usage found:\n")
    for path, count in items[:50]:
        print(f"  {path}: {count}")
    if len(items) > 50:
        print(f"  ... and {len(items) - 50} more.")
    total = sum(count for _path, count in items)
    print(f"\nTotal: {total} hit(s) across {len(items)} file(s).")
    if args.exit_zero:
        return 0
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main(None))
