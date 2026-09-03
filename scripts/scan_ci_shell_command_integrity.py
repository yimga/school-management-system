#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Refuse CI/dev commands that cannot run what they claim to run.

Two defects, both found on 2026-08-31, both invisible in review and both
capable of showing a green-looking pipeline that executed nothing.

TRUNCATED CONTINUATION
    A trailing backslash escapes the newline and joins the line with the one
    that FOLLOWS. When the following line is blank, the join yields nothing and
    the command ends right there; every remaining "continuation" line is parsed
    as its own command.

        python manage.py test \\
                                    <-- blank line
            apps.schoolops.tests.x \\
                                    <-- blank line
            apps.reports.tests.y

    ran as three commands: a BARE `manage.py test` (which crashes at Django
    discovery), then two `command not found`. Found in
    django-tests-postgres.yml, where it had silently disabled the Postgres
    proof for 24 test modules -- booking, inventory, substitute matching,
    discipline routing, report-card e2e, DR snapshot restore, CRDT live-rail
    convergence, residency border-lock and five N+1 query-count suites. Those
    are exactly the areas a platform audit could not verify, and the reason was
    never that the tests were missing.

BARE `manage.py test`
    With no positional label, Django's unittest loader discovers from '.', which
    in this tree reaches `emis/tests` -- a bare `tests` package under a non-app
    root -- and raises ImportError at DISCOVERY, before a single test runs.
    `--tag` does NOT help: it selects among tests already found. The working
    form names discovery roots, e.g.
        python manage.py test apps config services payment.tests emis.tests

SCOPE. The gate FAILS only on contexts that are actually executed: `run:`
blocks in workflows, and .sh/.ps1/.bat scripts. A bare invocation inside a
Python docstring or a Markdown runbook is documentation -- still worth fixing,
because it tells a human to run a command that crashes, so it is reported as
ADVISORY and does not fail the build.

READ-ONLY. This gate writes nothing, has no baseline, and takes no allowlist.
Its correct answer is zero, and a zero is only trustworthy if the detector is
known to work -- so --self-check runs both classifiers against known-bad and
known-good input, and the gate refuses to report a clean result if that fails.

Usage:
    python scripts/scan_ci_shell_command_integrity.py            # gate
    python scripts/scan_ci_shell_command_integrity.py --self-check
    python scripts/scan_ci_shell_command_integrity.py --advisory # + doc hits
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

RUN_KEY = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+)?run:\s*[|>][-+]?\s*$")
CALL = re.compile(r"manage\.py\s+test\b(?P<rest>[^\r\n|;&]*)")

# Flags that consume the following token, so it is not a test label.
FLAG_TAKES_VALUE = {
    "--settings", "--tag", "--exclude-tag", "--parallel", "--pattern", "-p",
    "-v", "--verbosity", "--testrunner", "--shuffle", "--durations", "-k",
    "--debug-sql", "--database",
}

EXECUTED_SUFFIXES = {".sh", ".ps1", ".bat"}
WORKFLOW_DIR = ".github/workflows"
DOC_SUFFIXES = {".md", ".rst", ".txt"}


# --------------------------------------------------------------- classifiers --
def is_bare(rest: str) -> bool:
    """True when no positional test label follows `manage.py test`."""
    toks = rest.split()
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok.startswith("-"):
            i += 2 if (tok in FLAG_TAKES_VALUE and "=" not in tok) else 1
            continue
        return False
    return True


def join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """Fold `... \\` + newline into one logical line, keeping its first line no."""
    out: list[tuple[int, str]] = []
    buf: str | None = None
    start = 0
    for n, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if buf is None:
            buf, start = "", n
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append((start, buf + line))
        buf = None
    if buf is not None:
        out.append((start, buf))
    return out


def truncated_continuations(block: list[str]) -> list[int]:
    """0-based indices in `block` whose continuation is killed by a blank line."""
    hits = [
        i for i, line in enumerate(block[:-1])
        if line.rstrip().endswith("\\") and not block[i + 1].strip()
    ]
    if block and block[-1].rstrip().endswith("\\"):
        hits.append(len(block) - 1)
    return hits


