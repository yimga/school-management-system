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

DETECTION IS STRUCTURAL, NOT TEXTUAL (2026-07-21)
-------------------------------------------------
The first version of this gate concatenated every ``static/js/**/*.js`` file
into one blob and ran ``re.search`` over it, and did the same with a ``\\bNAME\\b``
search over ``offline_queue.py``. That made the gate incapable of failing: a
capability whose only trace was

    // TODO: one day wire   action_type: 'payment_receipt'

plus a Python *comment* naming ``PAYMENT_RECEIPT`` reported
``producer: true, server: true, rail: "sodp"`` with zero findings. A gate that a
comment satisfies is decoration. Detection is now:

  * **Client producer** -- the JS is tokenised (comments dropped, string
    literals atomic) and a producer must be a real ``rmcOfflineEnqueue({...})``
    call site whose ``action_type`` property is one of the spec tokens, or a
    real ``rmcWAL.append(<domain>, ...)`` call site whose first argument is one
    of the spec domains. Text inside a comment or nested inside another string
    can no longer satisfy it. (Limitation, deliberate and documented: when the
    WAL domain argument is a local identifier -- e.g.
    ``rmc-attendance-wal-enhance.js`` picks ``domain`` per gate -- it is
    resolved from string assignments to that identifier inside the *enclosing
    block only*.)
  * **Server applier (SODP)** -- ``offline_queue.py`` is parsed with ``ast`` and
    only ``_apply_payload``'s real dispatch counts: an ``if`` whose test
    references ``OfflineActionType.<M>`` / ``OfflineAction.ActionType.<M>`` and
    whose body actually ``return``s a call. The member must additionally exist
    in a real enum (``offline_action_types.py`` or ``OfflineAction.ActionType``
    in ``platform_runtime/models.py``) -- no more ``endswith("SUBMISSION")``
    heuristic. Comments and docstrings do not appear in an AST at all.
  * **UI surface** -- template scanning strips HTML ``<!-- -->`` and Django
    ``{# #}`` / ``{% comment %}`` blocks first.

The must-fire negative controls live in
``scripts/tests/test_verify_offline_capability_implementation.py``
(``CommentOnlyMustFireTests``): each reintroduces the comment-only defect and
asserts the gate returns 1.

Follow-up (not done here): a *runtime* proof belongs in the unused Playwright
offline harness (``playwright.offline-indexeddb.config.js``, npm script
``test:e2e:offline-multiday``) -- structural detection proves the call site and
the dispatch branch exist and are wired, not that a queued action round-trips.

Stdlib-only by design: this runs in the dependency-free architectural-boundaries
job, so it must never import Django or the app. Everything is AST + tokeniser.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]

TAXONOMY = ROOT / "scripts" / "verify_offline_manifest_taxonomy.py"
ACTION_TYPES = ROOT / "apps" / "platform_runtime" / "offline_action_types.py"
OFFLINE_QUEUE = ROOT / "apps" / "platform_runtime" / "offline_queue.py"
PLATFORM_RUNTIME_MODELS = ROOT / "apps" / "platform_runtime" / "models.py"
WAL_WRITERS = ROOT / "apps" / "wal_stream" / "writers.py"
WAL_CONSUMERS = ROOT / "apps" / "wal_stream" / "consumers.py"
JS_DIR = ROOT / "static" / "js"
TEMPLATES_DIR = ROOT / "templates"

