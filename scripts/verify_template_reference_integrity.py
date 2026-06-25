#!/usr/bin/env python
"""Runtime template-reference integrity verifier.

Third member of the reference-integrity gate family. Its siblings seal *import*
references (``scan_import_reference_integrity``), *dynamic model* lookups
(``verify_get_model_integrity``) and *URL names* (``verify_url_name_integrity``).
This one closes the last literal-string → runtime-registry loophole the family
keeps finding: a **template path literal** passed to ``render`` /
``render_to_string`` / ``TemplateResponse`` / ``get_template`` that names a
template which does not exist.

``audit_template_render_safety`` walks ``templates/**/*.html`` and validates
*template syntax* + ``{% include %}`` / ``{% extends %}`` targets — but it never
sees a Python view that does ``render(request, "reports/renamed.html")`` after
the template was renamed or deleted. That ships green and 500s with
``TemplateDoesNotExist`` the first time the view is hit. A static scan that only
knows about repo templates would also FALSE-POSITIVE on third-party templates
(``admin/base_site.html``, ``rest_framework/api.html``) that live in installed
packages, not the repo.

So this verifier resolves with **ground truth**: it AST-collects every literal
template path in ``apps/`` + ``services/`` + ``config/``, then asks Django's own
loader (``django.template.loader.get_template`` / ``select_template``) whether
each resolves — exactly as runtime would, across project ``DIRS``, ``APP_DIRS``
and installed-app templates. A ``TemplateDoesNotExist`` is a finding.

Call / assignment shapes recognized:

* ``render(request, "x.html", ...)`` — 2nd positional (Django shortcut; gated on
  a literal ``request`` first arg to avoid custom ``.render()`` methods) and the
  ``template_name=`` kwarg.
* ``render_to_string("x.html", ...)`` / ``loader.render_to_string`` — 1st
  positional + ``template_name=`` kwarg.
* ``TemplateResponse(request, "x.html", ...)`` / ``SimpleTemplateResponse`` —
  template positional + ``template=`` kwarg.
* ``get_template("x.html")`` — 1st positional.
* ``select_template(["a.html", "b.html"])`` — list; resolves if ANY member does.
* a list passed where a single template is expected (``render`` /
  ``template_name``) — same "any member resolves" fallback semantics.
* class attribute ``template_name = "x.html"`` / ``template_names = [...]``.

Excused (zero false positives):

* a call inside a ``try/except (TemplateDoesNotExist|Exception|BaseException|bare)``
  block (incl. ``except <NAMED_TUPLE>:`` where the tuple includes a guard
  exception) — a deliberate optional-template / graceful-fallback pattern.
* a ``# template-ref-allow: <reason>`` marker on the line or the line above.
* non-literal args (``render(request, f"{x}.html")``, variables) — unresolvable
  statically, left to runtime.
* migrations and test files.

Requires Django (run in a deps-installed CI job, e.g. ci.yml::django-tests,
after ``manage.py check``). Output mirrors the boundary scanners.
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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-template-reference-integrity.json"

ALLOW_MARKER = "template-ref-allow:"
_GUARD_EXC_NAMES = {"TemplateDoesNotExist", "Exception", "BaseException"}

# Functions whose template argument we resolve, mapped to the positional index
# of the template path (``None`` = the call is handled specially / kwarg-only).
_RENDER_FUNCS = {
    "render": 1,            # render(request, template, context)
    "render_to_string": 0,  # render_to_string(template, context)
    "render_to_response": 0,
    "get_template": 0,
    "select_template": 0,   # list arg
    "TemplateResponse": 1,  # TemplateResponse(request, template, context)
    "SimpleTemplateResponse": 0,  # SimpleTemplateResponse(template, context)
}
# kwarg names that carry a template path on those calls.
_TEMPLATE_KWARGS = {"template_name", "template", "template_names"}

# A literal that "looks like a template path": no whitespace, and either a
# directory separator or a file extension. Keeps arbitrary string args out.
_TEMPLATEISH = re.compile(r"^[^\s]+(?:/[^\s]+)*\.[A-Za-z0-9]{1,6}$")


def _looks_like_template(value: str) -> bool:
    return bool(value) and bool(_TEMPLATEISH.match(value))


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
            if "migrations" in parts:
                continue
            if "tests" in parts or path.name.startswith("test_"):
                continue
            yield path


def _str_const(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _str_list(node) -> list[str] | None:
    """Return a list of string literals if node is a list/tuple of str consts."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out: list[str] = []
    for elt in node.elts:
        s = _str_const(elt)
        if s is None:
            return None  # mixed / non-literal — not statically resolvable
        out.append(s)
    return out


