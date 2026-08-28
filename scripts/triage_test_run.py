#!/usr/bin/env python
"""Split a red test run into KNOWN reds and NEW ones, so a red suite is readable.

WHY THIS EXISTS
---------------
A full run here is red, and has been for a while, for reasons that are written
down in three different places and nowhere the runner can see:

  * ~10 Migration Cloud failures caused by the local environment,
  * ~5 finance/academics failures verified pre-existing at HEAD,
  * AI draft tests that assert on live Ollama prose and flip at the SAME commit.

The consequence is that "the suite is red" carries no information. Every agent
who runs it re-derives the same triage by hand, and the only thing standing
between a real regression and a shrug is somebody remembering which reds are
old. That is a runbook, and a runbook is a bug.

This reads a run's output, matches each failure against a registry of reds that
have already been explained, and answers the only question that matters: **did
anything NEW break?**

WHAT IT WILL NOT DO
-------------------
Silence things. Three rules keep it from becoming a place to hide failures:

  * Every entry needs a ``reason`` and a ``class``. No blank cheques.
  * Only ``env`` and ``nondeterministic`` are tolerated silently. ``product``
    (a deferred bug) and ``unclassified`` (nobody has established the cause)
    are reported loudly and still FAIL the run unless
    ``--allow-known-unfixed`` is passed. Recording a red is not the same as
    accepting it.
  * An entry whose test PASSED is reported as STALE. The list is a burndown,
    and a red that got fixed must leave it -- otherwise the registry slowly
    becomes a list of tests nobody checks.

USAGE
-----
    python manage.py test ... > run.log 2>&1
    python scripts/triage_test_run.py run.log
    python scripts/triage_test_run.py run.log --record --reason "..." --class env
    python scripts/triage_test_run.py run.log --json

Exit 0 when every failure is a known env/nondeterministic red and nothing is
stale. Exit 1 on a NEW failure, a known-product red, or a stale entry.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "var" / "known-red-tests.json"

VALID_CLASSES = ("env", "nondeterministic", "product", "unclassified")
# Only these two are tolerated silently. "product" is a deferred bug and
# "unclassified" means nobody has established the cause yet -- both are real
# work, and a tool that shrugged at them would be the problem it was built to
# solve.
TOLERATED_CLASSES = ("env", "nondeterministic")

# unittest: "FAIL: test_x (module.Class.test_x)" / "ERROR: ..."
_UNITTEST = re.compile(r"^(FAIL|ERROR):\s+(\S+)\s+\(([^)]+)\)", re.M)
# pytest short summary: "FAILED path/to/test_x.py::Class::test_y - msg"
_PYTEST = re.compile(r"^(FAILED|ERROR)\s+(\S+::\S+)", re.M)
_RAN = re.compile(r"^Ran (\d+) tests? in", re.M)


def parse_failures(text: str) -> list[dict[str, str]]:
    """Every failing test id in a run log, however the runner spelled it."""
    found: dict[str, dict[str, str]] = {}
    for kind, _short, dotted in _UNITTEST.findall(text):
        found[dotted] = {"test": dotted, "kind": kind}
    for kind, nodeid in _PYTEST.findall(text):
        found[nodeid] = {"test": nodeid, "kind": kind}
    return sorted(found.values(), key=lambda f: f["test"])


def load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {"rule": "", "tests": {}}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rule": "", "tests": {}}


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8"
    )


def registry_problems(registry: dict) -> list[str]:
    problems = []
    for test, entry in sorted(registry.get("tests", {}).items()):
        if not isinstance(entry, dict):
            problems.append(f"{test}: entry must be an object")
            continue
        if not entry.get("reason"):
            problems.append(f"{test}: no reason. A known red without a reason is a shrug.")
        if entry.get("class") not in VALID_CLASSES:
            problems.append(
                f"{test}: class must be one of {', '.join(VALID_CLASSES)}, got {entry.get('class')!r}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", help="run output to read (default: stdin)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--record",
        action="store_true",
        help="add every unregistered failure in this log to the registry",
    )
    parser.add_argument("--reason", help="reason to record with --record")
    parser.add_argument(
        "--class",
        dest="klass",
        choices=VALID_CLASSES,
        help="class to record with --record",
    )
    parser.add_argument(
        "--allow-known-unfixed",
        action="store_true",
        help="do not fail on registered product/unclassified reds. They are still "
        "real work; this only says you already knew about them.",
    )
    parser.add_argument(
        "--scope",
        help="only consider tests whose id starts with this, so a partial run does "
        "not report every other known red as stale",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    text = Path(args.log).read_text(encoding="utf-8", errors="replace") if args.log else sys.stdin.read()
    failures = parse_failures(text)
    ran = _RAN.search(text)
    registry = load_registry()
    known = registry.get("tests", {})

    if args.record:
        if not args.reason or not args.klass:
            print("--record needs both --reason and --class", file=sys.stderr)
            return 2
        added = 0
        for failure in failures:
            if failure["test"] in known:
                continue
            known[failure["test"]] = {
                "reason": args.reason,
                "class": args.klass,
                "kind": failure["kind"],
            }
            added += 1
        registry["tests"] = known
        registry.setdefault(
            "rule",
            "A test here is red for a reason that is written down. env and "
            "nondeterministic are tolerated; product is a deferred bug and still "
            "fails unless --allow-known-product. An entry whose test passes is STALE "
            "and must be removed.",
        )
        save_registry(registry)
        print(f"recorded {added} new entry(ies) -> {REGISTRY_PATH}")
        return 0

    in_scope = lambda t: (not args.scope) or t.startswith(args.scope)  # noqa: E731
    failed_ids = {f["test"] for f in failures}
    new = [f for f in failures if f["test"] not in known]
    known_hit = [f for f in failures if f["test"] in known]
    unfixed = [
        f for f in known_hit
        if known[f["test"]].get("class") not in TOLERATED_CLASSES
    ]
    stale = sorted(t for t in known if in_scope(t) and t not in failed_ids)
    problems = registry_problems(registry)

    if args.json:
        print(json.dumps({
            "ran": int(ran.group(1)) if ran else None,
            "failures": len(failures),
            "new": [f["test"] for f in new],
            "known": [f["test"] for f in known_hit],
            "known_unfixed": [f["test"] for f in unfixed],
            "stale": stale,
            "registry_problems": problems,
        }, indent=2, sort_keys=True))
    else:
        print(f"tests run     : {ran.group(1) if ran else 'unknown'}")
        print(f"failures      : {len(failures)}")
        print(f"  known       : {len(known_hit)}")
        print(f"  NEW         : {len(new)}")
        if unfixed:
            print(f"  unfixed     : {len(unfixed)}  (product or unclassified -- real work, not environment)")
        if new:
            print("\nNEW failures -- nothing explains these:")
            for failure in new:
                print(f"  {failure['kind']}  {failure['test']}")
        if unfixed:
            print()
            print("known but UNFIXED (product bugs, or causes nobody has established):")
            for failure in unfixed:
                entry = known[failure["test"]]
                print(f"  [{entry['class']}] {failure['test']}")
        if stale:
            print(f"\nSTALE registry entries -- these PASSED, remove them ({len(stale)}):")
            for test in stale:
                print(f"  {test}")
        if problems:
            print("\nregistry problems:")
            for problem in problems:
                print(f"  {problem}")
        if not (new or stale or problems or (unfixed and not args.allow_known_unfixed)):
            print("\nEvery failure is a known env/nondeterministic red. Nothing new broke.")

    bad = bool(new or stale or problems or (unfixed and not args.allow_known_unfixed))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
