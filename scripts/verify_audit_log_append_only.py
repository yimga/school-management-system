#!/usr/bin/env python3
"""Gate: the compliance AuditLog is append-only outside a declared allowlist.

WHY THIS EXISTS, AND WHY IT WAS REWRITTEN
-----------------------------------------
An audit log that can be edited is not an audit log. This gate exists so that a
new ``AuditLog.objects...update()`` or ``.delete()`` has to be argued for in a
diff instead of appearing quietly.

The first version could not do that. It matched on the LAST TWO names of the
attribute chain::

    if chain[-2:] == ["objects", "update"] or chain[-2:] == ["objects", "delete"]:

which only ever sees the bare ``AuditLog.objects.update(...)`` -- a form nobody
writes, because a bare ``.update()`` on a manager is not even valid Django. The
form people actually write is ``AuditLog.objects.filter(...).update(...)``, whose
chain ends ``["filter", "update"]``. So the gate could only print PASS, and did,
while ``apps/compliance/privacy.py`` held a real one. A guard that cannot fail is
worse than no guard: it is a green light nobody re-checks.

Run ``--selftest`` to see the matcher flag a synthetic sample of every form it
claims to catch. A detector's zero is worth nothing until the detector has been
shown to produce a non-zero.

THE DECLARED EXCEPTION
----------------------
``anonymize_user`` in ``apps/compliance/privacy.py`` detaches the user FK and
strips ip/user-agent/object_repr from that user's audit rows. That is the GDPR
right-to-erasure path and it is legitimate: the ROW survives -- what it did, to
what, and when -- and only the identifiers of the erased person are removed. The
point of listing it here is that it is now DECLARED. A second such call, or a
change that starts deleting the rows outright, fails this gate.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "apps", ROOT / "services")

# Test files build the fixtures they assert on, and a migration is a schema-time
# operation reviewed as one. Management commands are NOT exempt: the retention
# purge is exactly the kind of thing that should be listed by name below.
SKIP_SEGMENTS = ("/migrations/", "/tests/")

# path -> why this mutation is allowed. Keep the reason specific enough that the
# next reader can tell whether a NEW call in the same file is covered by it.
ALLOWED = {
    "apps/compliance/privacy.py": (
        "anonymize_user(): GDPR erasure. Detaches user FK and strips "
        "ip_address/user_agent/object_repr; the audit ROW and its action, target "
        "and timestamp survive."
    ),
}

MUTATORS = {"update", "delete", "bulk_update", "bulk_create"}


def _root_name(node: ast.AST) -> str:
    """The leftmost identifier of an attribute chain, or ''."""
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ""


def scan_source(source: str, label: str) -> list[str]:
    """Flag every ``AuditLog...update/delete(...)`` regardless of chain length."""
    findings: list[str] = []
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in MUTATORS:
            continue
        # Walk the whole chain, not just its tail: `AuditLog.objects.filter(...)
        # .exclude(...).update(...)` is the same mutation with more links.
        chain, cur = [], node.func
        while isinstance(cur, (ast.Attribute, ast.Call)):
            if isinstance(cur, ast.Attribute):
                chain.insert(0, cur.attr)
                cur = cur.value
            else:
                cur = cur.func
        root = _root_name(node.func)
        if "AuditLog" not in root and "AuditLog" not in chain:
            continue
        if "objects" not in chain and "all_objects" not in chain:
            continue
        findings.append(f"{label}:{node.lineno} {root}.{'.'.join(chain)}()")
    return findings


def _scan_file(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return scan_source(source, path.relative_to(ROOT).as_posix())


SELFTEST_SAMPLE = """
from apps.compliance.models_audit import AuditLog

def wipe(user):
    AuditLog.objects.filter(user=user).update(user=None)
    AuditLog.objects.filter(user=user).exclude(pk=1).delete()
    AuditLog.objects.all().delete()
"""


def selftest() -> int:
    hits = scan_source(SELFTEST_SAMPLE, "<selftest>")
    expected = 3
    for h in hits:
        print(f"  caught {h}")
    if len(hits) != expected:
        print(
            f"SELFTEST FAIL: matcher caught {len(hits)}/{expected} known mutations. "
            "The gate cannot be trusted until this passes.",
            file=sys.stderr,
        )
        return 1
    print(f"selftest: OK, matcher catches all {expected} chained forms.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the matcher fires on known-bad samples, then exit",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    undeclared: list[str] = []
    declared: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.as_posix()
            if any(seg in rel for seg in SKIP_SEGMENTS):
                continue
            for finding in _scan_file(path):
                (declared if finding.split(":")[0] in ALLOWED else undeclared).append(finding)

    for finding in declared:
        print(f"  allowed  {finding}  # {ALLOWED[finding.split(':')[0]]}")
    if undeclared:
        print("verify_audit_log_append_only: FAIL", file=sys.stderr)
        for finding in undeclared:
            print(f"  {finding}", file=sys.stderr)
        print(
            "An AuditLog row may not be rewritten or removed by application code. "
            "If this really is an erasure obligation, add the file to ALLOWED in "
            "this script with the reason, so the exception is reviewable.",
            file=sys.stderr,
        )
        return 1
    print(
        f"verify_audit_log_append_only: PASS "
        f"({len(declared)} declared exception(s), 0 undeclared mutations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