# Client entry points a real producer must call.
ENQUEUE_FN = "rmcOfflineEnqueue"
WAL_OBJECT = "rmcWAL"
WAL_METHOD = "append"


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
    "enable_offline_fee_payment_sync": {
        "sodp_tokens": ("payment_receipt", "payment.proof_upload"),
        "sodp_members": ("PAYMENT_PROOF", "PAYMENT_RECEIPT"),
        "wal_domains": ("billing_charge",),
        "form_kinds": ("payment_receipt",),
        "generic": False,
    },
    "enable_offline_migration_cloud_upload": {
        "sodp_tokens": ("migration_cloud_upload", "migration.bundle_upload"),
        "sodp_members": ("MIGRATION_BUNDLE_UPLOAD", "MIGRATION_CLOUD_UPLOAD"),
        "wal_domains": (),
        "form_kinds": ("migration_cloud_upload",),
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


# ---------------------------------------------------------------------------
# Structural JS scanning.
#
# A minimal JS tokeniser: enough to know what is CODE and what is a comment or
# a string body. Comments are dropped outright; string literals become single
# atomic tokens, so text *inside* a string can never be mistaken for code.
# Regex literals are not modelled -- an unmatched `/` degrades to punctuation,
# and the `'`/`"` patterns are newline-bounded so a quote inside a regex cannot
# swallow the rest of the file.
# ---------------------------------------------------------------------------

_JS_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<line_comment>//[^\n]*)
    | (?P<block_comment>/\*.*?\*/)
    | (?P<sq>'(?:\\.|[^'\\\n])*')
    | (?P<dq>"(?:\\.|[^"\\\n])*")
    | (?P<tpl>`(?:\\.|[^`\\])*`)
    | (?P<num>\d[\w.]*)
    | (?P<ident>[A-Za-z_$][\w$]*)
    | (?P<punc>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_STRING_KINDS = frozenset({"sq", "dq", "tpl"})


class JsToken(NamedTuple):
    kind: str
    value: str
    depth: int  # curly-brace nesting depth


def _js_tokenize(src: str) -> list[JsToken]:
    tokens: list[JsToken] = []
    depth = 0
    for m in _JS_TOKEN_RE.finditer(src):
        kind = m.lastgroup or "punc"
        if kind in ("ws", "line_comment", "block_comment"):
            continue
        text = m.group()
        if kind == "punc" and text == "{":
            tokens.append(JsToken(kind, text, depth))
            depth += 1
            continue
        if kind == "punc" and text == "}":
            depth = max(0, depth - 1)
            tokens.append(JsToken(kind, text, depth))
            continue
        tokens.append(JsToken(kind, text, depth))
    return tokens


def _string_value(tok: JsToken) -> str:
    body = tok.value[1:-1]
    return re.sub(r"\\(.)", r"\1", body)


def _matching_paren(tokens: list[JsToken], open_idx: int) -> int:
    """Index of the ``)`` matching the ``(`` at ``open_idx`` (or end of stream)."""
    level = 0
    for j in range(open_idx, len(tokens)):
        v = tokens[j].value
        if tokens[j].kind == "punc" and v == "(":
            level += 1
        elif tokens[j].kind == "punc" and v == ")":
            level -= 1
            if level == 0:
                return j
    return len(tokens)


def _plain_call_sites(tokens: list[JsToken], name: str) -> list[int]:
    """Indices of the ``(`` opening a real call to identifier ``name``."""
    out = []
    for i, tok in enumerate(tokens):
        if tok.kind != "ident" or tok.value != name:
            continue
        if i + 1 < len(tokens) and tokens[i + 1].value == "(":
            out.append(i + 1)
    return out


def _member_call_sites(tokens: list[JsToken], obj: str, method: str) -> list[int]:
    """Indices of the ``(`` opening a real call to ``<obj>.<method>(``."""
    out = []
    for i in range(len(tokens) - 3):
        if tokens[i].kind != "ident" or tokens[i].value != obj:
            continue
        if tokens[i + 1].value != "." or tokens[i + 2].value != method:
            continue
        if tokens[i + 3].value == "(":
            out.append(i + 3)
    return out


def _enclosing_block_span(tokens: list[JsToken], idx: int) -> tuple[int, int]:
    """Token range of the block enclosing ``idx`` (by curly-brace depth)."""
    depth = tokens[idx].depth
    start = 0
    for j in range(idx, -1, -1):
        if tokens[j].depth < depth:
            start = j
            break
    end = len(tokens)
    for j in range(idx, len(tokens)):
        if tokens[j].depth < depth:
            end = j
            break
    return start, end


def _local_string_assignments(
    tokens: list[JsToken], idx: int, name: str
) -> set[str]:
    """String literals assigned to ``name`` within the block enclosing ``idx``."""
    start, end = _enclosing_block_span(tokens, idx)
    found: set[str] = set()
    for j in range(start, max(start, end - 2)):
        if tokens[j].kind != "ident" or tokens[j].value != name:
            continue
        if tokens[j + 1].value != "=" or tokens[j + 1].kind != "punc":
            continue
        if tokens[j + 2].kind in _STRING_KINDS:
            found.add(_string_value(tokens[j + 2]))
    return found


def _enqueued_action_types(tokens: list[JsToken]) -> set[str]:
    """``action_type`` string literals passed to a real ``rmcOfflineEnqueue`` call."""
    found: set[str] = set()
    for open_idx in _plain_call_sites(tokens, ENQUEUE_FN):
        close = _matching_paren(tokens, open_idx)
        for j in range(open_idx + 1, max(open_idx + 1, close - 2)):
            tok = tokens[j]
            key = (
                tok.value
                if tok.kind == "ident"
                else (_string_value(tok) if tok.kind in _STRING_KINDS else None)
            )
            if key != "action_type" or tokens[j + 1].value != ":":
                continue
            if tokens[j + 2].kind in _STRING_KINDS:
                found.add(_string_value(tokens[j + 2]))
    return found


def _wal_appended_domains(tokens: list[JsToken]) -> set[str]:
    """Domains passed as first argument to a real ``rmcWAL.append(...)`` call."""
    found: set[str] = set()
    for open_idx in _member_call_sites(tokens, WAL_OBJECT, WAL_METHOD):
        if open_idx + 1 >= len(tokens):
            continue
        arg = tokens[open_idx + 1]
        if arg.kind in _STRING_KINDS:
            found.add(_string_value(arg))
        elif arg.kind == "ident" and tokens[open_idx + 2].value in (",", ")"):
            found |= _local_string_assignments(tokens, open_idx, arg.value)
    return found


def _js_sources() -> list[str]:
    """Source of every client JS file that could hold an offline producer.

    Pre-filtered on a cheap substring so 29 MB of vendor bundles are not
    tokenised: a file with no textual mention of the entry point provably has
    no call site to it, so the filter is a sound superset.
    """
    out: list[str] = []
    for p in sorted(JS_DIR.rglob("*.js")):
        src = _read(p)
        if ENQUEUE_FN in src or WAL_OBJECT in src:
            out.append(src)
    return out


def _client_producer_facts(sources: list[str] | None = None) -> dict:
    """Real client-side call sites, keyed by what they prove."""
    if sources is None:
        sources = _js_sources()
    action_types: set[str] = set()
    wal_domains: set[str] = set()
    enqueue_calls = 0
    for src in sources:
        tokens = _js_tokenize(src)
        enqueue_calls += len(_plain_call_sites(tokens, ENQUEUE_FN))
        action_types |= _enqueued_action_types(tokens)
        wal_domains |= _wal_appended_domains(tokens)
    return {
        "action_types": action_types,
        "wal_domains": wal_domains,
        "enqueue_call_sites": enqueue_calls,
    }


# ---------------------------------------------------------------------------
# Structural server scanning (AST -- comments/docstrings are invisible to it).
# ---------------------------------------------------------------------------


def _enum_member_names() -> set[str]:
    """Members of ``OfflineActionType`` and ``OfflineAction.ActionType``."""
    names: set[str] = set()

    def _class_members(node: ast.ClassDef) -> set[str]:
        out = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                out.add(stmt.target.id)
        return out

    for node in ast.walk(ast.parse(_read(ACTION_TYPES))):
        if isinstance(node, ast.ClassDef) and node.name == "OfflineActionType":
            names |= _class_members(node)
    for node in ast.walk(ast.parse(_read(PLATFORM_RUNTIME_MODELS))):
        if isinstance(node, ast.ClassDef) and node.name == "OfflineAction":
            for stmt in node.body:
                if isinstance(stmt, ast.ClassDef) and stmt.name == "ActionType":
                    names |= _class_members(stmt)
    return names


def _enum_attr_names(test: ast.AST) -> set[str]:
    """Enum member names referenced as ``OfflineActionType.X`` / ``…ActionType.X``."""
    out: set[str] = set()
    for sub in ast.walk(test):
        if not isinstance(sub, ast.Attribute):
            continue
        base = sub.value
        if isinstance(base, ast.Name) and base.id in (
            "OfflineActionType",
            "ActionType",
        ):
            out.add(sub.attr)
        elif (
            isinstance(base, ast.Attribute)
            and base.attr == "ActionType"
            and isinstance(base.value, ast.Name)
        ):
            out.add(sub.attr)
    return out


def _apply_payload_fn(queue_src: str) -> ast.FunctionDef | None:
    for node in ast.walk(ast.parse(queue_src)):
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_payload":
            return node
    return None


def _branch_does_work(branch: ast.If) -> bool:
    """True when the branch body actually returns the result of a call."""
    for stmt in branch.body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Call):
                return True
    return False


def _dispatched_members(queue_src: str, enum_members: set[str]) -> set[str]:
    """Enum members ``_apply_payload`` really dispatches on to a real applier."""
    fn = _apply_payload_fn(queue_src)
    if fn is None:
        return set()
    dispatched: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or not _branch_does_work(node):
            continue
        dispatched |= _enum_attr_names(node.test) & enum_members
    return dispatched


# ---------------------------------------------------------------------------
# Template scanning (comment-stripped).
# ---------------------------------------------------------------------------

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_DJANGO_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_DJANGO_COMMENT_BLOCK_RE = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)


def _strip_markup_comments(text: str) -> str:
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _DJANGO_COMMENT_BLOCK_RE.sub(" ", text)
    return _DJANGO_COMMENT_RE.sub(" ", text)


def _template_form_kinds() -> set[str]:
    kinds: set[str] = set()
    pat = re.compile(r'data-rmc-offline-form\s*=\s*["\']([a-z_]+)["\']')
    for p in TEMPLATES_DIR.rglob("*.html"):
        kinds.update(pat.findall(_strip_markup_comments(_read(p))))
    return kinds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = ap.parse_args(argv)

    declared = _declared_queued_write_capabilities()
    wal_registry = _wal_string_set(WAL_WRITERS, "_REGISTRY")
    wal_allowed = _wal_string_set(WAL_CONSUMERS, "_ALLOWED_DOMAINS")
    client = _client_producer_facts()
    queue_src = _read(OFFLINE_QUEUE)
    enum_members = _enum_member_names()
    dispatched = _dispatched_members(queue_src, enum_members)
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
            # Generic rail: the plumbing itself must be real -- at least one
            # honest enqueue call site, and an _apply_payload that really
            # dispatches (an AST FunctionDef with >= 1 working branch).
            producer_ok = client["enqueue_call_sites"] > 0
            server_ok = bool(dispatched)
            rail = "generic"
        else:
            # --- producer (client) presence on either rail: real call sites ---
            sodp_producer = bool(set(spec["sodp_tokens"]) & client["action_types"])
            wal_producer = bool(set(spec["wal_domains"]) & client["wal_domains"])
            producer_ok = sodp_producer or wal_producer
            # --- server applier presence on either rail ---
            # SODP: the member must be dispatched by _apply_payload's real
            # control flow AND exist in a real enum. A mention in a comment or
            # docstring is not in the AST, so it cannot satisfy this.
            sodp_server = bool(set(spec["sodp_members"]) & dispatched)
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
        # What the structural pass actually resolved -- publishing this makes a
        # future regression to "the string appeared somewhere" visible in diff.
        "detection": {
            "mode": "structural (js tokeniser + python ast)",
            "enqueue_call_sites": client["enqueue_call_sites"],
            "enqueued_action_types": sorted(client["action_types"]),
            "wal_appended_domains": sorted(client["wal_domains"]),
            "dispatched_members": sorted(dispatched),
        },
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
