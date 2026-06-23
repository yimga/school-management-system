#!/usr/bin/env python
"""Runtime URL-name integrity verifier.

Seals the ``NoReverseMatch`` loophole: a ``reverse("foo:bar")`` /
``reverse_lazy(...)`` / ``{% url "foo:bar" %}`` naming a route that does not
exist. At runtime that is an uncaught ``NoReverseMatch`` — a 500 on the page
that renders the link, or a crashed redirect. For a school platform where
every dashboard is a web of cross-links, a renamed/removed URL pattern that
leaves a stale reference behind is a direct production outage.

Ground truth comes from Django's own resolver, so there are no false
positives from incomplete static knowledge:

* membership fast-path — the name is in the resolver's complete registered-name
  set (built by recursively walking ``reverse_dict`` + ``namespace_dict``); OR
* authoritative fallback — ``reverse(name)`` is attempted and the
  ``NoReverseMatch`` message is classified. Django says *"... is not a valid
  view function or pattern name"* for an unknown name (→ finding) versus
  *"... with arguments ... not found / pattern(s) tried"* for a **known** name
  that merely needs URL args (→ NOT a finding). So a parameterized route
  referenced without args never false-positives.

Reference shapes checked:

* Python (``apps/`` + ``services/``): ``reverse("name")`` / ``reverse_lazy("name")``
  with a string-literal first argument (bare / ``urls.reverse`` / ``django.urls``).
* Templates (``templates/**/*.html``): ``{% url "name" ... %}`` / ``{% url 'name' ... %}``
  with a quoted-literal first argument.

Intentionally NOT covered (avoids ambiguity / false positives):

* ``redirect(...)`` — its argument may be a URL path, a view name, OR a model
  instance; classifying it would risk false positives. Left to runtime.
* ``{% url variable %}`` / ``reverse(variable)`` — non-literal, unresolvable
  statically.

Excused:

* a ``reverse`` call inside ``try/except (NoReverseMatch|Exception|
  BaseException|bare|named-tuple-guard)``.
* a ``# url-name-allow: <reason>`` marker (Python: on the call line / line
  above; template: anywhere on the ``{% url %}`` line, incl. ``{# url-name-allow #}``).
* migrations + test files.

Requires Django (run in a deps-installed CI job, e.g. ci.yml::django-tests).
Output mirrors the boundary scanners.
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
APPS_DIR = REPO_ROOT / "apps"
TEMPLATES_DIR = REPO_ROOT / "templates"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-url-name-integrity.json"

ALLOW_MARKER = "url-name-allow:"
_GUARD_EXC_NAMES = {"NoReverseMatch", "Resolver404", "Exception", "BaseException"}
_REVERSE_FUNCS = {"reverse", "reverse_lazy"}
# {% url "name" ... %} / {% url 'name' ... %} — quoted literal first arg only.
_URL_TAG_RE = re.compile(r"\{%\s*url\s+(\"([^\"]+)\"|'([^']+)')")


# --------------------------------------------------------------------------
# Guard / marker awareness (mirrors the other reference-integrity gates)
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
            if "migrations" in parts or "tests" in parts or path.name.startswith("test_"):
                continue
            yield path


def _is_reverse_call(call: ast.Call) -> bool:
    name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
    return name in _REVERSE_FUNCS


def _literal_first_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _collect_python() -> list[dict]:
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
            if not isinstance(node, ast.Call) or not _is_reverse_call(node):
                continue
            name = _literal_first_arg(node)
            if name is None:
                continue
            if _is_excused(node.lineno, guarded, marked):
                continue
            targets.append({"path": rel, "line": node.lineno, "name": name, "via": "reverse"})
    return targets


def _collect_templates() -> list[dict]:
    targets: list[dict] = []
    if not TEMPLATES_DIR.exists():
        return targets
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, start=1):
            if ALLOW_MARKER in line:
                continue
            for m in _URL_TAG_RE.finditer(line):
                name = m.group(2) if m.group(2) is not None else m.group(3)
                if name:
                    targets.append({"path": rel, "line": i, "name": name, "via": "template"})
    return targets


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------
def _registered_names(resolver, prefix: str = "") -> set[str]:
    names: set[str] = set()
    try:
        reverse_dict = resolver.reverse_dict
    except Exception:
        reverse_dict = {}
    for key in reverse_dict.keys():
        if isinstance(key, str):
            names.add(prefix + key)
    for ns, entry in (getattr(resolver, "namespace_dict", {}) or {}).items():
        sub = entry[1]
        names |= _registered_names(sub, prefix + ns + ":")
    return names


def _resolve(targets: list[dict]) -> list[dict]:
    import django
    from django.urls import get_resolver, reverse, NoReverseMatch

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    valid = _registered_names(get_resolver())

    findings: list[dict] = []
    for t in targets:
        name = t["name"]
        if name in valid:
            continue
        # Authoritative fallback: distinguish unknown-name from needs-args.
        try:
            reverse(name)
            continue  # resolved without args -> valid
        except NoReverseMatch as exc:
            if "is not a valid view function or pattern name" not in str(exc):
                continue  # known name, just needs args -> NOT a finding
        except Exception:
            continue  # any other error: don't flag a name on it
        findings.append(
            {
                "path": t["path"],
                "line": t["line"],
                "statement": (
                    f'{{% url "{name}" %}}' if t["via"] == "template" else f'reverse("{name}")'
                ),
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
        "rule": "every literal reverse()/reverse_lazy()/{% url %} name must resolve "
        "against the live URL resolver; guard with try/except NoReverseMatch or "
        "# url-name-allow: <reason>",
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
    print(f"URL-name integrity: {scanned} literal reference(s) checked, {len(findings)} unresolved")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  {f['statement']}")


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
        print("\nNEW unresolved URL names introduced:")
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

    targets = _collect_python() + _collect_templates()
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