def _templates_from_node(node) -> tuple[list[str], str] | None:
    """Resolve a node to (template_list, mode). mode 'single' must all resolve;
    'any' (a list) resolves if at least one does. Returns None if not literal."""
    single = _str_const(node)
    if single is not None:
        return ([single], "single") if _looks_like_template(single) else None
    lst = _str_list(node)
    if lst is not None:
        keep = [s for s in lst if _looks_like_template(s)]
        return (keep, "any") if keep else None
    return None


def _is_render_shortcut(call: ast.Call) -> bool:
    """``render(request, ...)`` Django shortcut — gate on a literal ``request``
    first arg so custom ``obj.render(...)`` methods are not misread."""
    if not call.args:
        return False
    first = call.args[0]
    return isinstance(first, ast.Name) and first.id == "request"


def _collect_from_call(call: ast.Call) -> tuple[list[str], str] | None:
    fn = call.func
    name = getattr(fn, "attr", None) or getattr(fn, "id", None)
    if name not in _RENDER_FUNCS:
        return None
    if name == "render" and not _is_render_shortcut(call):
        return None
    idx = _RENDER_FUNCS[name]
    # positional template argument
    if idx is not None and len(call.args) > idx:
        got = _templates_from_node(call.args[idx])
        if got is not None:
            return got
    # kwarg template argument
    for kw in call.keywords:
        if kw.arg in _TEMPLATE_KWARGS:
            got = _templates_from_node(kw.value)
            if got is not None:
                return got
    return None


def _collect_from_assign(node: ast.Assign) -> tuple[list[str], str] | None:
    """class-body ``template_name = "x.html"`` / ``template_names = [...]``."""
    targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
    if not any(t in {"template_name", "template_names"} for t in targets):
        return None
    return _templates_from_node(node.value)


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
            got = None
            if isinstance(node, ast.Call):
                got = _collect_from_call(node)
            elif isinstance(node, ast.Assign):
                got = _collect_from_assign(node)
            if got is None:
                continue
            templates, mode = got
            if _is_excused(node.lineno, guarded, marked):
                continue
            targets.append(
                {"path": rel, "line": node.lineno, "templates": templates, "mode": mode}
            )
    return targets


# --------------------------------------------------------------------------
# Runtime resolution
# --------------------------------------------------------------------------
def _resolve(targets: list[dict]) -> list[dict]:
    import django
    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    def exists(name: str) -> bool:
        try:
            get_template(name)
            return True
        except TemplateDoesNotExist:
            return False
        except Exception:  # malformed template still "exists" — syntax is another gate's job
            return True

    findings: list[dict] = []
    for t in targets:
        names = t["templates"]
        if t["mode"] == "any":
            # select_template-style fallback list: OK if any resolves.
            missing = [] if any(exists(n) for n in names) else list(names)
        else:
            missing = [n for n in names if not exists(n)]
        if missing:
            findings.append(
                {
                    "path": t["path"],
                    "line": t["line"],
                    "templates": missing,
                    "mode": t["mode"],
                }
            )
    findings.sort(key=lambda i: (i["path"], i["line"], ",".join(i["templates"])))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every literal template path passed to render/render_to_string/"
        "TemplateResponse/get_template/select_template (or assigned to "
        "template_name[s]) must resolve via Django's loader; guard with "
        "try/except TemplateDoesNotExist or # template-ref-allow: <reason>",
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


def _key(f: dict) -> tuple[str, str]:
    return (f["path"], ",".join(sorted(f["templates"])))


def _print_summary(findings: list[dict], scanned: int) -> None:
    print(f"template-reference integrity: {scanned} literal target(s) checked, "
          f"{len(findings)} unresolved")
    for f in findings:
        joined = " | ".join(f["templates"])
        print(f"  {f['path']}:{f['line']}  {joined}  [TemplateDoesNotExist]")


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
    baseline_set = {_key(i) for i in baseline.get("findings", [])}
    current_set = {_key(i) for i in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    if new:
        print("\nNEW unresolved template references introduced:")
        for path, templates in sorted(new):
            print(f"  {path}  {templates}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, templates in sorted(removed):
            print(f"  {path}  {templates}")
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
