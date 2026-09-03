#!/usr/bin/env python3
"""Verify wizard step writers reach a domain service, not just the cockpit blob.

What this gate is for
---------------------
``apps/setup_studio/wizard_state_resolver.py::apply_step_answer`` appends a step
to ``state["completed"]`` BEFORE it invokes the step's persistence writer, and
wraps that call in a broad ``except Exception`` that only logs. So a writer that
does nothing useful is invisible from the UI: the wizard says done and the table
is empty. Writers are dispatched by dotted string from the wizard JSON, so
``git grep write_<name>`` finds no caller and nothing else can see the wiring
either. This gate is the only thing that looks.

Why the previous detector was wrong in BOTH directions
------------------------------------------------------
It matched a hand-maintained list of 15 function-name substrings
(``_DOMAIN_MARKERS``) against the writer's source text.

* 41 FALSE POSITIVES. Since that list was written the codebase moved to per-app
  wizard kernels -- ``apps.customersuccess.helpcenter_wizard_kernel``,
  ``apps.schoolops.pos_config_kernel``, ``apps.safeguarding.wizard_config_kernel``,
  ``apps.academics.scheduling_kernel``, ``apps.payroll.hr_wizard_kernel``,
  ``apps.reports.board_aggregation_kernel``, ``apps.evals.grading_wizard_kernel``,
  ``apps.accounts.persona_onboarding_kernel`` and a dozen more. None of their
  function names is in the list, so 41 writers that DO delegate were reported as
  "cockpit-only". A gate that names 41 innocent writers is a gate nobody reads,
  which is exactly what happened: it emitted ~8 KB of findings into a log no run
  ever produced, because it was wired into no workflow and no hook.

* 3 FALSE NEGATIVES, and this is the sharper half. ``_write_to_site_settings``
  -- the cockpit write helper itself -- was listed as a DOMAIN marker. It is the
  precise thing this gate exists to flag, so any writer that called the cockpit
  helper by name passed the domain-integration check. ``write_sovereignty_vocabulary``
  (body: ``_write_to_site_settings`` + ``_default_cockpit_writer``) and
  ``write_student_course_selection_step`` (body: one ``_write_to_site_settings``)
  are pure cockpit writers that the old gate reported as clean.

What it checks now (structure, not vocabulary)
----------------------------------------------
A writer DELEGATES when its own body does one of:

* call ``_try_domain_integration(...)``; or
* import a module OUTSIDE the three wizard resolver modules and CALL something
  it imported. The "and call" half matters: ``write_super_create_school_step``
  carries a deliberate ``# noqa: F401`` anchor import it never calls, and a
  name-only check would credit it; or
* write real model state -- a ``.objects.<create|get_or_create|update_or_create|
  bulk_create>`` call, ``save(update_fields=[...])`` naming a column other than
  ``settings``, or a ``setattr(obj, ...)`` paired with a ``.save(...)`` (the
  shape ``write_sovereignty_jurisdiction`` uses to write School.country_code /
  state_code / data_residency_region, whose update_fields list is COMPUTED, so
  a literal-only reader would call a real column write cockpit-only).

Nothing here is a name list, so a new kernel needs no edit to this file.

An honest limit, stated rather than papered over
------------------------------------------------
"Delegates to a domain service" is NOT the same as "the data reaches a domain
table". Most wizard kernels persist into a differently-named ``school.settings``
namespace, and as of 2026-09-02 neither the cockpit namespace
(``settings["wizards"]``) nor most kernel namespaces (``settings["pos"]``,
``settings["field_trip"]``, ``settings["role_wizards"]`` ...) has any reader in
``apps/`` or ``services/`` outside the module that wrote it. So passing this gate
by delegating to a reader-less kernel would move the blob, not fix the wizard.
The reader question is a bigger, separate gate; this one measures the layer
boundary it can actually see, and says so.

Exit codes::

    0 -- every writer delegates (or is an explicitly justified cockpit-only writer)
    1 -- at least one cockpit-only writer, or a stale allow entry
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD_DIR = ROOT / "apps" / "setup_studio" / "wizards"

RESOLVER_MODULES = {
    "wizard_resolvers": ROOT / "apps/setup_studio/wizard_resolvers.py",
    "wizard_resolvers_operator": ROOT / "apps/setup_studio/wizard_resolvers_operator.py",
    "wizard_resolvers_domain": ROOT / "apps/setup_studio/wizard_resolvers_domain.py",
}
# The resolver layer itself. An import of one of these is not delegation.
_RESOLVER_DOTTED = {f"apps.setup_studio.{name}" for name in RESOLVER_MODULES}

_WRITER_RE = re.compile(
    r"^apps\.setup_studio\.(wizard_resolvers(?:_operator|_domain)?)::(?P<fn>write_[a-z0-9_]+)$"
)

# Model-write call names that prove the writer touched real rows.
_ORM_WRITE_CALLS = frozenset({"create", "get_or_create", "update_or_create", "bulk_create"})

# Writers that are cockpit-only ON PURPOSE. Reason required; a stale entry (one
# naming a writer that no longer exists, or one that now delegates) is itself a
# finding, so an excuse cannot outlive the thing it excuses.
_ALLOW_COCKPIT_ONLY: dict[str, str] = {
    "write_super_create_school_step": (
        "operator scratch: the wizard runs BEFORE a tenant exists, so there is no "
        "school to write to; provisioning is the POST to super:api_create_school"
    ),
    "write_mfa_setup_step": (
        "account-scoped, not tenant-scoped: secret material lives in "
        "accounts.MFAEnrollment and the writer deliberately persists only the "
        "chosen channel plus the acceptance flag"
    ),
}


def _load_writers() -> dict[str, tuple[str, ast.FunctionDef]]:
    out: dict[str, tuple[str, ast.FunctionDef]] = {}
    for mod_name, path in RESOLVER_MODULES.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("write_"):
                out[node.name] = (mod_name, node)
    return out


def _delegation_evidence(node: ast.FunctionDef) -> str | None:
    """Return a one-line reason this writer delegates, or None if cockpit-only."""
    imported: dict[str, str] = {}   # local name -> module it came from
    called: set[str] = set()
    orm_write: list[str] = []
    column_save: list[str] = []
    setattr_targets: list[str] = []
    saw_save = False

    for sub in ast.walk(node):
        if isinstance(sub, ast.ImportFrom) and sub.module:
            if sub.module in _RESOLVER_DOTTED:
                continue
            for alias in sub.names:
                imported[alias.asname or alias.name] = sub.module
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                if alias.name not in _RESOLVER_DOTTED:
                    imported[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                called.add(func.id)
                if func.id == "setattr" and len(sub.args) >= 2:
                    setattr_targets.append(ast.dump(sub.args[1])[:60])
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
                # <Anything>.objects.<write>(...)
                if func.attr in _ORM_WRITE_CALLS and _has_objects_manager(func.value):
                    orm_write.append(func.attr)
                if func.attr == "save":
                    saw_save = True
                    fields = _update_fields(sub)
                    if fields is not None and set(fields) - {"settings"}:
                        column_save.append(",".join(sorted(fields)))

    if "_try_domain_integration" in called:
        return "calls _try_domain_integration"

    delegated = sorted({mod for name, mod in imported.items() if name in called})
    if delegated:
        return "calls into " + ", ".join(delegated)

    if orm_write:
        return "writes model rows via .objects.%s" % orm_write[0]
    if column_save:
        return "saves real School column(s): %s" % column_save[0]
    if setattr_targets and saw_save:
        return "setattr()s model field(s) and saves the row"

    if imported and not delegated:
        # An import whose symbol is never called is an anchor, not delegation.
        return None
    return None


def _has_objects_manager(value: ast.AST) -> bool:
    return isinstance(value, ast.Attribute) and value.attr == "objects"


def _update_fields(call: ast.Call) -> list[str] | None:
    for kw in call.keywords:
        if kw.arg == "update_fields" and isinstance(kw.value, (ast.List, ast.Tuple)):
            names = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.append(elt.value)
            return names
    return None


def main() -> int:
    writers = _load_writers()
    seen: list[tuple[str, str, str]] = []   # (fn, module, wizard file)
    seen_names: set[str] = set()
    failures: list[str] = []
    delegating = 0
    allowed = 0

    for path in sorted(WIZARD_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for step in data.get("steps") or []:
            writer = (step.get("persistence") or {}).get("writer") or ""
            match = _WRITER_RE.match(writer.strip())
            if not match:
                continue
            fn = match.group("fn")
            if fn in seen_names:
                continue
            seen_names.add(fn)

            located = writers.get(fn)
            if located is None:
                failures.append(
                    f"missing writer function: {fn} -- {path.name} dispatches a "
                    f"dotted path that resolves to nothing, so the step completes "
                    f"and NOTHING is written"
                )
                continue
            mod, node = located
            seen.append((fn, mod, path.name))

            if fn in _ALLOW_COCKPIT_ONLY:
                allowed += 1
                continue

            evidence = _delegation_evidence(node)
            if evidence is None:
                failures.append(
                    f"cockpit-only writer: {fn} ({mod}, {path.name}) -- its whole "
                    f"body lands in school.settings and it reaches no service "
                    f"outside the wizard resolver layer"
                )
            else:
                delegating += 1

    # A stale allow entry is a finding: it must name a real writer that is still
    # cockpit-only, otherwise the excuse has outlived its subject.
    for fn, reason in sorted(_ALLOW_COCKPIT_ONLY.items()):
        if not str(reason or "").strip():
            failures.append(f"_ALLOW_COCKPIT_ONLY['{fn}'] carries no reason")
        if fn not in seen_names:
            failures.append(
                f"_ALLOW_COCKPIT_ONLY names '{fn}', which no wizard JSON dispatches "
                f"any more -- the exemption is stale"
            )
            continue
        located = writers.get(fn)
        if located and _delegation_evidence(located[1]) is not None:
            failures.append(
                f"_ALLOW_COCKPIT_ONLY names '{fn}', which now delegates "
                f"({_delegation_evidence(located[1])}) -- drop the exemption"
            )

    print(
        "== verify_wizard_domain_writer_coverage == "
        f"{len(seen_names)} writer(s) dispatched: {delegating} delegate, "
        f"{allowed} explicitly cockpit-only, {len(failures)} finding(s)"
    )
    if failures:
        for item in failures:
            print(f"WIZARD_WRITER_COVERAGE_FAIL: {item}", file=sys.stderr)
        return 1
    print(f"WIZARD_WRITER_COVERAGE_PASS ({len(seen_names)} writers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
