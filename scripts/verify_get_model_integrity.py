#!/usr/bin/env python
"""Runtime ``get_model`` integrity verifier.

Companion to the static ``scan_import_reference_integrity`` gate. That gate
seals *import* references (``from apps.X import Y``) but deliberately cannot
resolve **dynamic model lookups** — ``apps.get_model("evals", "GradeImportJob")``
— because whether a model is *registered* is a runtime property of Django's
app registry, invisible to AST. A model class can be physically defined in a
``models_*.py`` file (so a static scan would "find" it) yet be **unregistered**
— no migration, not in any installed app's model set — so ``get_model`` raises
``LookupError`` at runtime. That is exactly the bug that shipped in
``apps/evals/import_services.py`` (``get_model("evals", "GradeImportJob")`` /
``"GradeImportRowLog"`` — defined only in the abandoned migration-less
``evals/models_enhanced.py``): a static check would have a FALSE NEGATIVE.

This verifier closes that gap with ground truth. It AST-scans ``apps/`` +
``services/`` for ``get_model`` calls with string-literal arguments, then asks
the **live registry** (``django.apps.apps.get_model``) whether each resolves.
A ``LookupError`` is a finding.

Two call shapes are recognized:

* ``get_model("app_label", "ModelName")`` / ``apps.get_model(...)`` /
  ``django_apps.get_model(...)`` — two literal args.
* ``get_model("app_label.ModelName")`` — single dotted literal.

Excused (zero false positives):

* a call inside a ``try/except (LookupError|Exception|BaseException|bare)``
  block (incl. ``except <NAMED_TUPLE>:`` where the tuple includes a guard
  exception) — a deliberate optional-model / graceful-degrade pattern.
* a ``# get-model-allow: <reason>`` marker on the call's line or the line
  above (e.g. a model that is intentionally provisioned later).
* non-literal args (``get_model(f"{app}.{m}")``, variables) — unresolvable
  statically, left to runtime.
* migrations (their ``get_model`` is the historical registry, run at migrate
  time) and test files.

Requires Django (run in a deps-installed CI job, e.g. ci.yml::django-tests,
after ``manage.py check``). Output mirrors the boundary scanners.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-get-model-integrity.json"

ALLOW_MARKER = "get-model-allow:"
_GUARD_EXC_NAMES = {"LookupError", "Exception", "BaseException"}


# --------------------------------------------------------------------------
# Guard / marker awareness (mirrors scan_import_reference_integrity)
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


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
def _iter_py_files():
    for root in (APPS_DIR, REPO_ROOT / "services"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            parts = set(path.parts)
            if "migrations" in parts:
                continue
            if "tests" in parts or path.name.startswith("test_"):
                continue
            yield path


def _is_get_model_call(call: ast.Call) -> bool:
    fn = call.func
    name = getattr(fn, "attr", None) or getattr(fn, "id", None)
    return name == "get_model"


def _literal_target(call: ast.Call) -> tuple[str, str] | None:
    """Return (app_label, model_name) if the call has resolvable literal args."""
    consts = [a for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    # two-arg form: get_model("app", "Model")
    if len(call.args) >= 2 and isinstance(call.args[0], ast.Constant) and isinstance(call.args[1], ast.Constant):
        a0, a1 = call.args[0].value, call.args[1].value
        if isinstance(a0, str) and isinstance(a1, str):
            return (a0, a1)
    # single dotted form: get_model("app.Model")
    if len(call.args) == 1 and consts and "." in consts[0].value:
        app, _, model = consts[0].value.partition(".")
        if app and model:
            return (app, model)
    return None


def _collect_targets() -> list[dict]:
    """All resolvable, non-excused get_model literal targets in the tree."""
    targets: list[dict] = []
    for path in _iter_py_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        guarded = _guarded_linenos(tree)
        marked = _marked_linenos(source.splitlines())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_get_model_call(node):
                continue
            target = _literal_target(node)
            if target is None:
                continue
            if _is_excused(node.lineno, guarded, marked):
                continue
            targets.append(
                {"path": rel, "line": node.lineno, "app": target[0], "model": target[1]}
            )
    return targets


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------
def _resolve(targets: list[dict]) -> list[dict]:
    import django
    from django.apps import apps as dj_apps

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    findings: list[dict] = []
    for t in targets:
        try:
            dj_apps.get_model(t["app"], t["model"])
        except Exception as exc:  # LookupError + any registry edge
            findings.append(
                {
                    "path": t["path"],
                    "line": t["line"],
                    "statement": f'get_model("{t["app"]}", "{t["model"]}")',
                    "error": type(exc).__name__,
                }
            )
    findings.sort(key=lambda i: (i["path"], i["line"], i["statement"]))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every get_model('app','Model') literal must resolve against the "
        "live Django app registry; guard with try/except LookupError or "
        "# get-model-allow: <reason> for intentionally-deferred models",
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
    print(f"get_model integrity: {scanned} literal call(s) checked, {len(findings)} unresolved")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['statement']}  [{f['error']}]")


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
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(i["path"], i["statement"]) for i in baseline.get("findings", [])}
    current_set = {(i["path"], i["statement"]) for i in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    if new:
        print("\nNEW unresolved get_model lookups introduced:")
        for path, statement in sorted(new):
            print(f"  {path}  {statement}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, statement in sorted(removed):
            print(f"  {path}  {statement}")
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
