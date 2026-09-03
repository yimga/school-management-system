#!/usr/bin/env python3
"""Run the gates that CI names but nothing local executes.

WHY THIS EXISTS
---------------
``scripts/pre_push_boundary_check.py`` runs a curated set of gates before every
push. The GitHub workflows under ``.github/workflows/`` name a far larger set --
several hundred scripts -- and those run ONLY in Actions. Actions has executed
nothing since 2026-08-15 (billing), so every gate in the difference between those
two sets has been running nowhere at all. That is not a theoretical gap: sweeping
it by hand on 2026-09-03 found two new RLS bypasses on main, a help-centre gate
red since a nav refactor moved its needle, and two gates asserting CI jobs that a
108-jobs-to-2 consolidation had removed.

This script closes the loop locally: discover what CI names, subtract what the
pre-push runner already covers, execute the remainder the way CI invokes it, and
classify the results.

A TRIGGER IS NOT A RUNNER
-------------------------
The whole point is execution, so "did it run" is recorded separately from "did it
pass". A gate that could not start (missing file, import error, no interpreter) is
NOT_RUN, never GREEN -- a zero from something that never executed is the exact lie
this script exists to prevent. Every row carries the command, the duration and the
output tail, so a green is auditable rather than asserted.

INVOCATION MATTERS
------------------
Gates are run with the arguments the workflow passes them, not bare. 17 of them
take flags (``--compare``, ``--write``, ``--strict``, ``--app-base``), and running
those bare over-reports badly: on the first hand sweep, 12 gates that looked red
turned green once invoked correctly.

USAGE
    python scripts/run_ci_only_gates_locally.py --list
    python scripts/run_ci_only_gates_locally.py --self-test
    python scripts/run_ci_only_gates_locally.py [--timeout 300] [--jobs 1]
    python scripts/run_ci_only_gates_locally.py --compare
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PRE_PUSH = ROOT / "scripts" / "pre_push_boundary_check.py"
REPORT = ROOT / "var" / "ci-only-gate-status.json"

#: A gate invocation as written in a workflow: `python scripts/<name>.py [args]`.
_INVOCATION = re.compile(
    r"python[3]?\s+(scripts/[A-Za-z0-9_]+\.py)([^\n\r|;&]*)"
)

#: Output shapes that mean "this needs something the local box does not have",
#: which is a different answer from "the repo is broken". Matched case-folded.
_ENV_SHAPES = (
    "error: argument",
    "the following arguments are required",
    "no such file or directory: 'node'",
    "'npx' is not recognized",
    "'node' is not recognized",
    "connection refused",
    "failed to establish a new connection",
    "max retries exceeded",
    "missing artifacts/",
    "playwright",
    "chromium",
)


class Result:
    __slots__ = ("script", "args", "executed", "status", "code", "seconds", "tail")

    def __init__(self, script, args, executed, status, code, seconds, tail):
        self.script = script
        self.args = args
        self.executed = executed
        self.status = status
        self.code = code
        self.seconds = seconds
        self.tail = tail

    def as_dict(self) -> dict:
        return {
            "script": self.script,
            "args": self.args,
            "executed": self.executed,
            "status": self.status,
            "exit_code": self.code,
            "seconds": self.seconds,
            "tail": self.tail,
        }


def workflow_invocations() -> dict[str, str]:
    """Every `python scripts/X.py <args>` CI names, best args per script.

    A script invoked several ways keeps the invocation with the most arguments --
    the richer form is the one that exercises it, and a bare call alongside a
    flagged call is usually a lint or a --help.
    """
    found: dict[str, str] = {}
    if not WORKFLOWS.is_dir():
        return found
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8", errors="replace")
        for rel, args in _INVOCATION.findall(text):
            name = Path(rel).name
            # Strip YAML quoting that bleeds in when the workflow writes the command
            # as a quoted scalar: a trailing '",' arrived as a literal argument, the
            # gate rejected it, and that reads as a repo failure when it is ours.
            args = " ".join(args.split()).rstrip(",\"'")
            if name not in found or len(args) > len(found[name]):
                found[name] = args
    return found


def pre_push_covered() -> set[str]:
    """Script filenames the pre-push runner already executes."""
    if not PRE_PUSH.is_file():
        return set()
    text = PRE_PUSH.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"[A-Za-z0-9_]+\.py", text))


def discover() -> list[tuple[str, str]]:
    """CI-named gates that the pre-push runner does NOT cover, and that exist."""
    covered = pre_push_covered()
    out = []
    for name, args in sorted(workflow_invocations().items()):
        if name in covered:
            continue
        if not (ROOT / "scripts" / name).is_file():
            continue
        out.append((name, args))
    return out


def is_test_suite_runner(name: str) -> bool:
    """True if this script's job is to RUN THE TEST SUITE, not to assert a property.

    `run_sqlite_memory_tests.py` and `run_50_app_test_shards.py` shell out to
    `manage.py test` over dozens of modules. They are not gates -- they are the test
    suite wearing a script name -- and sweeping them here both takes hours and
    conflates "a property is violated" with "a test failed". They are reported as
    their own class so the number is visible rather than silently dropped.
    """
    src_path = ROOT / "scripts" / name
    try:
        src = src_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    markers = ("manage.py", "DiscoverRunner", "-m pytest", "call_command(\"test\"")
    return sum(m in src for m in markers) > 0 and name.startswith("run_")


#: argparse usage errors -- this runner's invocation is wrong, not the repo.
_BAD_INVOCATION = (
    "error: unrecognized arguments",
    "error: argument",
    "error: invalid choice",
)


def classify(code: int, out: str, timed_out: bool) -> tuple[bool, str]:
    """(executed, status). NOT_RUN is never GREEN."""
    if timed_out:
        return True, "TIMEOUT"
    low = out.lower()
    if code == 0:
        return True, "GREEN"
    # Checked BEFORE the env shapes and before RED. A usage error means the runner
    # handed the gate arguments it does not accept, so the gate never judged anything.
    # Counting that as a repo finding is how a triage stops being believed.
    if "usage:" in low and any(shape in low for shape in _BAD_INVOCATION):
        return True, "BAD_INVOCATION"
    # Could the interpreter even start it?
    if "no such file or directory" in low and ".py" in low:
        return False, "NOT_RUN"
    if "modulenotfounderror" in low or "importerror" in low:
        return False, "NOT_RUN"
    if any(shape in low for shape in _ENV_SHAPES):
        return True, "NEEDS_ENV"
    return True, "RED"


def run_one(name: str, args: str, timeout: int) -> Result:
    cmd = [sys.executable, str(ROOT / "scripts" / name)] + args.split()
    started = time.time()
    timed_out = False
    # Popen + explicit TREE kill. subprocess.run(timeout=...) kills only the direct
    # child, and a gate that spawns a Django test runner leaves a grandchild holding
    # the stdout pipe -- so the reader then blocks forever waiting for an EOF that
    # never comes. Measured: this hung the sweep at gate 38 for 10+ minutes on a
    # 240s timeout, which is exactly the "looks like a hang" failure this repo has
    # been bitten by before.
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        code = 124
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, check=False,
            )
        else:
            proc.kill()
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out = ""
    seconds = round(time.time() - started, 1)
    executed, status = classify(code, out, timed_out)
    lines = [
        ln for ln in out.splitlines()
        if ln.strip() and not re.match(r"^(INFO|WARNING|DEBUG)\s", ln)
    ]
    return Result(name, args, executed, status, code, seconds, lines[-1][:200] if lines else "")


def self_test() -> int:
    """Prove the reader and the classifier before believing any result.

    A discovery pass that silently finds nothing, or a classifier that calls a
    crash GREEN, would make this whole script a very convincing zero.
    """
    failures = []

    found = workflow_invocations()
    if len(found) < 50:
        failures.append(f"workflow reader found only {len(found)} invocations; expected 50+")
    if not any(a for a in found.values()):
        failures.append("workflow reader recovered no ARGUMENTS from any invocation")

    covered = pre_push_covered()
    if len(covered) < 20:
        failures.append(f"pre-push reader found only {len(covered)} scripts; expected 20+")

    gates = discover()
    if not gates:
        failures.append("discovery returned zero gates")
    for name, _ in gates:
        if name in covered:
            failures.append(f"{name} is pre-push covered and should not be in the CI-only set")
            break

    cases = [
        ((0, "all good", False), (True, "GREEN")),
        ((1, "verify_x: FAIL - a real assertion", False), (True, "RED")),
        ((2, "error: argument --app-base is required", False), (True, "NEEDS_ENV")),
        ((1, "ModuleNotFoundError: No module named 'x'", False), (False, "NOT_RUN")),
        ((124, "", True), (True, "TIMEOUT")),
        ((2, "usage: g [-h]\ng: error: unrecognized arguments: --apply", False),
         (True, "BAD_INVOCATION")),
    ]
    for (code, out, to), want in cases:
        got = classify(code, out, to)
        if got != want:
            failures.append(f"classify({code!r}, {out[:24]!r}) = {got}, want {want}")

    for line in failures:
        print(f"SELF-TEST FAIL: {line}")
    if failures:
        return 1
    print(
        f"self-test OK: {len(found)} workflow invocations, {len(covered)} pre-push covered, "
        f"{len(gates)} CI-only gates, classifier correct on {len(cases)} cases"
    )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show what would run")
    ap.add_argument("--self-test", action="store_true", help="prove the reader/classifier")
    ap.add_argument("--timeout", type=int, default=300, help="per-gate seconds")
    ap.add_argument("--only", default="", help="substring filter")
    ap.add_argument(
        "--include-test-runners", action="store_true",
        help="also run the scripts that shell out to the Django test suite",
    )
    ap.add_argument("--compare", action="store_true", help="fail on NEW reds vs the report")
    ap.add_argument("--write", action="store_true", help="write the report")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    all_gates = [g for g in discover() if args.only in g[0]]
    suite_runners = [g for g in all_gates if is_test_suite_runner(g[0])]
    gates = (all_gates if args.include_test_runners
             else [g for g in all_gates if not is_test_suite_runner(g[0])])
    if args.list:
        for name, a in gates:
            print(f"  {name} {a}".rstrip())
        print(f"{len(gates)} CI-only gate(s)")
        if suite_runners and not args.include_test_runners:
            print(f"  (+{len(suite_runners)} test-suite runner(s) held back; "
                  f"--include-test-runners to run them)")
            for n, _ in suite_runners:
                print(f"    TEST_SUITE {n}")
        return 0

    if self_test() != 0:
        print("refusing to report results from an unproven reader", file=sys.stderr)
        return 2

    results = []
    for i, (name, a) in enumerate(gates, 1):
        r = run_one(name, a, args.timeout)
        results.append(r)
        print(f"[{i}/{len(gates)}] {r.status:<9} {name} {a}".rstrip(), flush=True)

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("\n=== summary ===")
    for k in ("GREEN", "RED", "NEEDS_ENV", "BAD_INVOCATION", "TIMEOUT", "NOT_RUN"):
        print(f"  {k:<10} {counts.get(k, 0)}")
    ran = sum(1 for r in results if r.executed)
    print(f"  executed   {ran}/{len(results)}  (NOT_RUN is never counted as green)")
    if suite_runners and not args.include_test_runners:
        print(f"  TEST_SUITE {len(suite_runners)} held back (they run the suite, "
              "not a property); --include-test-runners to sweep them too")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "counts": counts,
        "executed": ran,
        "total": len(results),
        "results": [r.as_dict() for r in results],
    }
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {REPORT.relative_to(ROOT).as_posix()}")

    if args.compare and REPORT.is_file():
        known = {
            r["script"] for r in json.loads(REPORT.read_text(encoding="utf-8")).get("results", [])
            if r["status"] in ("RED", "NOT_RUN")
        }
        new = sorted(
            r.script for r in results
            if r.status in ("RED", "NOT_RUN") and r.script not in known
        )
        if new:
            print("\nNEW failing CI-only gate(s):")
            for n in new:
                print(f"  {n}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
