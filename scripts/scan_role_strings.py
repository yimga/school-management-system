#!/usr/bin/env python
"""Hardcoded-role-string scanner.

Enforces the platform's "no hardcoding" rule for the five highest-touch
role tokens — ``"ADMIN"``, ``"TEACHER"``, ``"PARENT"``, ``"STUDENT"``,
``"PROPRIETOR"``. App code that needs these tokens must import the named
constant from the canonical SOT module
(``apps/platform_runtime/role_registry.py``) or reference the Django
``User.Role.<NAME>`` TextChoices enum — never inline the bare string.

Allowlist model:

  * Canonical SOT modules are exempt (the literals must live somewhere):
    - ``apps/platform_runtime/role_registry.py`` — the constant set
      used by comparison code.
    - ``apps/accounts/models.py`` — the Django ``User.Role``
      ``TextChoices`` enum, which is the ORM-layer SOT.
  * Specific lines can be marked with ``# role-string-allow: <reason>``
    on the same line OR the line immediately above the literal. Use
    sparingly — every entry is a "no hardcoding" contract escape.

Scope:

  * Walks ``apps/`` recursively.
  * Skips ``migrations/`` (historical state — frozen by design),
    ``tests/`` (test fixtures), and ``management/commands/`` (operator
    scripts where role tokens are seed data, not policy).

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
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-role-strings.json"

ROLE_TOKENS = frozenset({"ADMIN", "TEACHER", "PARENT", "STUDENT", "PROPRIETOR"})

# Canonical SOT modules — role literals are allowed to live here.
SOT_MODULES = frozenset(
    {
        APPS_DIR / "platform_runtime" / "role_registry.py",
        APPS_DIR / "accounts" / "models.py",
    }
)

# Directory segments that are intentionally exempt from the scan.
EXCLUDED_SEGMENTS = frozenset({"migrations", "tests"})
# Excluded sub-paths matched as a 2-segment tail (e.g. ``management/commands``).
EXCLUDED_TAILS = frozenset({("management", "commands")})

ALLOW_MARKER = "role-string-allow:"


def _is_excluded(path: Path) -> bool:
    parts = path.relative_to(APPS_DIR).parts
    if any(seg in EXCLUDED_SEGMENTS for seg in parts):
        return True
    for i in range(len(parts) - 1):
        if (parts[i], parts[i + 1]) in EXCLUDED_TAILS:
            return True
    return False


def _iter_app_files():
    if not APPS_DIR.exists():
        return
    for path in sorted(APPS_DIR.rglob("*.py")):
        if path in SOT_MODULES:
            continue
        if _is_excluded(path):
            continue
        yield path


def _is_allowlisted(source_lines: list[str], lineno: int) -> bool:
    # Check the literal's line and the line immediately above for the marker.
    for offset in (0, -1):
        idx = lineno - 1 + offset
        if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
            return True
    return False


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_app_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            if node.value not in ROLE_TOKENS:
                continue
            if _is_allowlisted(source_lines, node.lineno):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": node.lineno,
                    "role": node.value,
                }
            )
    findings.sort(key=lambda item: (item["path"], item["line"], item["role"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Role-name string literals outside apps/platform_runtime/role_registry.py "
            "must be replaced with the canonical ROLE_* constant (or User.Role.<NAME>.value)."
        ),
        "scan_dir": APPS_DIR.relative_to(REPO_ROOT).as_posix(),
        "role_tokens": sorted(ROLE_TOKENS),
        "sot_modules": sorted(
            m.relative_to(REPO_ROOT).as_posix() for m in SOT_MODULES
        ),
        "excluded_segments": sorted(EXCLUDED_SEGMENTS),
        "excluded_tails": sorted("/".join(t) for t in EXCLUDED_TAILS),
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
    print(f"Role-string scan: {len(findings)} hardcoded role literal(s)")
    for finding in findings[:50]:
        print(f"  {finding['path']}:{finding['line']}  \"{finding['role']}\"")
    if len(findings) > 50:
        print(f"  ... and {len(findings) - 50} more (see --json for full list)")


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
        (item["path"], item["line"], item["role"])
        for item in baseline.get("findings", [])
    }
    current_set = {
        (item["path"], item["line"], item["role"]) for item in findings
    }
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW hardcoded role-string literals introduced:")
        for path, line, role in sorted(new):
            print(f"  {path}:{line}  \"{role}\"")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, line, role in sorted(removed):
            print(f"  {path}:{line}  \"{role}\"")
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
