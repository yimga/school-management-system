#!/usr/bin/env python
"""Migration transaction-side-effect scanner (deploy-safety gate).

Seals the class of bug that aborted a Render pre-deploy in 2026-07-19 (schools
migration 0078): a ``RunPython`` migration that does a DB write / raw ``execute``
inside a BROAD ``except`` which swallows the error. On PostgreSQL a swallowed DB
error leaves the connection in ``needs_rollback``; the migration framework's
``record_applied`` (or the next statement) then raises
``TransactionManagementError`` and ABORTS THE ENTIRE DEPLOY. Catching the error
narrowly does not help — the transaction is already poisoned. The only safe
patterns are (a) wrap the DB op in a nested ``with transaction.atomic():``
savepoint so a failure rolls back cleanly, (b) let it raise, or (c) recover the
transaction with ``savepoint_rollback`` in the handler.

Two finding categories, both zero-tolerance:

(a) A DB op — ``cursor.execute`` / ORM write (``.save`` / ``.create`` /
    ``.get_or_create`` / ``.update_or_create`` / ``.bulk_create`` /
    ``.bulk_update`` / ``.iterator``) — inside a broad ``except``
    (``except Exception`` / ``except BaseException`` / bare ``except:``) whose
    handler neither re-raises nor calls ``savepoint_rollback``, AND the DB op is
    NOT itself inside a nested ``with ...atomic():`` in the try body.

(b) Email / network / Celery calls anywhere in a migration module
    (``send_mail`` / ``EmailMessage`` / ``.delay`` / ``.apply_async`` /
    ``requests`` / ``httpx`` / ``boto3`` / ``urllib`` / ``smtplib``) — a
    migration must never do I/O, regardless of exception handling.

Deliberately false-NEGATIVE biased (only the unambiguous DB-op method names, only
BROAD excepts) so it can be a zero-baseline gate with no false positives. Stdlib
AST only (no Django) → runs in the deps-free ``architectural-boundaries.yml``
boundary job. Mark a reviewed, genuinely-safe site with
``# migration-side-effect-allow: <reason>`` on the offending line or the line
above.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"

ALLOW_MARKER = "migration-side-effect-allow:"

# Unambiguous DB-op method names (attribute calls). Plain `update`/`delete`/
# `add`/`set`/`clear` are intentionally excluded — too easy to collide with
# dict/set/list methods and produce false positives.
_DB_OP_ATTRS = frozenset(
    {
        "execute",
        "executemany",
        "save",
        "create",
        "get_or_create",
        "update_or_create",
        "bulk_create",
        "bulk_update",
        "iterator",
        "aiterator",
    }
)

# Category (b) — I/O that must never appear in a migration body.
_IO_CALL_NAMES = frozenset({"send_mail", "send_mass_mail", "mail_admins"})
_IO_CTOR_NAMES = frozenset({"EmailMessage", "EmailMultiAlternatives"})
_IO_ATTR_CALLS = frozenset({"delay", "apply_async"})
_IO_ROOT_MODULES = frozenset({"requests", "httpx", "boto3", "urllib", "smtplib"})

_BROAD_NAMES = frozenset({"Exception", "BaseException"})


def _migration_files():
    if not APPS_DIR.is_dir():
        return
    for path in sorted(APPS_DIR.glob("*/migrations/*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """True for ``except:`` / ``except Exception`` / ``except BaseException`` /
    a tuple that includes one of those."""
    if handler.type is None:
        return True
    node = handler.type
    if isinstance(node, ast.Name) and node.id in _BROAD_NAMES:
        return True
    if isinstance(node, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in _BROAD_NAMES for elt in node.elts
        )
    return False


def _handler_recovers(handler: ast.ExceptHandler) -> bool:
    """A handler that re-raises or rolls back the savepoint is NOT a silent
    swallow — it does not leave the outer transaction poisoned."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("savepoint_rollback", "rollback"):
                return True
    return False


def _is_atomic_with(node: ast.With) -> bool:
    for item in node.items:
        ctx = item.context_expr
        if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute):
            if ctx.func.attr == "atomic":
                return True
    return False