def run_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Every YAML `run: |` block as (1-based line no of its first body line, body)."""
    lines = text.splitlines()
    out: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lines):
        m = RUN_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        base = len(m.group("indent")) + (2 if m.group("dash") else 0)
        body, j = [], i + 1
        while j < len(lines):
            nxt = lines[j]
            if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= base:
                break
            body.append(nxt)
            j += 1
        out.append((i + 2, body))
        i = j
    return out


# -------------------------------------------------------------- self-check ----
SELF_CHECK = [
    # (label, text, expect_truncations, expect_bare)
    (
        "blank line kills the continuation",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python x \\\n\n            y\n",
        1, 0,
    ),
    (
        "well-formed continuation",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python x \\\n            y\n",
        0, 0,
    ),
    (
        "bare manage.py test",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python manage.py test --noinput -v 0\n",
        0, 1,
    ),
    (
        "tag without a discovery root is still bare",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python manage.py test --tag=x --noinput\n",
        0, 1,
    ),
    (
        "scoped invocation",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python manage.py test apps --settings=config.settings\n",
        0, 0,
    ),
    (
        "scoped across a continuation",
        "jobs:\n  a:\n    steps:\n      - run: |\n          python manage.py test \\\n            apps config\n",
        0, 0,
    ),
]


def analyse_yaml(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    trunc: list[tuple[int, str]] = []
    bare: list[tuple[int, str]] = []
    for first_line, body in run_blocks(text):
        for k in truncated_continuations(body):
            trunc.append((first_line + k, body[k].strip()[:100]))
        for off, logical in join_continuations(body):
            stripped = logical.lstrip()
            if stripped.startswith("#"):
                continue
            m = CALL.search(logical)
            if m and is_bare(m.group("rest")):
                bare.append((first_line + off - 1, logical.strip()[:100]))
    return trunc, bare


def self_check() -> bool:
    ok = True
    for label, text, want_trunc, want_bare in SELF_CHECK:
        trunc, bare = analyse_yaml(text)
        got = (len(trunc), len(bare))
        want = (want_trunc, want_bare)
        mark = "ok  " if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  [{mark}] {label:<45} truncations/bare = {got}, expected {want}")
    return ok


# --------------------------------------------------------------------- scan ---
def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return proc.stdout.splitlines()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-check", action="store_true",
                    help="prove both classifiers against known input and exit")
    ap.add_argument("--advisory", action="store_true",
                    help="also scan docs and docstrings (adds ~11s; never fails "
                         "the gate, so it is off by default)")
    args = ap.parse_args()

    print("detector self-check (a zero is worthless without it):")
    passed = self_check()
    print()
    if not passed:
        print("SELF-CHECK FAILED -- refusing to report a scan result.")
        return 2
    if args.self_check:
        print("CI_SHELL_COMMAND_INTEGRITY_SELFCHECK_PASS")
        return 0

    trunc_hits: list[tuple[str, int, str]] = []
    bare_hits: list[tuple[str, int, str]] = []
    advisory: list[tuple[str, int, str]] = []

    for rel in tracked_files():
        path = REPO / rel
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        in_workflows = rel.replace("\\", "/").startswith(WORKFLOW_DIR)
        # Docs and .py docstrings can only ever produce ADVISORY hits, and
        # reading 8,000 Python files to find them costs ~11s of the gate's ~12s.
        # A pre-push hook that already runs 45 gates cannot spend that on output
        # nobody blocks on, so the advisory sweep is opt-in.
        if not args.advisory and not in_workflows and suffix not in EXECUTED_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if in_workflows and suffix in {".yml", ".yaml"}:
            trunc, bare = analyse_yaml(text)
            trunc_hits += [(rel, n, s) for n, s in trunc]
            bare_hits += [(rel, n, s) for n, s in bare]
            continue

        lines = text.splitlines()
        if suffix in EXECUTED_SUFFIXES:
            for k in truncated_continuations(lines):
                trunc_hits.append((rel, k + 1, lines[k].strip()[:100]))
            for n, logical in join_continuations(lines):
                if logical.lstrip().startswith("#"):
                    continue
                m = CALL.search(logical)
                if m and is_bare(m.group("rest")):
                    bare_hits.append((rel, n, logical.strip()[:100]))
        elif suffix in DOC_SUFFIXES or suffix == ".py":
            for n, logical in join_continuations(lines):
                m = CALL.search(logical)
                if m and is_bare(m.group("rest")):
                    advisory.append((rel, n, logical.strip()[:100]))

    print(f"truncated shell continuations (executed) .... {len(trunc_hits)}")
    for rel, n, s in trunc_hits:
        print(f"    {rel}:{n}  {s}")
    print(f"bare `manage.py test` (executed) ............ {len(bare_hits)}")
    for rel, n, s in bare_hits:
        print(f"    {rel}:{n}  {s}")
    if args.advisory:
        print(f"bare `manage.py test` in docs/docstrings .... {len(advisory)} (advisory)")
        for rel, n, s in advisory:
            print(f"    {rel}:{n}  {s}")
    else:
        print("bare `manage.py test` in docs/docstrings .... not scanned "
              "(pass --advisory)")

    if trunc_hits or bare_hits:
        print()
        print("FAIL: a command above cannot run what it names.")
        print("  * truncated continuation -> delete the blank line after the backslash")
        print("  * bare `manage.py test`  -> add discovery roots, e.g. "
              "`test apps config services payment.tests emis.tests`")
        return 1

    print()
    print("CI_SHELL_COMMAND_INTEGRITY_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
