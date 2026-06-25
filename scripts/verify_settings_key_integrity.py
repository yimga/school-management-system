#!/usr/bin/env python
"""Runtime settings-key integrity verifier.

Fifth member of the reference-integrity family (imports, dynamic models, URL
names, templates, and now Django settings). Closes the loophole where code
reads a settings attribute that the deployed configuration never defines:

    from django.conf import settings
    ...
    if settings.FEATURE_BUDGET_CAP:   # typo'd / removed -> AttributeError 500

A bare ``settings.MISSING`` (or ``getattr(settings, "MISSING")`` with no
default) raises ``AttributeError`` at runtime — a hard 500 on whatever request
path first touches it, or a silently-swallowed dead branch. ``manage.py check``
never catches it; a static scan can't know the full settings surface (env-var
driven, sub-module split, third-party app defaults).

Ground truth is the LIVE ``django.conf.settings`` object after ``django.setup``
(``hasattr`` against the resolved config), so there are no false positives from
incomplete static knowledge — exactly the approach ``verify_get_model_integrity``
uses against the app registry.

Reference shapes checked (``apps/`` + ``services/`` + ``config/``):

* ``settings.NAME`` attribute access where ``settings`` is bound to
  ``django.conf.settings`` in that file (``from django.conf import settings``)
  and ``NAME`` is an UPPER_SNAKE settings key (read context only — assignment
  targets ``settings.NAME = ...`` are skipped).
* ``getattr(settings, "NAME")`` with a string literal and **no default** — the
  3-arg form ``getattr(settings, "NAME", default)`` is safe and skipped.

Excused (zero false positives):

* a read inside ``try/except (AttributeError|Exception|BaseException|bare|
  named-tuple-guard)`` — a deliberate optional-setting pattern.
* a ``# settings-key-allow: <reason>`` marker on the line or the line above.
* migrations + test files; files that don't import ``django.conf.settings``.

Requires Django (run in a deps-installed CI job, e.g. ci.yml::django-tests).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("apps", "services", "config")
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-settings-key-integrity.json"

ALLOW_MARKER = "settings-key-allow:"
_GUARD_EXC_NAMES = {"AttributeError", "ImproperlyConfigured", "Exception", "BaseException"}
# An UPPER_SNAKE name is a Django settings key; lowercase attrs (settings.foo)
# are method/helper accesses, never a setting.
_SETTING_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


# --------------------------------------------------------------------------
# Guard / marker awareness (mirrors verify_get_model_integrity)
# --------------------------------------------------------------------------
def _exception_tuple_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
            members = {
                (getattr(e, "id", None) or getattr(e, "attr", None))
                for e in node.value.elts
            }
            if members & _GUARD_EXC_NAMES:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        aliases.add(tgt.id)
    return aliases


def _guarded_linenos(tree: ast.AST) -> set[int]:
    guarded: set[int] = set()
    tuple_aliases = _exception_tuple_aliases(tree)

    def handler_catches(handlers: list[ast.ExceptHandler]) -> bool:
        for h in handlers:
            if h.type is None:
                return True
            exc_nodes = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
            for e in exc_nodes:
                nm = getattr(e, "id", None) or getattr(e, "attr", None)
                if nm in _GUARD_EXC_NAMES or nm in tuple_aliases:
                    return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and handler_catches(node.handlers):
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    ln = getattr(inner, "lineno", None)
                    if ln is not None:
                        guarded.add(ln)
    return guarded


def _marked_linenos(source_lines: list[str]) -> set[int]:
    return {i + 1 for i, line in enumerate(source_lines) if ALLOW_MARKER in line}


def _is_excused(lineno: int, guarded: set[int], marked: set[int]) -> bool:
    return lineno in guarded or lineno in marked or (lineno - 1) in marked


def _hasattr_guarded(line_text: str, name: str) -> bool:
    """The common inline guard ``settings.NAME if hasattr(settings, "NAME") ...``
    (and ``if hasattr(settings, "NAME"): ... settings.NAME`` on one line) is a
    deliberate optional-setting read — never an AttributeError."""
    return (
        f'hasattr(settings, "{name}")' in line_text
        or f"hasattr(settings, '{name}')" in line_text
    )


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
def _iter_py_files():
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            parts = set(path.parts)
            if "migrations" in parts or "tests" in parts or path.name.startswith("test_"):
                continue
            yield path


def _imports_django_settings(tree: ast.AST) -> bool:
    """True if the file binds the name ``settings`` to ``django.conf.settings``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "django.conf":
            for alias in node.names:
                if alias.name == "settings" and (alias.asname or "settings") == "settings":
                    return True
    return False


def _is_settings_assignment_target(node: ast.Attribute) -> bool:
    return isinstance(node.ctx, ast.Store)


def collect_names(source: str) -> list[tuple[int, str]]:
    """Return (lineno, SETTING_NAME) for every checked read in ``source``.

    Pure-AST; no guard/marker filtering (callers apply that). Exposed for tests.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    if not _imports_django_settings(tree):
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # settings.NAME  (read context only)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "settings"
            and not _is_settings_assignment_target(node)
            and _SETTING_NAME.match(node.attr)
        ):
            found.append((node.lineno, node.attr))
        # getattr(settings, "NAME")  with NO default
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "settings"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and _SETTING_NAME.match(node.args[1].value)
        ):
            found.append((node.lineno, node.args[1].value))
    return found


def _collect_targets() -> list[dict]:
    targets: list[dict] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names = collect_names(source)
        if not names:
            continue
        tree = ast.parse(source)
        guarded = _guarded_linenos(tree)
        source_lines = source.splitlines()
        marked = _marked_linenos(source_lines)
        for lineno, name in names:
            if _is_excused(lineno, guarded, marked):
                continue
            line_text = source_lines[lineno - 1] if 0 < lineno <= len(source_lines) else ""
            if _hasattr_guarded(line_text, name):
                continue
            targets.append({"path": rel, "line": lineno, "name": name})
    return targets


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------
def _resolve(targets: list[dict]) -> list[dict]:
    import django
    from django.conf import settings as live_settings

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    findings: list[dict] = []
    for t in targets:
        if not hasattr(live_settings, t["name"]):
            findings.append(t)
    findings.sort(key=lambda i: (i["path"], i["line"], i["name"]))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every literal settings.NAME read (and getattr(settings,'NAME') "
        "with no default) must resolve on the live django.conf.settings; guard "
        "with try/except AttributeError, a getattr default, or "
        "# settings-key-allow: <reason>",
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


def _print_summary(findings: list[dict], scanned: int) -> None:
    print(
        f"settings-key integrity: {scanned} literal read(s) checked, "
        f"{len(findings)} unresolved"
    )
    for f in findings:
        print(f"  {f['path']}:{f['line']}  settings.{f['name']}  [AttributeError]")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _key(f: dict) -> tuple[str, str]:
    return (f["path"], f["name"])


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {_key(i) for i in baseline.get("findings", [])}
    current_set = {_key(i) for i in findings}
    new = current_set - baseline_set
    if new:
        print("\nNEW unresolved settings keys introduced:")
        for path, name in sorted(new):
            print(f"  {path}  settings.{name}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    targets = _collect_targets()
    findings = _resolve(targets)

    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    _print_summary(findings, len(targets))
    if args.compare:
        return _compare(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