def _is_db_op_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _DB_OP_ATTRS
    )


def _unprotected_db_ops(body: list[ast.stmt]) -> list[ast.AST]:
    """DB-op calls in ``body`` that are NOT wrapped in a nested ``with atomic():``.

    Descends the statement tree but stops at any ``with ...atomic():`` (those are
    savepoint-protected) — so a DB op inside a nested atomic is not reported.
    """
    hits: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.With) and _is_atomic_with(node):
            return  # protected subtree — skip entirely
        if _is_db_op_call(node):
            hits.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in body:
        visit(stmt)
    return hits


def _io_finding_node(node: ast.AST):
    """Return a short label if ``node`` is a category-(b) I/O call, else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        if func.id in _IO_CALL_NAMES:
            return func.id
        if func.id in _IO_CTOR_NAMES:
            return func.id
    if isinstance(func, ast.Attribute):
        if func.attr in _IO_ATTR_CALLS:
            return f".{func.attr}"
        # Walk the attribute chain to its root Name (requests.get, boto3.client,
        # urllib.request.urlopen, httpx.post, ...).
        root = func
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in _IO_ROOT_MODULES:
            return f"{root.id}.{func.attr}"
    return None


def _line_allowed(lines: list[str], lineno: int) -> bool:
    """True if the finding line or the line above carries the allow marker."""
    for probe in (lineno, lineno - 1):
        if 1 <= probe <= len(lines) and ALLOW_MARKER in lines[probe - 1]:
            return True
    return False


def scan_source(source: str, rel_path: str) -> list[dict]:
    """Scan one migration's source; return findings. Used by both the tree walk
    and the unit tests (feed a snippet + a synthetic path)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    findings: list[dict] = []

    # Category (a): DB op inside a broad, non-recovering except.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        swallows = any(
            _is_broad_handler(h) and not _handler_recovers(h) for h in node.handlers
        )
        if not swallows:
            continue
        for op in _unprotected_db_ops(node.body):
            if _line_allowed(lines, op.lineno):
                continue
            findings.append(
                {
                    "path": rel_path,
                    "line": op.lineno,
                    "category": "db-op-in-broad-except",
                    "detail": f".{op.func.attr}() swallowed by a broad except "
                    f"(poisons the migrate transaction on Postgres)",
                }
            )

    # Category (b): I/O anywhere in the migration.
    for node in ast.walk(tree):
        label = _io_finding_node(node)
        if label is None:
            continue
        if _line_allowed(lines, node.lineno):
            continue
        findings.append(
            {
                "path": rel_path,
                "line": node.lineno,
                "category": "io-in-migration",
                "detail": f"{label} — migrations must not do email/network/Celery I/O",
            }
        )

    findings.sort(key=lambda f: (f["line"], f["category"]))
    return findings


def scan_tree() -> list[dict]:
    findings: list[dict] = []
    for path in _migration_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_source(source, rel))
    findings.sort(key=lambda f: (f["path"], f["line"], f["category"]))
    return findings


def _payload(findings: list[dict]) -> dict:
    return {
        "rule": "no DB write / raw execute inside a broad except in a migration "
        "(poisons the migrate transaction -> deploy abort); no email/network/"
        "Celery I/O in a migration. Wrap the DB op in a nested "
        "transaction.atomic() savepoint, let it raise, or mark a genuinely-safe "
        "site with '# migration-side-effect-allow: <reason>'.",
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_tree()
    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"migration transaction side-effects: {len(findings)} finding(s) "
        f"(zero-tolerance)"
    )
    for f in findings:
        print(f"  {f['path']}:{f['line']}  [{f['category']}] {f['detail']}")
    if findings:
        print(
            "\nA migration does a DB op inside a broad except (deploy-abort class) "
            "or performs I/O. Wrap the DB op in a nested `with transaction.atomic():` "
            "savepoint, let it raise, or mark a reviewed safe site with "
            "'# migration-side-effect-allow: <reason>'."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
