#!/usr/bin/env python3
"""Every flushing test class must restore the catalog it truncates.

``TransactionTestCase._fixture_teardown`` runs ``flush``, which truncates EVERY
table and is not rolled back. Against this repo's persisted ``--keepdb`` database
that damage is permanent: migrations stay recorded as applied, so the idempotent
data-seed migrations never re-run. ``flush`` re-emits ``post_migrate``, which
recreates exactly one ``AccessRole`` (SUPERADMIN) and nothing else -- so granular
RBAC resolves to nothing and unrelated suites answer 403, looking like permission
regressions in code that is fine.

WHY A GATE AND NOT A NOTE
-------------------------
``docs/audits/TRANSACTION_TESTCASE_FLUSH_2026_09_03.md`` reviewed 33 classes,
converted 32, and told the survivor to be "ordered last". By 2026-09-06 there
were FIFTEEN flushing classes again, and the ordering instruction was never
enforceable: pytest runs in collection order and does not reorder. Django's own
runner does sort ``TestCase`` before ``TransactionTestCase`` -- a large part of
why the two runners disagree about this suite -- but even there the flush still
lands on the persisted file, so the NEXT run starts empty whatever the order was.

That is what makes this invisible: **the flush and the failure need not be in the
same run**. A single-file run can fail today because a whole-suite run truncated
the file yesterday, so bisecting the failing file finds nothing.

WHAT COUNTS
-----------
``LiveServerTestCase`` is a ``TransactionTestCase`` subclass and flushes
identically -- a search for the obvious base class does not find it, and one was
sitting in ``apps/compliance`` when this gate was written.

A class is satisfied by ``RestoresSeedCatalogMixin`` among its bases, by
inheriting a base that already carries it, or by a reviewed
``# seed-flush-allow: <reason>`` marker. A marker with no reason, and a marker on
a class that does not flush, are themselves findings -- an excuse must not
outlive the thing it excuses.

SHADOWED NAMES
--------------
Bases are matched by NAME, which is not the same question as "is this Django's
class". ``apps/finance/tests/test_payment_phase2.py`` defines its own
``class TransactionTestCase(TestCase)`` -- a test for transaction models that
happens to collide with Django's name and does not flush at all. So a flushing
name DEFINED in the file with non-flushing bases is treated as shadowed there.
That biases the gate towards a false negative in a file that shadows a real
base, which is the right direction: a gate that cries wolf on correct code is a
gate somebody switches off.

There is NO baseline. A class that truncates the seed catalog and leaves it
truncated is never intentional.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Bases whose teardown flushes. ``TenantHostTransactionTestCase`` is this
#: repo's own wrapper and is listed so a subclass of it is recognised as
#: flushing; it satisfies the rule itself because it carries the mixin.
FLUSHING_BASES = frozenset(
    {
        "TransactionTestCase",
        "LiveServerTestCase",
        "StaticLiveServerTestCase",
        "ChannelsLiveServerTestCase",
        "TenantHostTransactionTestCase",
    }
)

#: Bases that already restore, so a subclass inherits the cure.
RESTORING_NAMES = frozenset({"RestoresSeedCatalogMixin", "TenantHostTransactionTestCase"})

MARKER = "seed-flush-allow:"
MIN_REASON_CHARS = 10


def _base_names(node: ast.ClassDef) -> list[str]:
    names = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _marker_reason(lines: list[str], lineno: int) -> str | None:
    """Return the reason from a marker on the class line or the line above."""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and MARKER in lines[idx]:
            return lines[idx].split(MARKER, 1)[1].strip()
    return None


def scan_source(path: str, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # verify_python_files_parse owns that failure. Reporting it twice buries
        # the report that explains how to fix it.
        return []

    lines = source.splitlines()
    findings: list[dict] = []
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    # A flushing NAME redefined in this file by a non-flushing class refers to
    # that local class, not Django's. See SHADOWED NAMES in the module docstring.
    shadowed = {
        node.name
        for node in classes
        if node.name in FLUSHING_BASES
        and not FLUSHING_BASES.intersection(_base_names(node))
    }
    flushing_here = FLUSHING_BASES - shadowed

    restoring_local: set[str] = set()
    # Two passes: a class may subclass one defined above it in the same file.
    for _ in range(2):
        for node in classes:
            bases = _base_names(node)
            if RESTORING_NAMES.intersection(bases) or restoring_local.intersection(bases):
                restoring_local.add(node.name)

    for node in classes:
        bases = _base_names(node)
        flushes = flushing_here.intersection(bases)
        restores = bool(
            RESTORING_NAMES.intersection(bases) or restoring_local.intersection(bases)
        )
        reason = _marker_reason(lines, node.lineno)

        if not flushes:
            if reason is not None:
                findings.append(
                    {
                        "file": path,
                        "line": node.lineno,
                        "cls": node.name,
                        "kind": "stale-allow-marker",
                        "detail": "marker governs no flushing class",
                    }
                )
            continue

        if restores:
            if reason is not None:
                findings.append(
                    {
                        "file": path,
                        "line": node.lineno,
                        "cls": node.name,
                        "kind": "stale-allow-marker",
                        "detail": "class already restores; the marker excuses nothing",
                    }
                )
            continue

        if reason is not None:
            if len(reason) < MIN_REASON_CHARS:
                findings.append(
                    {
                        "file": path,
                        "line": node.lineno,
                        "cls": node.name,
                        "kind": "allow-marker-without-reason",
                        "detail": "reason must be at least %d characters" % MIN_REASON_CHARS,
                    }
                )
            continue

        findings.append(
            {
                "file": path,
                "line": node.lineno,
                "cls": node.name,
                "kind": "unrestored-flush",
                "detail": "inherits %s and does not restore the seed catalog"
                % ", ".join(sorted(flushes)),
            }
        )
    return findings


SELF_CHECK_CASES = [
    ("class A(TransactionTestCase):\n    pass\n", 1, "bare TransactionTestCase"),
    ("class A(RestoresSeedCatalogMixin, TransactionTestCase):\n    pass\n", 0, "mixin present"),
    ("class A(LiveServerTestCase):\n    pass\n", 1, "LiveServerTestCase also flushes"),
    ("class A(TestCase):\n    pass\n", 0, "TestCase does not flush"),
    (
        "# seed-flush-allow: needs a real transaction for threaded writes\n"
        "class A(TransactionTestCase):\n    pass\n",
        0,
        "reviewed marker on the line above",
    ),
    (
        "class A(TransactionTestCase):  # seed-flush-allow: short\n    pass\n",
        1,
        "reason too short",
    ),
    (
        "# seed-flush-allow: this class does not flush at all\nclass A(TestCase):\n    pass\n",
        1,
        "stale marker",
    ),
    (
        "class Base(RestoresSeedCatalogMixin, TransactionTestCase):\n    pass\n"
        "class A(Base):\n    pass\n",
        0,
        "inherits the cure from a local base",
    ),
    (
        "class TransactionTestCase(TestCase):\n    pass\n"
        "class A(TransactionTestCase):\n    pass\n",
        0,
        "locally shadowed name is not Django's flushing class",
    ),
    (
        "class A(\n    RestoresSeedCatalogMixin,\n    TransactionTestCase,\n):\n    pass\n",
        0,
        "multi-line base list -- a regex on the class line misses this",
    ),
    ("class A(\n    TransactionTestCase,\n):\n    pass\n", 1, "multi-line base list, unrestored"),
    ("class A(:\n", 0, "unparseable is another gate's job"),
]


def self_check() -> bool:
    ok = True
    for source, expected, label in SELF_CHECK_CASES:
        got = len(scan_source("<self-check>", source))
        if got != expected:
            print(
                "SELF-CHECK FAIL: %s -- expected %d finding(s), got %d"
                % (label, expected, got)
            )
            ok = False
    return ok


def candidate_files() -> list[Path]:
    """Files that name a flushing base at all.

    ``git grep`` rather than reading every tracked module: there are 7,704
    tracked ``.py`` files under ``apps/`` and reading them all costs 220s on
    Windows, where the same search over the index costs about three seconds.
    It searches tracked working-tree content, which is what deploys -- so a
    brand-new file is invisible until ``git add -N``, the same trade every
    ``git ls-files`` gate in this repo already makes.
    """
    args = ["git", "grep", "-l"]
    for name in sorted(FLUSHING_BASES) + [MARKER.rstrip(":")]:
        args += ["-e", name]
    args += ["--", "apps"]
    out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    paths = [ROOT / line for line in out.stdout.splitlines() if line.endswith(".py")]
    return [p for p in paths if p.exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    if not self_check():
        print(
            "\nRefusing to report a scan result: the classifier disagrees with "
            "its own known-good cases."
        )
        return 1
    if args.self_check:
        print("self-check: %d cases OK" % len(SELF_CHECK_CASES))
        return 0

    files = candidate_files()
    if not files:
        # A zero over an empty corpus is not a zero. This repo HAS flushing
        # classes; finding none means discovery broke, not that the tree is clean.
        print(
            "scan_unrestored_flush_testcase: FAIL -- no candidate files found. "
            "Discovery is broken (is this a git worktree?)."
        )
        return 1

    findings: list[dict] = []
    for path in files:
        try:
            source = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        findings.extend(scan_source(rel, source))

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
        return 1 if findings else 0

    for f in findings:
        print("%s:%d: %s: %s -- %s" % (f["file"], f["line"], f["kind"], f["cls"], f["detail"]))
    print(
        "\nscan_unrestored_flush_testcase: %d finding(s) across %d candidate files"
        % (len(findings), len(files))
    )
    if findings:
        print(
            "\nFix: add RestoresSeedCatalogMixin (apps/test_utils/seed_preserving.py)\n"
            "as the FIRST base, or record a reviewed exception with\n"
            "`# seed-flush-allow: <reason>` on the class line or the line above."
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
