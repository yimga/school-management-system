#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Refuse a CI step whose exit code is pinned to success.

A GitHub Actions step fails when its shell exits non-zero. Anything that
guarantees a zero exit makes the step -- and every gate inside it -- unable
to report a failure, while still drawing a green check. Found repeatedly in
this repo, most recently on 2026-09-02:

  * `pip install -r requirements.txt 2>/dev/null || pip install django` --
    the whole environment silently degraded to 2 packages instead of 68, and
    `2>/dev/null` deleted the reason.
  * `pip-audit ... --strict || true` -- `--strict` asks pip-audit to exit
    non-zero and the next token throws that away.
  * `npx playwright test help-center-crawl.spec.js || echo "Lane 2 e2e
    skipped/failed"` -- under a comment that read "Enforcing since
    2026-08-22". The comment was right about the intent and wrong about the
    file: the browser lane had never been able to fail.

WHAT IS A FINDING. Only the shape that actually pins the exit code:

  1. The LAST effective command of a step's shell -- blank lines, comment
     lines and `\\` continuations folded away -- ends in `|| true`, `|| :`,
     `|| exit 0`, or `|| echo ...`. The shell's exit status IS that
     command's, so the step is structurally incapable of failing.
  2. `continue-on-error: true` on a step or a job.

WHAT IS NOT A FINDING, deliberately, so that this gate needs no allowlist:

  * A swallow that is not last. `kill "$(cat pid)" 2>/dev/null || true`
    followed by `exit 1`, or `code=$(curl ... || echo "000")` inside a
    readiness poll whose loop or whose next step does the enforcing, leaves
    the step's exit code determined by something real.
  * A swallow inside an `if`/`else` whose block ends in `fi`. A tiered gate
    that warns on one branch and enforces on the other (see
    lighthouse-tenant-ci.yml and `vars.LHCI_TENANT_STRICT`) is a design, not
    a defect.
  * `cmd || other-cmd` where the fallback is real work (`npm ci || npm
    install`, `psql -c ... || psql -c "CREATE ROLE ..."`). That shape does
    hide the first command's failure and is worth human review, but it is
    sometimes a correct idempotent idiom, and a gate that cannot tell them
    apart would need an allowlist -- which is the thing this class of defect
    hides behind.

READ-ONLY. No baseline, no allowlist, nothing to edit when it goes red. Its
correct answer is zero, and a zero is only worth anything if the detector is
known to work, so --self-check runs the classifier over known-bad and
known-good input and the gate refuses to report a clean result if that fails.

Usage:
    python scripts/scan_workflow_swallowed_exit_codes.py
    python scripts/scan_workflow_swallowed_exit_codes.py --self-check
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ".github/workflows"

# `run: |`, `run: >`, `- run: |`  -- a block scalar whose body follows.
RUN_BLOCK = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+)?run:\s*[|>][-+]?\s*$")
# `run: some command`  -- a one-line scalar; the command IS the whole shell.
RUN_INLINE = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s+)?run:\s*(?P<cmd>\S.*)$")
CONTINUE_ON_ERROR = re.compile(r"^\s*continue-on-error:\s*(?P<value>\S.*?)\s*$")

# Terminators that pin the shell's exit status to 0.
SWALLOW_TAIL = re.compile(
    r"\|\|\s*(?:true\b|:\s*$|exit\s+0\b|echo\b)",
)


def fold_continuations(body: list[str]) -> list[tuple[int, str]]:
    """Fold `... \\` + newline into one logical line, keeping its first line no."""
    out: list[tuple[int, str]] = []
    buf: str | None = None
    start = 0
    for n, raw in enumerate(body):
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


def last_effective(body: list[str]) -> tuple[int, str] | None:
    """The last logical shell command in a run block, or None if there is none."""
    for offset, logical in reversed(fold_continuations(body)):
        stripped = logical.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return offset, stripped
    return None


