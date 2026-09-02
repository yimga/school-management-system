"""Which tenant models does a Migration Cloud import actually write, and which of
those can ever reach the cloud?

    python scripts/audit_lander_write_reachability.py
    python scripts/audit_lander_write_reachability.py --json
    python scripts/audit_lander_write_reachability.py --check-declaration
    python scripts/audit_lander_write_reachability.py --self-test

WHY THIS EXISTS
---------------
``apps/sync_engine/management/commands/edge_rail_coverage.py`` answers "what does the
rail carry" (17 entities) and "what does it not" (353 tenant-scoped models). That is
architecture. The question an operator standing in front of a box actually has is
narrower and much sharper:

    I am about to import this school's history. Which of it can never leave?

Answering that needs the OTHER half: what the landers write. A grep for
``Model.objects.create`` answers it wrongly and reassuringly. The dominant idiom in
this package is::

    from apps.schoolops.models import Route
    ...
    upsert_with_conflict_detection(ctx=ctx, domain="transport", model=Route, ...)

``Route`` never appears next to ``.objects.create``, so a pattern scan of the landers
reports the transport lander writes NOTHING. Every first-class lander shipped since
v3.26 uses that helper. A scan that misses them is not a lower bound with a small
error -- it is a scan that mostly returns silence. Measured here: a
``.objects.<write>``-only pass over the same tree resolves 21 models; the full
resolution finds 38.

WHAT THIS DOES INSTEAD
----------------------
An inter-procedural AST resolution over the lander package, ``_helpers.py`` and the
orchestrator's residual-capture net. Five things have to work together, because the
landers use all five:

  1. **Model-name binding.** Any name bound to a Django model, at module scope or
     inside a function: ``from apps.X.models import Y`` (resolved through the LIVE app
     registry, so a re-exported model still lands on its real label),
     ``apps.get_model("x", "Y")``, ``get_user_model()``, plain aliasing.

  2. **Direct writes.** ``<model>.objects.create / get_or_create / update_or_create /
     bulk_create / bulk_update / update / delete``, queryset-tail ``.update()`` /
     ``.delete()``, and ``<instance>.save()``.

  3. **Writes through a helper's parameter.** Each function gets a SUMMARY: the models
     it writes outright, plus the PARAMETERS it writes through.
     ``upsert_with_conflict_detection`` summarises as "writes whatever arrives as
     ``model``"; ``save_scoped`` as "writes whatever arrives as ``obj``". Call sites
     bind those parameters to the caller's own names and the whole thing runs to a
     fixed point. This is what finds ``Route``.

  4. **Models carried through a tuple.** ``structure_lander`` hands SEVEN model classes
     to ``_provision_row`` as one ``models=(AcademicYear, Term, ...)`` argument and
     destructures them inside. Without per-element tuple binding the most
     rail-relevant lander in the package resolves to "writes nothing it can name".

  5. **Return types.** ``student = resolve_student(student_model=StudentProfile)``
     followed by ``save_scoped(student, ...)``, and
     ``obj, _, _ = upsert_with_conflict_detection(model=TeacherProfile, ...)`` followed
     by ``_sweep_custom_attributes(obj, ...)``. Summaries therefore also record what a
     function RETURNS -- concretely, or as "whatever arrived as parameter P" -- and
     modules are analysed twice so the second pass has that oracle.

HONESTY
-------
Every write site whose target could not be named is COUNTED and reported. A domain
with unresolved sites is reported as a FLOOR, never as a complete answer -- the same
discipline ``edge_rail_coverage --counts`` uses for tables it cannot read. A total
printed next to a pile of failed reads is not a total.

PROVING THE DETECTOR
--------------------
``--self-test`` plants one synthetic lander exercising every supported idiom and one
that writes nothing, runs the real resolver over them, and asserts the first is fully
reported and the second reports nothing of its own. A scan that has never been shown
capable of a non-zero answer is indistinguishable from a broken scan, and this repo
has shipped exactly that.

OUTPUT
------
Human table by domain, or ``--json``. ``--check-declaration`` compares the resolved
answer against ``apps.migration_cloud.landers.write_targets.DOMAIN_WRITE_TARGETS`` --
the table the runtime guard reads -- and exits non-zero on drift, so the declaration
cannot rot while the landers move underneath it.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --- Write vocabulary -------------------------------------------------------
# Manager methods that mutate.
MANAGER_WRITE_METHODS = frozenset({
    "create", "get_or_create", "update_or_create", "bulk_create", "bulk_update",
    "acreate", "aget_or_create", "aupdate_or_create", "abulk_create",
})
# Called on a queryset tail (``Model.objects.filter(...).update(...)``) as well as on
# the manager itself. ``update``/``delete`` count: a lander that rewrites an existing
# row still puts state on this box that the rail may not be able to carry away.
QUERYSET_WRITE_METHODS = frozenset({"update", "delete", "aupdate", "adelete"})
INSTANCE_WRITE_METHODS = frozenset({"save", "asave", "delete", "adelete"})

MANAGER_ATTRS = frozenset({"objects", "_base_manager", "_default_manager", "all_objects"})
# Queryset methods that hand back a MODEL INSTANCE -- the binding for ``obj.save()``.
QUERYSET_INSTANCE_METHODS = frozenset({"first", "last", "get", "create", "earliest", "latest"})
# Manager/queryset methods that hand back another queryset.
QUERYSET_CHAIN_METHODS = frozenset({
    "filter", "exclude", "all", "select_related", "prefetch_related", "order_by",
    "annotate", "distinct", "using", "only", "defer", "select_for_update", "none",
})

# An origin is ("label", "app.Model") -- a model we can name -- or ("param", slot),
# where slot is a parameter name, optionally ``name#index`` for one element of a tuple
# the caller built.
LABEL = "label"
PARAM = "param"


class Unresolved:
    """A write whose target this resolver could not name. Counted, never ignored."""

    __slots__ = ("where", "detail")

    def __init__(self, where: str, detail: str) -> None:
        self.where = where
        self.detail = detail

    def as_dict(self) -> dict:
        return {"where": self.where, "detail": self.detail}


# --- Model index ------------------------------------------------------------

def build_model_index() -> dict:
    """Maps for turning a source-level name into an ``app_label.ModelName``.

    Uses the LIVE app registry so ``from apps.people.models import StudentProfile``
    resolves even when the class lives in ``apps.people.models_students`` and is only
    re-exported -- which several apps here do.
    """
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.apps import apps as dj_apps
    from django.conf import settings

    by_name: dict[str, set[str]] = {}
    by_app_and_name: dict[tuple[str, str], str] = {}
    for model in dj_apps.get_models(include_auto_created=True):
        by_name.setdefault(model.__name__, set()).add(model._meta.label)
        by_app_and_name[(model._meta.app_label, model.__name__)] = model._meta.label

    module_to_label = {cfg.name: cfg.label for cfg in dj_apps.get_app_configs()}
    return {
        "by_name": by_name,
        "by_app_and_name": by_app_and_name,
        "module_to_app_label": module_to_label,
        "auth_user_model": settings.AUTH_USER_MODEL,
    }


def resolve_import(index: dict, module: str, name: str) -> str | None:
    """``("apps.schoolops.models", "Route")`` -> ``"schoolops.Route"``."""
    module = module or ""
    best_label, best_len = None, -1
    for app_module, label in index["module_to_app_label"].items():
        if module == app_module or module.startswith(app_module + "."):
            if len(app_module) > best_len:
                best_len, best_label = len(app_module), label
    if best_label is not None:
        hit = index["by_app_and_name"].get((best_label, name))
        if hit:
            return hit
    candidates = index["by_name"].get(name) or set()
    return next(iter(candidates)) if len(candidates) == 1 else None


def resolve_label_pair(index: dict, app_label: str, model_name: str) -> str | None:
    hit = index["by_app_and_name"].get((app_label, model_name))
    if hit:
        return hit
    candidates = index["by_name"].get(model_name) or set()
    return next(iter(candidates)) if len(candidates) == 1 else None


# --- Summaries --------------------------------------------------------------

class FunctionSummary:
    __slots__ = ("key", "params", "positional", "concrete", "param_writes", "calls",
                 "unresolved", "return_labels", "return_params")

    def __init__(self, key: str, params: list[str], positional: list[str]) -> None:
        self.key = key
        self.params = params
        # Parameters a call site may fill POSITIONALLY, in declaration order. Kept
        # apart from ``params`` because this package is overwhelmingly keyword-only
        # and mixing the two mis-binds ``#0``.
        self.positional = positional
        self.concrete: set[str] = set()
        self.param_writes: set[str] = set()
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.unresolved: list[Unresolved] = []
        self.return_labels: set[str] = set()
        self.return_params: set[str] = set()

    def returns(self) -> tuple[set[str], set[str]]:
        return self.return_labels, self.return_params


class ModuleAnalysis:
    __slots__ = ("path", "module", "functions", "imported_funcs", "registered_domains",
                 "module_models", "sweeping_classes")

    def __init__(self, path: Path, module: str) -> None:
        self.path = path
        self.module = module
        self.functions: dict[str, FunctionSummary] = {}
        self.imported_funcs: dict[str, str] = {}
        self.registered_domains: list[tuple[str, str]] = []
        self.module_models: dict[str, str] = {}
        self.sweeping_classes: set[str] = set()


def _chain_root_name(node: ast.AST) -> str | None:
    cur = node
    while True:
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        else:
            break
    return cur.id if isinstance(cur, ast.Name) else None


class _FunctionWalker(ast.NodeVisitor):
    """Collects one function's write sites, bindings, returns and outgoing calls."""

    def __init__(self, analysis: ModuleAnalysis, summary: FunctionSummary,
                 index: dict, inherited_models: dict[str, str],
                 returns_oracle: dict[str, tuple[set[str], set[str]]]) -> None:
        self.a = analysis
        self.s = summary
        self.index = index
        self.oracle = returns_oracle
        self.models: dict[str, str] = dict(inherited_models)
        # local name -> origin, for MODEL CLASSES reached through a parameter
        self.model_origins: dict[str, tuple[str, str]] = {}
        # local name -> origin, for INSTANCES and for QUERYSETS
        self.instances: dict[str, tuple[str, str]] = {}
        self.querysets: dict[str, tuple[str, str]] = {}
        self.params: set[str] = set(summary.params)
        # Function-scope ``from ._helpers import upsert_with_conflict_detection``.
        # Landers import the shared upsert INSIDE ``land()`` as often as at module
        # scope; treating a local import as absent silently dropped the single most
        # common write idiom in the package -- the attendance lander resolved to
        # "writes nothing" while writing every attendance row a school has.
        self.local_funcs: dict[str, str] = {}

    # -- bindings ----------------------------------------------------------
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        target = _absolute_module(self.a.module, node)
        for alias in node.names:
            local = alias.asname or alias.name
            label = resolve_import(self.index, target, alias.name)
            if label:
                self.models[local] = label
            else:
                self.local_funcs[local] = f"{target}:{alias.name}"

    def _model_origin(self, node: ast.AST) -> tuple[str, str] | None:
        """Origin of an expression naming a model CLASS."""
        if isinstance(node, ast.Name):
            if node.id in self.models:
                return (LABEL, self.models[node.id])
            if node.id in self.model_origins:
                return self.model_origins[node.id]
            if node.id in self.params:
                return (PARAM, node.id)
            return None
        if isinstance(node, ast.Call):
            chain = _attr_chain(node.func)
            if chain and chain[-1] == "get_model":
                args = [a for a in node.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                if len(args) >= 2:
                    hit = resolve_label_pair(self.index, args[0].value, args[1].value)
                    return (LABEL, hit) if hit else None
                if len(args) == 1 and "." in args[0].value:
                    app, _, name = args[0].value.partition(".")
                    hit = resolve_label_pair(self.index, app, name)
                    return (LABEL, hit) if hit else None
                return None
            if chain and chain[-1] == "get_user_model":
                app, _, name = self.index["auth_user_model"].partition(".")
                hit = resolve_label_pair(self.index, app.lower(), name)
                return (LABEL, hit) if hit else None
        return None

    def _manager_base(self, node: ast.Call) -> tuple[tuple[str, str] | None, list[str]]:
        """``Model.objects.filter(x).first()`` -> (origin of Model, ["filter","first"])."""
        names: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            names.append(cur.func.attr)
            cur = cur.func.value
        names.reverse()
        # A queryset variable stands in for its model.
        if isinstance(cur, ast.Name) and cur.id in self.querysets:
            return self.querysets[cur.id], names
        while isinstance(cur, ast.Attribute) and cur.attr in MANAGER_ATTRS:
            cur = cur.value
        return self._model_origin(cur), names

    def _instance_origin(self, node: ast.AST) -> tuple[str, str] | None:
        """Origin of an expression producing a model INSTANCE."""
        if isinstance(node, ast.Name):
            if node.id in self.instances:
                return self.instances[node.id]
            if node.id in self.params:
                return (PARAM, node.id)
            return None
        if isinstance(node, ast.Call):
            direct = self._model_origin(node.func)      # ``Model(...)``
            if direct:
                return direct
            base, names = self._manager_base(node)
            if base and names and names[-1] in QUERYSET_INSTANCE_METHODS:
                return base
            return self._call_return_origin(node)
        return None

    def _queryset_origin(self, node: ast.AST) -> tuple[str, str] | None:
        if isinstance(node, ast.Call):
            base, names = self._manager_base(node)
            if base and names and names[-1] in QUERYSET_CHAIN_METHODS:
                return base
        if isinstance(node, ast.Attribute) and node.attr in MANAGER_ATTRS:
            return self._model_origin(node.value)
        return None

    def _call_return_origin(self, node: ast.Call) -> tuple[str, str] | None:
        """What a call to a summarised function hands back."""
        key = self._callee_key(node)
        if key is None:
            return None
        returns = self.oracle.get(key)
        if not returns:
            return None
        labels, param_slots = returns
        if labels:
            return (LABEL, sorted(labels)[0])
        if not param_slots:
            return None
        bindings = self._call_bindings(node)
        for slot in sorted(param_slots):
            token = _slot_token(bindings, slot, self.oracle.get("#positional:" + key))
            if token.startswith(LABEL + ":"):
                return (LABEL, token.split(":", 1)[1])
            if token.startswith(PARAM + ":"):
                return (PARAM, token.split(":", 1)[1])
        return None

    def visit_Assign(self, node: ast.Assign) -> None:
        model_org = self._model_origin(node.value)
        inst_org = self._instance_origin(node.value)
        qs_org = self._queryset_origin(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if model_org:
                    self._bind_model(target.id, model_org)
                if inst_org:
                    self.instances[target.id] = inst_org
                if qs_org:
                    self.querysets[target.id] = qs_org
            elif isinstance(target, (ast.Tuple, ast.List)):
                # ``AcademicYear, Term, ... = models`` where ``models`` is a parameter.
                # The structure lander hands seven model classes through one parameter
                # this way, so without per-element binding the most rail-relevant
                # lander resolves to "writes nothing it can name".
                if isinstance(node.value, ast.Name) and node.value.id in self.params:
                    for idx, elt in enumerate(target.elts):
                        if isinstance(elt, ast.Name):
                            self.model_origins[elt.id] = (PARAM, f"{node.value.id}#{idx}")
                # ``obj, created[, preserved] = <call>`` -- the shared upsert's shape.
                first = target.elts[0] if target.elts else None
                if isinstance(first, ast.Name) and isinstance(node.value, ast.Call):
                    base, names = self._manager_base(node.value)
                    if base and names and names[-1] in ("get_or_create", "update_or_create"):
                        self.instances[first.id] = base
                    else:
                        ret = self._call_return_origin(node.value)
                        if ret:
                            self.instances[first.id] = ret
        self.generic_visit(node)

    def _bind_model(self, name: str, origin: tuple[str, str]) -> None:
        if origin[0] == LABEL:
            self.models[name] = origin[1]
        else:
            self.model_origins[name] = origin

    def visit_Return(self, node: ast.Return) -> None:
        value = node.value
        if value is None:
            return
        # ``return obj, created, preserved`` -- the caller binds the first element.
        if isinstance(value, ast.Tuple) and value.elts:
            value = value.elts[0]
        origin = self._instance_origin(value)
        if origin:
            if origin[0] == LABEL:
                self.s.return_labels.add(origin[1])
            else:
                self.s.return_params.add(origin[1])
        self.generic_visit(node)

    # -- writes ------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        self._record_write(node)
        self._record_outgoing_call(node)
        self.generic_visit(node)

    def _record_write(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        method = node.func.attr
        recv = node.func.value

        if method in MANAGER_WRITE_METHODS or method in QUERYSET_WRITE_METHODS:
            base, _names = self._manager_base(node)
            if base:
                self._add(base)
                return
            if method in MANAGER_WRITE_METHODS or self._looks_like_manager(recv):
                self.s.unresolved.append(Unresolved(
                    self.s.key,
                    f"line {node.lineno}: .{method}() on a receiver this resolver "
                    f"could not name",
                ))
            return

        if method in INSTANCE_WRITE_METHODS:
            origin = self._instance_origin(recv)
            if origin:
                self._add(origin)

    def _add(self, origin: tuple[str, str]) -> None:
        if origin[0] == LABEL:
            self.s.concrete.add(origin[1])
        else:
            self.s.param_writes.add(origin[1])

    def _looks_like_manager(self, recv: ast.AST) -> bool:
        chain = _attr_chain(recv)
        return bool(chain) and any(part in MANAGER_ATTRS for part in chain)

    # -- calls -------------------------------------------------------------
    def _callee_key(self, node: ast.Call) -> str | None:
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            # ``_helpers.persist_dfv_extras(...)`` / ``self._land_one(...)``
            name = node.func.attr
        if not name:
            return None
        return (self.local_funcs.get(name)
                or self.a.imported_funcs.get(name)
                or f"{self.a.module}:{name}")

    def _call_bindings(self, node: ast.Call) -> dict[str, str]:
        bindings: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is not None:
                bindings[kw.arg] = self._token_of(kw.value)
        for pos, arg in enumerate(node.args):
            bindings[f"#{pos}"] = self._token_of(arg)
        return bindings

    def _record_outgoing_call(self, node: ast.Call) -> None:
        key = self._callee_key(node)
        if key is None:
            return
        self.s.calls.append((key, self._call_bindings(node)))

    def _token_of(self, node: ast.AST) -> str:
        if isinstance(node, (ast.Tuple, ast.List)):
            return "tuple:" + "|".join(self._token_of(e) for e in node.elts)
        origin = self._model_origin(node) or self._instance_origin(node)
        if origin:
            return f"{origin[0]}:{origin[1]}"
        root = _chain_root_name(node)
        if root and root in self.params:
            return f"{PARAM}:{root}"
        return "?"


def _attr_chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return parts
    return None


def _module_name_for(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _absolute_module(current: str, node: ast.ImportFrom) -> str:
    """Turn ``from ._helpers import x`` inside ``a.b.c`` into ``a.b._helpers``."""
    if not node.level:
        return node.module or ""
    parts = current.split(".")
    base = ".".join(parts[: max(len(parts) - node.level, 0)])
    return f"{base}.{node.module}" if node.module else base


def _element(token: str, index: int) -> str:
    if not token.startswith("tuple:"):
        return "?"
    parts = token[len("tuple:"):].split("|")
    return parts[index] if index < len(parts) else "?"


def _slot_token(bindings: dict[str, str], slot: str,
                positional: list[str] | None = None) -> str:
    """Resolve ``model`` / ``models#3`` against one call site's arguments."""
    param, _, idx_text = slot.partition("#")
    token = bindings.get(param)
    if token is None and positional:
        try:
            pos = [p for p in positional if p != "self"].index(param)
        except ValueError:
            pos = -1
        if pos >= 0:
            token = bindings.get(f"#{pos}")
    if token is None:
        return "?"
    if idx_text:
        return _element(token, int(idx_text))
    return token


def analyze_module(path: Path, index: dict,
                   returns_oracle: dict[str, tuple[set[str], set[str]]]) -> ModuleAnalysis:
    module = _module_name_for(path)
    analysis = ModuleAnalysis(path, module)
    tree = ast.parse(path.read_bytes().decode("utf-8"), filename=str(path))

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            target = _absolute_module(module, node)
            for alias in node.names:
                local = alias.asname or alias.name
                label = resolve_import(index, target, alias.name)
                if label:
                    analysis.module_models[local] = label
                else:
                    analysis.imported_funcs[local] = f"{target}:{alias.name}"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "register":
                if call.args and isinstance(call.args[0], ast.Constant):
                    cls = ""
                    if len(call.args) > 1 and isinstance(call.args[1], ast.Call):
                        target_fn = call.args[1].func
                        cls = target_fn.id if isinstance(target_fn, ast.Name) else ""
                    analysis.registered_domains.append((call.args[0].value, cls))
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign)
                        and any(isinstance(t, ast.Name)
                                and t.id == "sweeps_custom_columns" for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant)
                        and stmt.value.value is True):
                    analysis.sweeping_classes.add(node.name)

    # A function nested inside another function is NOT given its own summary: the
    # enclosing walker already descends into it, with the enclosing scope's model
    # bindings in hand. Giving it a second, binding-less summary reported its writes
    # as unresolved and pushed a complete domain into the FLOOR bucket.
    nested: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if sub is not node and isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    nested.add(id(sub))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if id(node) in nested:
            continue
        positional = [a.arg for a in node.args.posonlyargs] + [a.arg for a in node.args.args]
        params = list(positional) + [a.arg for a in node.args.kwonlyargs]
        key = f"{module}:{node.name}"
        summary = analysis.functions.get(key)
        if summary is None:
            summary = FunctionSummary(key, params, positional)
            analysis.functions[key] = summary
        else:
            summary.params = sorted(set(summary.params) | set(params))
        walker = _FunctionWalker(analysis, summary, index, analysis.module_models,
                                 returns_oracle)
        for child in node.body:
            walker.visit(child)
    return analysis


def close_over_calls(summaries: dict[str, FunctionSummary], max_passes: int = 12) -> int:
    """Propagate helper writes back to their callers until nothing changes."""
    passes = 0
    for passes in range(1, max_passes + 1):
        changed = False
        for summary in summaries.values():
            for callee_key, bindings in summary.calls:
                callee = summaries.get(callee_key)
                if callee is None:
                    continue
                before = (len(summary.concrete), len(summary.param_writes),
                          len(summary.unresolved))
                summary.concrete |= callee.concrete
                for slot in callee.param_writes:
                    token = _slot_token(bindings, slot, callee.positional)
                    if token.startswith(LABEL + ":"):
                        summary.concrete.add(token.split(":", 1)[1])
                    elif token.startswith(PARAM + ":"):
                        summary.param_writes.add(token.split(":", 1)[1])
                    else:
                        summary.unresolved.append(Unresolved(
                            summary.key,
                            f"calls {callee_key}, which writes through parameter "
                            f"{slot!r}, and the argument could not be named",
                        ))
                after = (len(summary.concrete), len(summary.param_writes),
                         len(summary.unresolved))
                if before != after:
                    changed = True
        if not changed:
            break
    return passes


# --- Domain resolution ------------------------------------------------------

LANDER_DIR = "apps/migration_cloud/landers"
EXTRA_SOURCES = ("apps/migration_cloud/orchestrator.py",)


def _source_paths() -> list[Path]:
    paths = sorted((REPO_ROOT / LANDER_DIR).glob("*.py"))
    paths += [REPO_ROOT / p for p in EXTRA_SOURCES]
    return paths


def resolve(index: dict | None = None) -> dict:
    """The measured answer: domain -> models written, with unresolved sites counted."""
    index = index or build_model_index()
    paths = _source_paths()

    # Pass 1 builds the return-type oracle; pass 2 uses it, so a lander that binds an
    # instance from a helper's return value (``student = resolve_student(...)``) can
    # be followed into its later ``save_scoped(student, ...)``.
    oracle: dict[str, tuple[set[str], set[str]]] = {}
    analyses: list[ModuleAnalysis] = []
    for _ in range(2):
        analyses = [analyze_module(p, index, oracle) for p in paths]
        oracle = {}
        for analysis in analyses:
            for key, summary in analysis.functions.items():
                if summary.return_labels or summary.return_params:
                    oracle[key] = (set(summary.return_labels), set(summary.return_params))
                oracle["#positional:" + key] = summary.positional

    summaries: dict[str, FunctionSummary] = {}
    for analysis in analyses:
        summaries.update(analysis.functions)
    passes = close_over_calls(summaries)

    domains: dict[str, dict] = {}
    for analysis in analyses:
        if not analysis.registered_domains:
            continue
        module_concrete: set[str] = set()
        module_unresolved: list[Unresolved] = []
        for summary in analysis.functions.values():
            module_concrete |= summary.concrete
            module_unresolved.extend(summary.unresolved)
        for domain, _cls in analysis.registered_domains:
            entry = domains.setdefault(domain, {"models": set(), "unresolved": [],
                                                "modules": []})
            entry["models"] |= module_concrete
            entry["unresolved"].extend(u.as_dict() for u in module_unresolved)
            entry["modules"].append(analysis.module)

    # The residual-capture net runs behind EVERY lander that does not sweep its own
    # custom columns, and it writes DynamicFieldValue/Definition. That write is not in
    # the lander's own source, so it has to be added here or every domain
    # under-reports the one model they all touch.
    residual = residual_net_models(summaries)
    non_sweeping = non_sweeping_domains(analyses)
    for domain, entry in domains.items():
        if domain in non_sweeping:
            entry["models"] |= residual
            entry["residual_net"] = sorted(residual)
        else:
            entry["residual_net"] = []

    return {
        "domains": {
            d: {
                "models": sorted(v["models"]),
                "unresolved": v["unresolved"],
                "modules": sorted(set(v["modules"])),
                "residual_net": v.get("residual_net", []),
            }
            for d, v in sorted(domains.items())
        },
        "fixed_point_passes": passes,
        "functions_analyzed": len(summaries),
        "files_analyzed": [str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in paths],
    }


def residual_net_models(summaries: dict[str, FunctionSummary]) -> set[str]:
    """What ``_ResidualCapture.flush`` puts on disk behind a non-sweeping lander."""
    summary = summaries.get("apps.migration_cloud.landers._helpers:persist_dfv_extras")
    return set(summary.concrete) if summary else set()


def non_sweeping_domains(analyses: list[ModuleAnalysis]) -> set[str]:
    out: set[str] = set()
    for analysis in analyses:
        for domain, cls in analysis.registered_domains:
            if cls not in analysis.sweeping_classes:
                out.add(domain)
    return out


# --- Rail join --------------------------------------------------------------

def rail_state() -> dict[str, dict]:
    """The rail, from the real resolvers -- NOT ``policy_registry.get_policy``."""
    from apps.sync_engine.management.commands.edge_rail_coverage import _rail_state

    return _rail_state()


def annotate_with_rail(report: dict) -> dict:
    state = rail_state()
    by_label = {facts["model"]: dict(facts, entity=entity)
                for entity, facts in state.items()}
    for entry in report["domains"].values():
        reaches, stranded, held = [], [], []
        for label in entry["models"]:
            facts = by_label.get(label)
            if facts is None:
                stranded.append(label)
            elif facts["insert_held"]:
                held.append(label)
            else:
                reaches.append(label)
        entry["reaches_cloud"] = sorted(reaches)
        entry["insert_held"] = sorted(held)
        entry["stranded"] = sorted(stranded)
        entry["complete"] = not entry["unresolved"]
    report["rail_models"] = sorted(by_label)
    return report


# --- Declaration check ------------------------------------------------------

def check_declaration(report: dict) -> tuple[bool, list[str]]:
    from apps.migration_cloud.landers.write_targets import DOMAIN_WRITE_TARGETS

    problems: list[str] = []
    resolved = {d: set(v["models"]) for d, v in report["domains"].items()}
    declared = {d: set(v) for d, v in DOMAIN_WRITE_TARGETS.items()}
    for domain in sorted(set(resolved) | set(declared)):
        got, want = resolved.get(domain), declared.get(domain)
        if got is None:
            problems.append(f"{domain}: declared in write_targets.py but no lander registers it")
            continue
        if want is None:
            problems.append(
                f"{domain}: a lander registers it but write_targets.py does not declare "
                f"it (writes {sorted(got)})"
            )
            continue
        if got - want:
            problems.append(f"{domain}: resolver found undeclared writes {sorted(got - want)}")
        if want - got:
            problems.append(f"{domain}: declared but not found by the resolver {sorted(want - got)}")
    return (not problems), problems


# --- Self-test --------------------------------------------------------------

_PROBE_WRITER = '''"""Temporary self-test probe. Deleted by the resolver's --self-test."""
from __future__ import annotations

from apps.schoolops.models import Route, LibraryItem, HostelRoom
from apps.people.models import StudentProfile

from ._helpers import (
    get_or_create_named,
    resolve_student,
    save_scoped,
    upsert_with_conflict_detection,
)
from .base import Lander, register


class ProbeLander(Lander):
    domain = "selftest_probe"

    def land(self, *, canonical_rows, ctx):
        from django.apps import apps as dj
        from apps.finance.models import Invoice

        # 1 -- direct manager write
        Route.objects.create(name="x")
        # 2 -- model carried to a helper as a keyword
        upsert_with_conflict_detection(ctx=ctx, domain="selftest_probe",
                                       model=LibraryItem, lookup={}, defaults={})
        # 3 -- a second helper, different parameter shape
        get_or_create_named(model=HostelRoom, school=None, name="n")
        # 4 -- instance produced by a helper's RETURN, written through another helper
        student = resolve_student(ctx=ctx, student_model=StudentProfile,
                                  lookup_field="external_id", external_id="1")
        save_scoped(student, ["first_name"])
        # 5 -- get_model by string
        Evaluation = dj.get_model("evals", "Evaluation")
        Evaluation.objects.update_or_create(defaults={})
        # 6 -- queryset-tail update
        Invoice.objects.filter(pk=1).update(reference="x")
        # 7 -- models carried through a tuple parameter
        self._through_tuple(models=(Route, LibraryItem))
        return None

    def _through_tuple(self, *, models):
        First, Second = models
        First.objects.create(name="a")
        Second.objects.create(title="b")


register("selftest_probe", ProbeLander())
'''

_PROBE_QUIET = '''"""Temporary self-test probe. Deleted by the resolver's --self-test."""
from __future__ import annotations

from .base import Lander, register


class QuietLander(Lander):
    domain = "selftest_quiet"

    def land(self, *, canonical_rows, ctx):
        total = 0
        for _row in canonical_rows:
            total += 1
        return total


register("selftest_quiet", QuietLander())
'''

_PROBE_EXPECTED = frozenset({
    "schoolops.Route", "schoolops.LibraryItem", "schoolops.HostelRoom",
    "people.StudentProfile", "evals.Evaluation", "finance.Invoice",
})


def self_test(index: dict) -> int:
    """Plant every supported idiom and assert the resolver reports each one.

    A scan that has never been shown reporting a non-zero answer is not evidence of
    zero. The probes are tracked-shaped files inside the real package (relative
    imports have to resolve to the real ``_helpers`` summaries) and are removed in a
    ``finally``.
    """
    writer = REPO_ROOT / LANDER_DIR / "_selftest_probe_writer.py"
    quiet = REPO_ROOT / LANDER_DIR / "_selftest_probe_quiet.py"
    failures: list[str] = []
    try:
        writer.write_bytes(_PROBE_WRITER.encode("utf-8"))
        quiet.write_bytes(_PROBE_QUIET.encode("utf-8"))
        report = resolve(index)
        probe = report["domains"].get("selftest_probe")
        silent = report["domains"].get("selftest_quiet")
        if probe is None:
            failures.append("the planted writing lander was not discovered at all")
        else:
            found = set(probe["models"])
            for label in sorted(_PROBE_EXPECTED):
                if label not in found:
                    failures.append(f"planted write to {label} was NOT reported")
            if probe["unresolved"]:
                failures.append(
                    "the planted lander reported %d unresolved sites; every idiom in it "
                    "is one this resolver claims to support"
                    % len(probe["unresolved"])
                )
        if silent is None:
            failures.append("the planted non-writing lander was not discovered at all")
        else:
            # The residual net legitimately attaches DFV behind every non-sweeping
            # lander, so subtract it before asserting "writes nothing of its own".
            own = set(silent["models"]) - set(silent["residual_net"])
            if own:
                failures.append(
                    f"a lander with no writes was reported as writing {sorted(own)} "
                    f"-- false positive"
                )
    finally:
        for path in (writer, quiet):
            if path.exists():
                path.unlink()

    if failures:
        print("SELF-TEST FAILED -- a zero from this resolver would mean nothing:")
        for line in failures:
            print("  x " + line)
        return 1
    print("SELF-TEST PASSED: %d planted writes across 7 idioms all reported, with no "
          "unresolved sites; a lander that writes nothing reports nothing."
          % len(_PROBE_EXPECTED))
    return 0


# --- CLI --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument("--check-declaration", action="store_true",
                        help="Compare against landers/write_targets.py; non-zero on drift.")
    parser.add_argument("--self-test", action="store_true",
                        help="Prove the resolver can report a non-zero answer.")
    args = parser.parse_args(argv)

    index = build_model_index()
    if args.self_test:
        return self_test(index)

    report = annotate_with_rail(resolve(index))

    if args.check_declaration:
        ok, problems = check_declaration(report)
        if ok:
            print("write_targets.py matches the resolver for all %d domains."
                  % len(report["domains"]))
            return 0
        print("write_targets.py has DRIFTED from what the landers write:")
        for line in problems:
            print("  x " + line)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    total_unresolved = sum(len(v["unresolved"]) for v in report["domains"].values())
    print("")
    print("LANDER WRITE REACHABILITY -- what an import writes, and what can leave")
    print("  domains with a registered lander ... %d" % len(report["domains"]))
    print("  functions analysed ................. %d" % report["functions_analyzed"])
    print("  fixed-point passes ................. %d" % report["fixed_point_passes"])
    print("  unresolved write sites ............. %d" % total_unresolved)
    if total_unresolved:
        print("  -> domains with unresolved sites are a FLOOR, not a complete answer.")
    print("")
    print("%-24s %6s %8s %6s %9s" % ("DOMAIN", "MODELS", "REACHES", "HELD", "STRANDED"))
    for domain, entry in report["domains"].items():
        flag = "" if entry["complete"] else "  (FLOOR)"
        print("%-24s %6d %8d %6d %9d%s" % (
            domain, len(entry["models"]), len(entry["reaches_cloud"]),
            len(entry["insert_held"]), len(entry["stranded"]), flag,
        ))
    print("")
    for domain, entry in report["domains"].items():
        if not entry["stranded"]:
            continue
        print("  %s -> cannot leave this box:" % domain)
        for label in entry["stranded"]:
            print("      %s" % label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
