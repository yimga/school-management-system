#!/usr/bin/env python
"""Import-reference integrity scanner.

Seals the class of bug this platform repeatedly shipped: an import that
names a module or symbol which does **not** exist — a wrong-module import
(``from apps.academics.models import Schedule`` when ``Schedule`` lives in
``academics.scheduling``), a renamed/moved symbol, or an absent module.
At runtime these surface as an uncaught ``ImportError`` (→ 500 on a routed
view) or — far worse — get **swallowed** by a broad ``except`` block so a
counter/list silently pins to 0/empty forever and nobody notices.

The fix is to make the loophole impossible to reintroduce: a zero-tolerance
CI gate that statically resolves every ``apps.*`` reference against the
filesystem + AST, with no runtime/Django dependency (so it runs in the same
deps-free CI job as the other architectural-boundary scanners).

Reference paths checked (the paths a phantom can hide in, statically):

1. ``from apps.A.B import name``  — module must resolve AND ``name`` must be
   defined in it (or be a submodule of it).
2. ``import apps.A.B``            — the module must resolve.
3. ``from .x import name`` / ``from . import x`` (relative) — resolved to
   its absolute ``apps.*`` form, then checked as (1)/(2).
4. ``importlib.import_module("apps.A.B")`` / ``__import__("apps.A.B")``
   string-literal calls — the module must resolve.

What is intentionally NOT flagged (so the gate has zero false positives):

* Any import inside a ``try: … except (ImportError|ModuleNotFoundError|
  Exception|BaseException|bare): …`` block. A guarded import that can't
  resolve is a deliberate optional-dependency / graceful-degrade pattern,
  not a loophole.
* Any import carrying a ``# import-ref-allow: <reason>`` marker on its own
  line or the line above (e.g. a verified schema-decision deferral whose
  target model does not exist yet).
* Symbol-level checks are skipped when the target module re-exports via
  ``from x import *`` or defines a module-level ``__getattr__`` (PEP 562) —
  in those cases the symbol cannot be proven absent statically.
* Test files and migrations (migrations have their own gate).

Symbol collection deliberately over-collects (walks the entire target tree,
including names bound inside functions/conditionals/``TYPE_CHECKING``). That
biases the scanner toward false **negatives**, never false positives — the
only acceptable direction for a zero-tolerance gate.

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
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-import-reference-integrity.json"

ALLOW_MARKER = "import-ref-allow:"
_GUARD_EXC_NAMES = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}

# Caches: dotted-module -> resolved Path|None and -> collected-symbol info.
_module_file_cache: dict[str, Path | None] = {}
_module_symbols_cache: dict[str, tuple[set[str], bool]] = {}


# --------------------------------------------------------------------------
# Filesystem / AST module resolution
# --------------------------------------------------------------------------
def _module_file(dotted: str) -> Path | None:
    """Resolve ``apps.a.b`` to its module file/dir, or None if absent.

    Resolution order: ``apps/a/b/__init__.py`` (regular package) →
    ``apps/a/b.py`` (module) → ``apps/a/b/`` (PEP 420 namespace package, a
    directory with no ``__init__.py`` — valid and widely used, e.g.
    ``apps/api/``). Returning the directory keeps namespace-package imports
    from being false-flagged; symbol resolution treats it as opaque.
    """
    if dotted in _module_file_cache:
        return _module_file_cache[dotted]
    parts = dotted.split(".")
    base = REPO_ROOT.joinpath(*parts)
    result: Path | None = None
    pkg_init = base / "__init__.py"
    mod_py = base.with_suffix(".py")
    if pkg_init.exists():
        result = pkg_init
    elif mod_py.exists():
        result = mod_py
    elif base.is_dir():
        result = base  # PEP 420 namespace package
    _module_file_cache[dotted] = result
    return result


def _is_submodule(parent_dotted: str, name: str) -> bool:
    """True when ``parent.name`` resolves to a module file (e.g. a package's
    submodule imported via ``from pkg import submod``)."""
    return _module_file(f"{parent_dotted}.{name}") is not None


def _module_symbols(dotted: str) -> tuple[set[str], bool]:
    """Return (names defined in the module, opaque?).

    ``opaque`` is True when the module re-exports via ``import *`` or defines
    a module-level ``__getattr__`` — meaning we cannot prove a symbol absent.
    """
    if dotted in _module_symbols_cache:
        return _module_symbols_cache[dotted]
    path = _module_file(dotted)
    names: set[str] = set()
    opaque = False
    if path is None or path.is_dir():
        # unknown module, or PEP 420 namespace package (no __init__ to parse)
        _module_symbols_cache[dotted] = (names, True)
        return names, True
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, UnicodeDecodeError):
        _module_symbols_cache[dotted] = (names, True)
        return names, True
    for node in ast.walk(tree):
        # Dynamic re-export via globals().update(...) (e.g. a package __init__
        # that injects a shadowed legacy module's names) is invisible to AST —
        # treat any globals() use as opaque so we never false-flag such names.
        if isinstance(node, ast.Name) and node.id == "globals":
            opaque = True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if node.name == "__getattr__":
                opaque = True
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                _collect_assign_names(tgt, names)
        elif isinstance(node, ast.AnnAssign):
            _collect_assign_names(node.target, names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    opaque = True
                else:
                    names.add(a.asname or a.name)
    _module_symbols_cache[dotted] = (names, opaque)
    return names, opaque


def _collect_assign_names(target: ast.AST, names: set[str]) -> None:
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_assign_names(elt, names)


def _resolve_relative(file_path: Path, level: int, module: str | None) -> str | None:
    """Resolve a relative import to its absolute ``apps.*`` dotted form.

    ``file_path`` is the importing file. For both ``__init__.py`` and a plain
    module file, the anchoring package is the directory the file lives in.
    """
    try:
        rel = file_path.relative_to(REPO_ROOT)
    except ValueError:
        return None
    pkg_parts = list(rel.parts[:-1])  # directory containing the file
    if level < 1:
        return None
    # level 1 = current package; each extra level climbs one parent.
    anchor = pkg_parts[: len(pkg_parts) - (level - 1)]
    if not anchor or anchor[0] != "apps":
        return None  # only resolve relatives that land back inside apps/
    dotted = list(anchor)
    if module:
        dotted += module.split(".")
    return ".".join(dotted) if dotted else None


# --------------------------------------------------------------------------
# Guard / marker awareness
# --------------------------------------------------------------------------
def _exception_tuple_aliases(tree: ast.AST) -> set[str]:
    """Module-level names bound to an exception tuple that includes a guard
    exception, e.g. ``_GATE_SOFT_FAILURES = (ImportError, AttributeError, …)``.

    Lets ``except _GATE_SOFT_FAILURES:`` be recognized as ImportError-tolerant
    (the idiomatic 'soft-failure' guard used across this codebase) without the
    developer having to add a marker.
    """
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
    """Line numbers of statements inside an ImportError-tolerant try-body."""
    guarded: set[int] = set()
    tuple_aliases = _exception_tuple_aliases(tree)

    def handler_catches(handlers: list[ast.ExceptHandler]) -> bool:
        for h in handlers:
            if h.type is None:  # bare except
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
    """1-based line numbers carrying the allow marker."""
    return {i + 1 for i, line in enumerate(source_lines) if ALLOW_MARKER in line}


def _is_excused(lineno: int, guarded: set[int], marked: set[int]) -> bool:
    # marker on the import line OR the line directly above it
    return lineno in guarded or lineno in marked or (lineno - 1) in marked


# --------------------------------------------------------------------------
# File scanning
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


def _literal_module_arg(call: ast.Call) -> str | None:
    fn = call.func
    name = getattr(fn, "id", None) or getattr(fn, "attr", None)
    if name not in ("import_module", "__import__"):
        return None
    if not call.args:
        return None
    a0 = call.args[0]
    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
        return a0.value
    return None


def _scan_file(path: Path) -> list[dict]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []
    guarded = _guarded_linenos(tree)
    marked = _marked_linenos(source.splitlines())
    findings: list[dict] = []

    def add(lineno: int, statement: str, kind: str) -> None:
        if _is_excused(lineno, guarded, marked):
            return
        findings.append({"path": rel, "line": lineno, "statement": statement, "kind": kind})

    for node in ast.walk(tree):
        # 1. import apps.A.B
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("apps.") and _module_file(a.name) is None:
                    add(node.lineno, f"import {a.name}", "absent-module")

        # 2/3. from apps.A.B import x   /   from .x import y
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                dotted = _resolve_relative(path, node.level, node.module)
                if dotted is None or not dotted.startswith("apps"):
                    continue
            elif node.module and node.module.startswith("apps."):
                dotted = node.module
            else:
                continue

            if _module_file(dotted) is None:
                stmt = f"from {'.' * (node.level or 0)}{node.module or ''} import ..."
                add(node.lineno, f"{stmt}  [-> {dotted}]", "absent-module")
                continue
            defined, opaque = _module_symbols(dotted)
            if opaque:
                continue
            for a in node.names:
                if a.name == "*":
                    continue
                if a.name in defined:
                    continue
                if _is_submodule(dotted, a.name):
                    continue
                add(node.lineno, f"from {dotted} import {a.name}", "absent-symbol")

        # 4. import_module("apps.A.B") / __import__("apps.A.B")
        elif isinstance(node, ast.Call):
            modlit = _literal_module_arg(node)
            if modlit and modlit.startswith("apps.") and _module_file(modlit) is None:
                add(node.lineno, f"import_module({modlit!r})", "absent-module")

    return findings


def _scan() -> list[dict]:
    findings: list[dict] = []
    for path in _iter_py_files():
        findings.extend(_scan_file(path))
    findings.sort(key=lambda i: (i["path"], i["line"], i["statement"]))
    return findings


# --------------------------------------------------------------------------
# Baseline / CLI (mirrors the other boundary scanners)
# --------------------------------------------------------------------------
def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "every apps.* import (absolute, relative, dynamic-literal) must "
        "resolve to a real module + symbol; guard with try/except ImportError or "
        "# import-ref-allow: <reason> for intentional optional/deferred targets",
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
    print(f"Import-reference integrity scan: {len(findings)} unresolved reference(s)")
    for f in findings:
        print(f"  {f['path']}:{f['line']}  [{f['kind']}]  {f['statement']}")


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
    baseline_set = {(i["path"], i["statement"]) for i in baseline.get("findings", [])}
    current_set = {(i["path"], i["statement"]) for i in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW unresolved import references introduced:")
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