def run_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Every `run: |` block as (1-based line no of its first body line, body)."""
    lines = text.splitlines()
    out: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lines):
        m = RUN_BLOCK.match(lines[i])
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


def inline_runs(text: str) -> list[tuple[int, str]]:
    """Every one-line `run: cmd` as (1-based line no, command)."""
    out: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if RUN_BLOCK.match(line):
            continue
        m = RUN_INLINE.match(line)
        if m:
            out.append((n, m.group("cmd").strip()))
    return out


def analyse(text: str) -> list[tuple[int, str, str]]:
    """(line no, kind, evidence) for every step whose exit code is pinned to 0."""
    hits: list[tuple[int, str, str]] = []

    for first_line, body in run_blocks(text):
        tail = last_effective(body)
        if tail is None:
            continue
        offset, command = tail
        if SWALLOW_TAIL.search(command):
            hits.append((first_line + offset, "swallow-on-last-command", command[:140]))

    for line_no, command in inline_runs(text):
        if SWALLOW_TAIL.search(command):
            hits.append((line_no, "swallow-on-inline-run", command[:140]))

    for n, line in enumerate(text.splitlines(), 1):
        m = CONTINUE_ON_ERROR.match(line)
        if m and m.group("value").strip().strip("\"'").lower() != "false":
            hits.append((n, "continue-on-error", line.strip()[:140]))

    return sorted(hits)


# -------------------------------------------------------------- self-check ----
def _wf(body: str) -> str:
    return "jobs:\n  a:\n    steps:\n" + body


SELF_CHECK: list[tuple[str, str, int]] = [
    (
        "swallow on the last line of a run block",
        _wf("      - run: |\n          npx playwright test spec.js || echo \"skipped\"\n"),
        1,
    ),
    (
        "swallow on a one-line run scalar",
        _wf("      - run: chromedriver --version || true\n"),
        1,
    ),
    (
        "|| true before a real command is NOT a finding",
        _wf("      - run: |\n          ls -la dist/ || true\n          test -f dist/app.zip\n"),
        0,
    ),
    (
        "cleanup swallow before exit 1 is NOT a finding",
        _wf("      - run: |\n          kill \"$(cat /tmp/x.pid)\" 2>/dev/null || true\n          exit 1\n"),
        0,
    ),
    (
        "poll sentinel inside a loop is NOT a finding",
        _wf(
            "      - run: |\n          for i in 1 2 3; do\n"
            "            code=$(curl -s -o /dev/null -w '%{http_code}' http://x/ || echo \"000\")\n"
            "            [ \"$code\" = 200 ] && break\n          done\n"
            "          npx playwright test spec.js\n"
        ),
        0,
    ),
    (
        "tiered gate ending in fi is NOT a finding",
        _wf(
            "      - run: |\n          if [ \"$STRICT\" = 1 ]; then\n            lhci autorun\n"
            "          else\n            lhci autorun || echo \"::warning::below budget\"\n"
            "          fi\n"
        ),
        0,
    ),
    (
        "a trailing comment does not hide the swallow",
        _wf("      - run: |\n          pytest tests/ || true\n          # done\n"),
        1,
    ),
    (
        "a swallow folded across a continuation is still last",
        _wf("      - run: |\n          pip-audit --requirement requirements.txt \\\n            --strict || true\n"),
        1,
    ),
    (
        "|| { ...; exit 1; } is enforcing, NOT a finding",
        _wf("      - run: |\n          bandit -r apps || { echo \"::error::HIGH findings\"; exit 1; }\n"),
        0,
    ),
    (
        "npm ci || npm install is out of scope by design",
        _wf("      - run: npm ci || npm install --no-audit --no-fund\n"),
        0,
    ),
    ("continue-on-error: true", _wf("      - run: pytest\n        continue-on-error: true\n"), 1),
    ("continue-on-error: false", _wf("      - run: pytest\n        continue-on-error: false\n"), 0),
    ("a clean step", _wf("      - run: |\n          pytest tests/\n"), 0),
]


def self_check() -> bool:
    ok = True
    for label, text, want in SELF_CHECK:
        got = len(analyse(text))
        mark = "ok  " if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  [{mark}] {label:<52} findings = {got}, expected {want}")
    return ok


# --------------------------------------------------------------------- scan ---
def tracked_workflows() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "--", WORKFLOW_DIR],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        p for p in proc.stdout.splitlines()
        if p.endswith((".yml", ".yaml"))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    print("detector self-check (a zero is worthless from a broken detector):")
    if not self_check():
        print("\nSELF-CHECK FAILED -- refusing to report a scan result.")
        return 2
    if args.self_check:
        print("\nWORKFLOW_SWALLOWED_EXIT_CODES_SELFCHECK_PASS")
        return 0

    files = tracked_workflows()
    findings: list[tuple[str, int, str, str]] = []
    for rel in files:
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        for line_no, kind, evidence in analyse(text):
            findings.append((rel, line_no, kind, evidence))

    print(f"\nscanned {len(files)} workflow file(s) under {WORKFLOW_DIR}")
    if findings:
        print("\nsteps whose exit code is pinned to success:")
        for rel, line_no, kind, evidence in findings:
            print(f"  {rel}:{line_no}  [{kind}]")
            print(f"      {evidence}")
        print(
            f"\nWORKFLOW_SWALLOWED_EXIT_CODES_FAIL ({len(findings)} step(s) cannot "
            "report a failure)"
        )
        print(
            "Fix the step so its exit code is real. If the swallow is diagnostic, "
            "move it so it is not the last command."
        )
        return 1

    print("\nWORKFLOW_SWALLOWED_EXIT_CODES_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
