#!/usr/bin/env python
"""Runtime ORM relation-path integrity verifier (reference-integrity family).

Sibling to the import / get_model / url-name / template / settings / **field**
reference gates. The field gate (`verify_field_reference_integrity.py`) seals
literal field names passed to `.order_by`/`.values`/`.only`/`.defer`/... but it
DELIBERATELY skips relation-traversal methods. This one closes that documented
gap: a literal **relation path** passed to `.select_related("x")` /
`.prefetch_related("x__y")` where the first segment names no field/relation on
the head model becomes an uncaught `FieldError` ("Cannot resolve keyword 'x'
into field") the first time the queryset is evaluated. AST cannot prove a
relation exists; the model's `_meta` is ground truth.

`select_related`/`prefetch_related` are SEPARATE from the field gate's method
set precisely because their args are *relation* paths (forward FK/O2O for
`select_related`; forward M2M + reverse relations + `GenericRelation` for
`prefetch_related`), and the first `__` segment must resolve as a field/relation
on the head model — exactly the `_meta.get_field` question, same silent-500
failure mode.

Introduction caught a REAL bug: `apps/reports/management/commands/
generate_regional_reports.py` did `Evaluation.objects.filter(...).select_related(
"component", "subject")` — `evals.Evaluation` has NEITHER field (its relation is
`subject_assignment` → `SubjectAssignment.subject`), so the canonical
`generate_regional_reports` command crashed with `FieldError` the moment its
queryset evaluated; every other reference-integrity gate missed it (the import
gate sees `Evaluation` resolves; the field gate skips `select_related`). Fixed
to `.select_related("subject_assignment__subject")` (+ `eval.subject_assignment
.subject` / `eval.final_score` reads), driving the baseline to 0.

Deliberately conservative — biased hard toward false-NEGATIVES so it can be a
zero-tolerance gate without ever reddening CI on a clean tree:

* Methods checked (positional string args only): `select_related` /
  `prefetch_related`. `Prefetch(...)` objects and `F()` are not string literals
  so they are never seen (skipped).
* The chain head must be `<Name>.objects` where `<Name>` is Capitalised (a model
  class) and resolves to exactly ONE registered model by class name. 0 / >1
  (name collision across apps) -> skipped, not guessed.
* Any chain containing `annotate` / `alias` / `extra` / `raw` / `union` /
  `intersection` / `difference` is skipped — those introduce pseudo-fields.
* Each literal is normalised before lookup: only the FIRST `__` segment (the
  relation on THIS model) is checked, so deep traversals (`a__b__c`) and
  the `"pk"` sentinel never false-positive. v1 checks NAME existence only
  (`get_field` does not raise `FieldDoesNotExist`); proving the segment is a
  *relation* rather than a scalar — and chasing the tail across models — is
  deferred (GenericForeignKey / private-field edges keep that FP-prone).
* Only a `FieldDoesNotExist` is a finding; any other lookup error (registry
  edge) is swallowed (false-negative bias).
* Excused: a call inside `try/except (FieldError|FieldDoesNotExist|Exception|
  BaseException|bare)` and a `# relation-path-allow: <reason>` marker on the
  call's line or the line above. Migrations + test files skipped.

Requires Django (run in ci.yml::django-tests after the field-reference step).
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
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-relation-path-integrity.json"
)

ALLOW_MARKER = "relation-path-allow:"
_GUARD_EXC_NAMES = {
    "FieldError",
    "FieldDoesNotExist",
    "Exception",
    "BaseException",
}

# Queryset methods whose positional string args name a relation path on the head
# model. The field-reference gate intentionally excludes these (relation-, not
# scalar-field, resolution); this gate owns them.
_RELATION_METHODS = {"select_related", "prefetch_related"}

# Methods that introduce pseudo-fields (annotations/aliases) into the field
# namespace, or otherwise make resolution ambiguous -> skip the whole chain.
_AMBIGUOUS_METHODS = {
    "annotate",
    "alias",
    "extra",
    "raw",
    "union",
    "intersection",
    "difference",
}

# Literal args that are always valid / special and must never be flagged.
_SKIP_LITERALS = {"pk"}


# --------------------------------------------------------------------------
# Guard / marker awareness (mirrors verify_field_reference_integrity)
# --------------------------------------------------------------------------
def _exception_tuple_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.Tuple, ast.List)
        ):
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


def _resolve_model_head(receiver: ast.AST) -> str | None:
    """Walk a queryset receiver chain to its head.

    Returns the model class name if the chain is ``<Capitalised Name>.objects`` with
    only non-ambiguous queryset methods in between, else None (skip / unresolvable).
    """
    cur = receiver
    while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
        method = cur.func.attr
        if method in _AMBIGUOUS_METHODS:
            return None
        cur = cur.func.value
    # After unwinding the call chain, the head must be ``<Name>.objects``.
    if (
        isinstance(cur, ast.Attribute)
        and cur.attr == "objects"
        and isinstance(cur.value, ast.Name)
    ):
        name = cur.value.id
        if name[:1].isupper():
            return name
    return None


def _relation_literals(call: ast.Call) -> list[str]:
    """First-segment relation names from the positional string args of the call."""
    out: list[str] = []
    for arg in call.args:
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        raw = arg.value.strip()
        if not raw or raw in _SKIP_LITERALS:
            continue
        first = raw.split("__", 1)[0]
        if not first or first in _SKIP_LITERALS:
            continue
        out.append(first)
    return out


def _collect_targets() -> list[dict]:
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
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            if node.func.attr not in _RELATION_METHODS:
                continue
            model = _resolve_model_head(node.func.value)
            if model is None:
                continue
            if _is_excused(node.lineno, guarded, marked):
                continue
            for field in _relation_literals(node):
                targets.append(
                    {
                        "path": rel,
                        "line": node.lineno,
                        "model": model,
                        "field": field,
                        "method": node.func.attr,
                    }
                )
    return targets


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------
def _resolve(targets: list[dict]) -> list[dict]:
    import django

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.apps import apps as dj_apps
    from django.core.exceptions import FieldDoesNotExist

    # Map class name -> model, skipping ambiguous (collision) names entirely.
    by_name: dict[str, object] = {}
    ambiguous: set[str] = set()
    for model in dj_apps.get_models():
        nm = model.__name__
        if nm in by_name:
            ambiguous.add(nm)
        by_name[nm] = model
    for nm in ambiguous:
        by_name.pop(nm, None)

    findings: list[dict] = []
    for t in targets:
        model = by_name.get(t["model"])
        if model is None:
            # Unknown or name-collision model head -> not statically resolvable.
            continue
        try:
            model._meta.get_field(t["field"])
        except FieldDoesNotExist:
            findings.append(
                {
                    "path": t["path"],
                    "line": t["line"],
                    "statement": f'{t["model"]}.objects...{t["method"]}("{t["field"]}")',
                    "error": "FieldDoesNotExist",
                }
            )
        except Exception:  # registry edge — never a finding (false-negative bias)
            continue
    findings.sort(key=lambda i: (i["path"], i["line"], i["statement"]))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every literal relation path passed to .select_related/"
        ".prefetch_related on a directly-resolvable <Model>.objects chain must "
        "have its first segment resolve via the model's _meta.get_field; guard "
        "with try/except FieldError or # relation-path-allow: <reason>",
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
        f"relation-path integrity: {scanned} literal relation ref(s) checked, "
        f"{len(findings)} unresolved"
    )
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
        print("\nNEW unresolved relation references introduced:")
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
