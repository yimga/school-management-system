#!/usr/bin/env python3
"""Offline-capability *implementation* gate -- seals the "label without code" class.

The sibling gate ``verify_offline_manifest_taxonomy.py`` proves a tenant manifest
*declares* the offline capability flags with the right shape. It does NOT prove
any of those flags are backed by real code. A surface can ship
``enable_offline_homework_sync = true`` while no client producer enqueues the
action and no server applier writes it -- i.e. offline-first theater.

This gate closes that gap. For every declared ``OFFLINE_QUEUED_WRITE`` capability
it asserts a *complete vertical slice* exists across either offline rail:

  * **SODP / OfflineAction rail** -- ``apps/platform_runtime/offline_queue.py``
    (typed ``OfflineActionType`` intents drained via ``_apply_payload``); client
    producers enqueue through ``window.rmcOfflineEnqueue`` (``action_type: '…'``).
  * **WAL rail** -- ``apps/wal_stream/`` (``_REGISTRY`` writers + consumer
    allow-list); client producers call ``window.rmcWAL.append("<domain>", …)``.

A capability is HONEST when BOTH a client producer and a server applier exist on
at least one rail. Missing either is a hard failure (theater).

Two secondary invariants keep the contract from rotting silently:
  * Every taxonomy capability must have an entry in ``_CAPABILITY_SPEC`` below --
    a brand-new ``enable_offline_*`` flag with no spec is a hard failure, forcing
    the author to declare (and therefore implement) its rails.
  * A producer that exists but has *no UI surface* (no template carries the
    matching ``data-rmc-offline-form`` / WAL hook) is reported as a non-fatal
    ``latent`` warning -- the code is real but unreachable, which is a product
    gap to fill, not a regression to block CI on.

Stdlib-only by design: this runs in the dependency-free architectural-boundaries
job, so it must never import Django or the app. Everything is AST + text scan.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TAXONOMY = ROOT / "scripts" / "verify_offline_manifest_taxonomy.py"
ACTION_TYPES = ROOT / "apps" / "platform_runtime" / "offline_action_types.py"
OFFLINE_QUEUE = ROOT / "apps" / "platform_runtime" / "offline_queue.py"
WAL_WRITERS = ROOT / "apps" / "wal_stream" / "writers.py"
WAL_CONSUMERS = ROOT / "apps" / "wal_stream" / "consumers.py"
JS_DIR = ROOT / "static" / "js"
TEMPLATES_DIR = ROOT / "templates"


# ---------------------------------------------------------------------------
# The implementation contract. One row per OFFLINE_QUEUED_WRITE capability.
#
#   sodp_tokens : action_type strings a client producer may enqueue (legacy +
#                 dotted SODP forms). Producer match = any token in an enqueue.
#   sodp_members: OfflineActionType / OfflineAction.ActionType member names the
#                 server dispatch (offline_queue._apply_payload) must reference.
#   wal_domains : WAL domains satisfying the same capability on the WAL rail.
#   form_kinds  : data-rmc-offline-form values that expose a UI surface. Empty
#                 tuple => UI coverage is not required (generic/meta capability).
#   generic     : when True the capability is satisfied by the generic enqueue
#                 plumbing (rmcOfflineEnqueue + _apply_payload) rather than a
#                 specific typed action.
# ---------------------------------------------------------------------------
_CAPABILITY_SPEC: dict[str, dict] = {
    "enable_offline_form_queue": {
        "sodp_tokens": (),
        "sodp_members": (),
        "wal_domains": (),
        "form_kinds": (),
        "generic": True,
    },
    "enable_offline_attendance_sync": {
        "sodp_tokens": ("attendance", "attendance.mark"),
        "sodp_members": ("ATTENDANCE_MARK", "ATTENDANCE"),
        "wal_domains": ("attendance", "teacher_attendance"),
        "form_kinds": ("attendance",),
        "generic": False,
    },
    "enable_offline_grade_sync": {
        "sodp_tokens": ("grading", "grade.submit"),
        "sodp_members": ("GRADE_SUBMIT", "GRADING"),
        "wal_domains": ("grade",),
        "form_kinds": ("grading",),
        "generic": False,
    },
    "enable_offline_homework_sync": {
        "sodp_tokens": ("homework_submission", "homework.submit"),
        "sodp_members": ("HOMEWORK_SUBMIT", "HOMEWORK_SUBMISSION"),
        "wal_domains": (),
        "form_kinds": ("homework_submission",),
        "generic": False,
    },
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _assigned_value(node: ast.AST, name: str):
    """Return the value node assigned to ``name`` (plain or annotated), else None."""
    if isinstance(node, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def _declared_queued_write_capabilities() -> set[str]:
    """Extract OFFLINE_CAPABILITY_TIERS['OFFLINE_QUEUED_WRITE'] via AST."""
    tree = ast.parse(_read(TAXONOMY))
    for node in ast.walk(tree):
        value = _assigned_value(node, "OFFLINE_CAPABILITY_TIERS")
        if not isinstance(value, ast.Dict):
            continue
        for key, val in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == "OFFLINE_QUEUED_WRITE":
                return {el.value for el in _iter_set_literals(val)}
    return set()


def _iter_set_literals(node: ast.AST):
    """Yield string Constants from a ``frozenset({...})`` / ``{...}`` literal."""
    if isinstance(node, ast.Call) and node.args:
        node = node.args[0]
    elts = getattr(node, "elts", [])
    for el in elts:
        if isinstance(el, ast.Constant) and isinstance(el.value, str):
            yield el


def _wal_string_set(path: Path, name: str) -> set[str]:
    """Collect string keys/members of a module-level dict or set named ``name``."""
    tree = ast.parse(_read(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        val = _assigned_value(node, name)
        if val is None:
            continue
        if isinstance(val, ast.Dict):
            for k in val.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    found.add(k.value)
        else:
            for el in _iter_set_literals(val):
                found.add(el.value)
    return found


def _js_producer_blob() -> str:
    """Concatenated source of every client JS file (producers live here)."""
    parts = []
    for p in sorted(JS_DIR.rglob("*.js")):
        parts.append(_read(p))
    return "\n".join(parts)


def _template_form_kinds() -> set[str]:
    kinds: set[str] = set()
    pat = re.compile(r'data-rmc-offline-form\s*=\s*["\']([a-z_]+)["\']')
    for p in TEMPLATES_DIR.rglob("*.html"):
        kinds.update(pat.findall(_read(p)))
    return kinds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = ap.parse_args(argv)

    declared = _declared_queued_write_capabilities()
    wal_registry = _wal_string_set(WAL_WRITERS, "_REGISTRY")
    wal_allowed = _wal_string_set(WAL_CONSUMERS, "_ALLOWED_DOMAINS")
    js_blob = _js_producer_blob()
    queue_src = _read(OFFLINE_QUEUE)
    action_types_src = _read(ACTION_TYPES)
    ui_kinds = _template_form_kinds()

    failures: list[str] = []
    latent: list[str] = []
    rows: list[dict] = []

    # Unmapped-capability guard: a new taxonomy flag with no spec must fail.
    for cap in sorted(declared - set(_CAPABILITY_SPEC)):
        failures.append(
            f"{cap}: declared in taxonomy OFFLINE_QUEUED_WRITE but has no "
            f"_CAPABILITY_SPEC entry -- map it to a real producer + applier."
        )
    # Stale-spec guard: a spec row for a capability the taxonomy dropped.
    for cap in sorted(set(_CAPABILITY_SPEC) - declared):
        failures.append(
            f"{cap}: present in _CAPABILITY_SPEC but no longer declared in the "
            f"taxonomy -- remove the stale spec row."
        )

    for cap in sorted(declared & set(_CAPABILITY_SPEC)):
        spec = _CAPABILITY_SPEC[cap]
        if spec.get("generic"):
            producer_ok = "rmcOfflineEnqueue" in js_blob
            server_ok = "_apply_payload" in queue_src
            rail = "generic"
        else:
            # --- producer (client) presence on either rail ---
            sodp_producer = any(
                re.search(r"action_type\s*:\s*['\"]" + re.escape(t) + r"['\"]", js_blob)
                for t in spec["sodp_tokens"]
            )
            wal_producer = "rmcWAL.append" in js_blob and any(
                re.search(r"['\"]" + re.escape(d) + r"['\"]", js_blob)
                for d in spec["wal_domains"]
            )
            producer_ok = sodp_producer or wal_producer
            # --- server applier presence on either rail ---
            sodp_server = any(
                re.search(r"\b" + re.escape(m) + r"\b", queue_src)
                and (
                    re.search(r"\b" + re.escape(m) + r"\b", action_types_src)
                    or m.endswith("SUBMISSION")  # legacy ActionType lives in models.py
                )
                for m in spec["sodp_members"]
            )
            wal_server = any(
                d in wal_registry and d in wal_allowed for d in spec["wal_domains"]
            )
            server_ok = sodp_server or wal_server
            rail = (
                "+".join(
                    r
                    for r, ok in (("sodp", sodp_producer and sodp_server),
                                  ("wal", wal_producer and wal_server))
                    if ok
                )
                or "none"
            )

        if not producer_ok:
            failures.append(f"{cap}: no client producer found (no enqueue/append).")
        if not server_ok:
            failures.append(f"{cap}: no server applier found on any rail.")

        # UI-surface coverage: producer exists but nothing renders it = latent.
        form_kinds = spec.get("form_kinds") or ()
        ui_ok = (not form_kinds) or any(k in ui_kinds for k in form_kinds)
        if producer_ok and server_ok and not ui_ok:
            latent.append(
                f"{cap}: producer + applier exist but no template carries "
                f"data-rmc-offline-form in {form_kinds} -- capability is latent "
                f"(unreachable until a UI surface ships)."
            )

        rows.append(
            {
                "capability": cap,
                "producer": producer_ok,
                "server": server_ok,
                "ui_surface": ui_ok,
                "rail": rail,
            }
        )

    report = {
        "finding_count": len(failures),
        "checked": len(rows),
        "latent_count": len(latent),
        "rows": rows,
        "latent": latent,
        "failures": failures,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if failures else 0

    if failures:
        print("verify_offline_capability_implementation: FAIL")
        for f in failures:
            print(f"  - {f}")
    if latent:
        print("verify_offline_capability_implementation: latent (non-fatal):")
        for w in latent:
            print(f"  ~ {w}")
    if not failures:
        print(
            "verify_offline_capability_implementation: "
            f"OFFLINE_CAPABILITY_IMPLEMENTATION_PASS "
            f"(checked={len(rows)}, latent={len(latent)})"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
