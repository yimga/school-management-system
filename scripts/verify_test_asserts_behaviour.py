#!/usr/bin/env python
"""Meta-gate: prove a test still FAILS when the behaviour it names is removed.

WHY THIS EXISTS
---------------
``verify_gates_can_fail.py`` asks whether a GATE can fail. This asks the same
question one layer down, of the TESTS, and it is the same failure every time:
something asserted the WORD and not the BEHAVIOUR.

A test that reads a template's SOURCE and asserts a substring cannot tell markup
that renders from markup that has been moved inside ``{% comment %}``. The bytes
are identical; the page is not. The test is green either way, so it protects
nothing -- and reads exactly like coverage while doing it.

A static scanner cannot settle this. "Asserting that a partial is included or a
CSS class is defined" is sometimes a legitimate source contract, and the property
that separates the two is "does it still pass once the behaviour is gone" --
a MUTATION property. So this mutates.

MEASURED 2026-08-31 on a stratified sample of 42 tests over 26 files in 12 apps,
drawn from the 1,232 tests that read a file, assert a substring on it, and name a
``.html``:

    VACUOUS  18 / 27 measurable  (67%)

Extrapolated that is ~825 tests platform-wide, which is an ESTIMATE from 27
measurements and is deliberately not what this gate ratchets (see RATCHET).

THE MUTATION, AND THE TWO WRONG ONES
------------------------------------
Getting this right took three attempts, and the two wrong ones are recorded here
because both look correct and both produce a number:

  1. Delete the needle, re-add it inside a comment.        -> 83%  TOO HIGH
     Over-counts a RENDERING test whose needle also arrives from its own context:
     a wizard stage literally named "Configure" is still on the page, so the test
     passes for a legitimate reason and gets scored vacuous.

  2. Empty the file, preserve only the SAMPLED needle.     -> 54%  TOO LOW
     Under-counts a SOURCE test that asserts a SECOND needle from the same file:
     that needle is gone from the bytes, so the test fails for a reason that has
     nothing to do with rendering.

  3. Empty the file, preserve EVERY needle the test asserts is present. -> 67%
     Now both properties hold at once: every string a source reader looks for is
     still in the bytes, and nothing the template declared renders. A test that
     still passes cannot be reading the output.

That is ``_vacuous_body()`` below, and the reasoning is here so the next person
cannot regress it by "simplifying" the mutation.

THE BINDING CONTROL
-------------------
A verdict only means something if the test consults the file that was mutated. A
test module can name a dozen templates, so a test can be paired with one it never
opens -- and "still passes with that template gone" is then trivially true. So
every case is first bound: empty each candidate template with NOTHING preserved;
the one whose emptying makes the test FAIL is the file it reads. A case with no
such file is UNMEASURABLE and is excluded from the rate, never counted as clean.
On the 2026-08-31 sample that excluded 14 of 42 -- most of them read a ``.js`` or
``.css``, which a .html-keyed sampler cannot pair.

RATCHET
-------
The ratchet is the COUNT OF KNOWN-VACUOUS TESTS, never a sampled percentage. A
sampled rate moves on its own -- a different seed, a test renamed, one case
becoming unmeasurable -- and a gate whose number moves without anyone touching
the tree is a gate people learn to ignore. Same reasoning that kept the axe
violation total off its ratchet.

So:

  * ENFORCING, and deterministic: every entry in the baseline is re-measured.
    An entry that is now SOUND is a FINDING -- remove it from the baseline, which
    is how the number goes down. An entry that can no longer be measured (test
    renamed or deleted) is also a finding, so the baseline cannot quietly rot
    into a list of names that no longer exist. And with ``--scope-changed`` any
    test in a CHANGED file that measures vacuous and is not baselined fails:
    deterministic per push, so it cannot flake.

  * REPORT-ONLY: ``--sample N`` discovery over the whole candidate population.
    It prints what it finds and always exits 0. Discovery is how the baseline
    grows, by a human running it and committing the result -- not by a gate
    failing on a random draw.

ISOLATION
---------
Mutations are applied in a DETACHED GIT WORKTREE, reusing
``verify_gates_can_fail.Workspace``. Several agents share this checkout and it
usually carries uncommitted work; planting deliberate defects in it is how you
lose someone else's afternoon. It also makes the restore path non-critical: a
harness killed mid-run damages a scratch directory, not real files.

The worktree is created at HEAD, so UNCOMMITTED test fixes are not in it. Commit
before you expect this gate to see your work.

USAGE
-----
    python scripts/verify_test_asserts_behaviour.py --compare
    python scripts/verify_test_asserts_behaviour.py --compare --scope-changed
    python scripts/verify_test_asserts_behaviour.py --sample 40 --seed 20260831
    python scripts/verify_test_asserts_behaviour.py --list
    python scripts/verify_test_asserts_behaviour.py --all --update-baseline

--update-baseline needs a scope (--all, --sample or --scope-changed). It used
to accept none, which selected nothing, measured nothing and wrote a baseline
of zero -- after which --compare passed forever with the whole population
unmeasured. A harness that reports a clean 0 without measuring is the defect
this one exists to find, so it now refuses instead.

Exit 0 when every baselined test is still vacuous and nothing new is found in
the enforced scope. Exit 1 on a fixed-but-still-baselined entry, a baseline entry
that no longer resolves, or a new vacuous test in a changed file.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

BASELINE_PATH = ROOT / "var" / "security-audit-baseline-test-asserts-behaviour.json"

#: Wall-clock ceiling for the whole in-worktree measurement. A timeout is a
#: resource result, not a finding -- the pre-push runner says the same.
DEFAULT_TIMEOUT_S = 1800

#: Assertions that claim a string IS PRESENT. Only these are preserved by the
#: mutation; an assertNotIn needle is one the test wants ABSENT, and inserting it
#: would fail the test for the opposite of the reason under investigation.
POSITIVE_ASSERTS = frozenset({"assertIn", "assertRegex"})

#: Direct file reads. A test that never opens a file cannot be reading source.
READ_CALLS = frozenset({"read_text", "read_bytes", "open"})

_SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".git", ".venv"})


# ---------------------------------------------------------------------------
# Candidate population: tests that read a file, assert a substring, name a .html
# ---------------------------------------------------------------------------
def _test_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for base in (root / "apps", root / "config"):
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for name in filenames:
                if name.startswith("test_") and name.endswith(".py"):
                    out.append(Path(dirpath) / name)
    return sorted(out)


def _called_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = getattr(child.func, "id", None) or getattr(child.func, "attr", None)
            if name:
                out.add(name)
    return out


def _html_literals(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            value = child.value
            if value.endswith((".html", ".htm")) and " " not in value:
                out.add(value)
    return out


def asserted_needles(fn: ast.FunctionDef) -> list[str]:
    """Every literal this test asserts IS PRESENT.

    Includes the ``for needle in ("a", "b"): self.assertIn(needle, src)`` shape,
    which is common here and invisible to a first-argument-only reader. Missing
    ONE of these is what produced the 54% under-count; see the module docstring.
    """
    out: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in POSITIVE_ASSERTS:
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    out.append(first.value)
        if isinstance(node, (ast.Tuple, ast.List)):
            values = [
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if len(values) >= 2 and all(len(v) >= 4 for v in values):
                out.extend(values)
    return sorted(set(out))


#: Base classes whose tests run without a database. The measurement runs unittest
#: inside the isolated worktree with no test database built, so a TestCase would
#: error for a reason that has nothing to do with the mutation and be scored
#: UNUSABLE. Restricting the population is the honest move: 105 of the 504
#: candidates on 2026-09-01 are TestCase/TransactionTestCase and are OUT OF SCOPE
#: for this gate, not silently clean. Widening it means building a test DB in the
#: worktree, which is a different (and much slower) gate.
DB_FREE_BASES = frozenset({"SimpleTestCase"})


def _db_free_classes(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(b, "id", None) or getattr(b, "attr", None) for b in node.bases}
        if bases & DB_FREE_BASES:
            out.add(node.name)
    return out


def candidates(root: Path, include_db_backed: bool = False) -> list[dict]:
    """Tests that read a file, assert a substring on it, and name a .html."""
    rows: list[dict] = []
    for path in _test_files(root):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        module_html = _html_literals(tree)
        db_free = _db_free_classes(tree)
        rel = str(path.relative_to(root)).replace("\\", "/")
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not include_db_backed and cls.name not in db_free:
                continue
            for fn in cls.body:
                if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith("test")):
                    continue
                names = _called_names(fn)
                if not (names & POSITIVE_ASSERTS) or not (names & READ_CALLS):
                    continue
                html = _html_literals(fn) | module_html
                if not html:
                    continue
                rows.append(
                    {
                        "id": f"{rel[:-3].replace('/', '.')}.{cls.name}.{fn.name}",
                        "file": rel,
                        "module": rel[:-3].replace("/", "."),
                        "templates": sorted(html),
                        "needles": asserted_needles(fn),
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# The measurement. Runs INSIDE the isolated worktree (--in-worktree).
# ---------------------------------------------------------------------------
_BASENAME_INDEX: dict[str, list[Path]] | None = None


def _basename_index(root: Path) -> dict[str, list[Path]]:
    """Every .html under a template root, grouped by bare filename.

    Built once. Tests name a template both ways and the fixed prefixes in
    _resolve_template only reach one of them.
    """
    global _BASENAME_INDEX
    if _BASENAME_INDEX is None:
        idx: dict[str, list[Path]] = {}
        bases = [root / "templates"]
        bases += [
            a / "templates"
            for a in (root / "apps").iterdir()
            if (a / "templates").is_dir()
        ]
        for base in bases:
            if not base.is_dir():
                continue
            for path in base.rglob("*.html"):
                if path.is_file():
                    idx.setdefault(path.name, []).append(path)
        _BASENAME_INDEX = idx
    return _BASENAME_INDEX


def _resolve_template(root: Path, name: str) -> Path | None:
    """Resolve a template literal the way the TESTS write it, not just Django.

    Tests name templates two ways and both must resolve: the loader-relative form
    (``portal_base.html``, ``components/x.html``) and the REPO-relative form
    (``templates/base.html``), which is what a test using pathlib writes. Trying
    only the first put ``templates/templates/base.html`` on disk, found nothing,
    and reported 31 of 35 sampled cases UNMEASURABLE -- a harness saying "I cannot
    see" when the truth was "I looked in the wrong place". That is the exact
    failure this whole gate exists to catch, so it is spelled out here.
    """
    searched = [root / name]
    searched += [root / "templates" / name]
    searched += [
        a / "templates" / name for a in (root / "apps").iterdir() if (a / "templates").is_dir()
    ]
    for candidate in searched:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue

    # Last resort: an UNAMBIGUOUS basename match under any template root.
    # Tests name a template by its bare filename ("login.html") while the
    # file lives in a subdirectory ("templates/auth/login.html"), and none
    # of the three fixed prefixes above can reach it. Measured 2026-09-01:
    # 548 of the 1187 .html literals named by candidate tests did not
    # resolve and 252 methods had nothing resolve at all, every one of
    # which was then reported "reads none of its .html literals". An
    # unmeasurable case is excluded from the rate, so a resolver that
    # cannot see makes this gate look BETTER than it is -- the same
    # mistake, in this same function, that the docstring above records
    # fixing once already.
    #
    # Unambiguous only. login.html matches BOTH templates/admin/login.html
    # and templates/auth/login.html; picking one would empty the wrong file
    # and turn an honest "I cannot tell" into a confident wrong verdict.
    if "/" not in name and "*" not in name:
        matches = _basename_index(root).get(name, [])
        if len(matches) == 1:
            return matches[0]
    return None


def _vacuous_body(original: bytes, needles: list[str]) -> bytes:
    """The mutation: nothing renders, every asserted needle is still in the bytes.

    Both halves matter and neither is optional -- see MUTATION in the module
    docstring. Dropping the needles gives a number that is too low; keeping the
    surrounding markup gives one that is too high.
    """
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    return b"".join(
        b"{% comment %}" + newline + n.encode("utf-8") + newline + b"{% endcomment %}" + newline
        for n in needles
    )


def measure(root: Path, cases: list[dict]) -> dict:
    """Bind, mutate and judge every case. Returns a verdict per case."""
    import hashlib
    import importlib
    import io
    import unittest

    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.test.utils import setup_test_environment

    setup_test_environment()

    def fresh(module: str) -> None:
        """Drop the module and Django's template cache.

        A test that reads its file at MODULE level (a class attribute, a
        constant) captured the pre-mutation bytes at import time. Without this
        the mutation is invisible and every verdict is VACUOUS.
        """
        for name in list(sys.modules):
            if name == module or name.startswith(module + "."):
                del sys.modules[name]
        importlib.invalidate_caches()
        try:
            from django.template import engines

            for engine in engines.all():
                for loader in getattr(engine.engine, "template_loaders", []):
                    if hasattr(loader, "reset"):
                        loader.reset()
        except Exception:  # noqa: BLE001 - cache clearing is best effort
            pass

    def passes(test_id: str, module: str) -> bool | None:
        """True/False, or None when the id will not load at all."""
        fresh(module)
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        try:
            suite.addTests(loader.loadTestsFromName(test_id))
        except Exception:  # noqa: BLE001
            return None
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        if result.testsRun == 0:
            return None
        return not (result.failures or result.errors)

    def with_body(path: Path, body: bytes, test_id: str, module: str) -> bool | None:
        original = path.read_bytes()
        before = hashlib.md5(original).hexdigest()
        try:
            path.write_bytes(body)
            return passes(test_id, module)
        finally:
            path.write_bytes(original)
            after = hashlib.md5(path.read_bytes()).hexdigest()
            if after != before:
                raise SystemExit(f"restore failed for {path}: {before} -> {after}")
            fresh(module)

    verdicts: list[dict] = []
    for case in cases:
        test_id, module = case["id"], case["module"]
        if passes(test_id, module) is not True:
            verdicts.append({**case, "verdict": "UNUSABLE", "why": "red or unloadable unmutated"})
            continue

        bound: Path | None = None
        bound_name = ""
        for name in case["templates"]:
            path = _resolve_template(root, name)
            if path is None:
                continue
            if with_body(path, b"", test_id, module) is False:
                bound, bound_name = path, name
                break
        if bound is None:
            verdicts.append({**case, "verdict": "UNMEASURABLE", "why": "reads none of its .html literals"})
            continue

        needles = case["needles"] or [""]
        still = with_body(bound, _vacuous_body(bound.read_bytes(), needles), test_id, module)
        verdicts.append(
            {
                **case,
                "template": str(bound.relative_to(root)).replace("\\", "/"),
                "bound_as": bound_name,
                "verdict": "VACUOUS" if still else "SOUND",
            }
        )
    return {"verdicts": verdicts}


# ---------------------------------------------------------------------------
# Outer half: isolation, scope selection, ratchet.
# ---------------------------------------------------------------------------
def changed_test_files(root: Path, base_ref: str) -> set[str]:
    """Test files changed vs ``base_ref``; empty set means "could not tell"."""
    try:
        merge_base = subprocess.run(
            ["git", "-C", str(root), "merge-base", base_ref, "HEAD"],
            capture_output=True, text=True, timeout=60,
        )
        if merge_base.returncode != 0:
            return set()
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMR",
             merge_base.stdout.strip(), "HEAD"],
            capture_output=True, text=True, timeout=60,
        )
        if diff.returncode != 0:
            return set()
    except (OSError, subprocess.SubprocessError):
        return set()
    return {
        line.strip()
        for line in diff.stdout.splitlines()
        if line.strip().endswith(".py") and "/tests/" in line.strip()
    }


def load_baseline(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_baseline(
    path: Path, vacuous: list[dict], measured: dict | None = None
) -> None:
    """Write the ratchet, and the DENOMINATOR that makes it readable.

    finding_count alone is a numerator. A run that measures fewer cases
    writes a smaller number and reads as progress, which is precisely what
    happened here: _resolve_template could not find a template named by its
    bare filename, 89 cases fell into the unmeasurable bucket, that bucket
    is excluded from the rate, and this file recorded the flattering half.
    Storing measured/sound/unmeasurable next to it means the next reader can
    tell a fixed test from a blinded harness.
    """
    payload = {
        "finding_count": len(vacuous),
        "measured": measured or {},
        "vacuous": [
            {"id": v["id"], "file": v["file"], "template": v.get("template", "")}
            for v in sorted(vacuous, key=lambda v: v["id"])
        ],
        "rule": (
            "Tests measured VACUOUS: they still pass when the template they name is "
            "made to render nothing while every string they assert stays in its bytes. "
            "RATCHET DOWN ONLY. Fix a test (assert on rendered output) and REMOVE its "
            "entry; the gate fails on a baselined entry that has become SOUND, so the "
            "list cannot rot. Never add an entry to silence a finding -- a new vacuous "
            "test in a changed file is a finding, not a baseline candidate. "
            "finding_count may only fall EXCEPT when \"measured\" grows: a "
            "harness that can see more cases legitimately finds more, and that "
            "rise must be justified in the commit that makes it. Measured by "
            "scripts/verify_test_asserts_behaviour.py."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_in_worktree(argv: list[str], timeout: int, keep: bool) -> tuple[int, str]:
    """Do the measurement in a detached worktree, never in this checkout."""
    import shutil

    from verify_gates_can_fail import Workspace

    workspace_path = ROOT.parent / f"{ROOT.name}__asserts_behaviour"
    with Workspace(workspace_path, keep=keep) as workspace:
        workspace.reset()
        # Run THIS copy of the harness, not HEAD's. The worktree is checked out at
        # HEAD, so without this an edit to the harness cannot be tested until it is
        # committed -- and the first run, before the script exists at HEAD at all,
        # fails with an argparse error and no explanation.
        shutil.copy2(Path(__file__), workspace.path / "scripts" / Path(__file__).name)
        cmd = [
            sys.executable,
            str(workspace.path / "scripts" / Path(__file__).name),
            "--in-worktree",
            *argv,
        ]
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["PYTHONPATH"] = str(workspace.path)
        try:
            proc = subprocess.run(
                cmd, cwd=str(workspace.path), capture_output=True, text=True,
                errors="replace", timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return -9, "TIMEOUT"
        # stderr matters on a non-zero exit: an inner traceback is the only clue
        # the caller gets, and dropping it turns a typo into "failed (rc=2)".
        return proc.returncode, (proc.stdout if proc.returncode == 0 else
                                 (proc.stdout or "") + (proc.stderr or ""))


def _select(root: Path, args: argparse.Namespace, baseline: dict | None) -> list[dict]:
    """Which cases to measure, given the mode."""
    pool = candidates(root)
    by_id = {c["id"]: c for c in pool}

    if getattr(args, "measure_all", False):
        return pool

    if args.sample:
        # Discovery. Seeded so a run is reproducible and a reviewer can re-derive
        # the same draw; stratified by app so one large app cannot own the sample.
        buckets: dict[str, list[dict]] = {}
        for case in pool:
            parts = case["file"].split("/")
            buckets.setdefault(parts[1] if parts[0] == "apps" else parts[0], []).append(case)
        rng = random.Random(args.seed)
        picked: list[dict] = []
        per_app = max(1, args.sample // max(1, len(buckets)))
        for app in sorted(buckets):
            group = buckets[app]
            picked += rng.sample(group, min(len(group), per_app))
        rng.shuffle(picked)
        return picked[: args.sample]

    selected: list[dict] = []
    seen: set[str] = set()
    # --scope-changed bounds the run to the files this push touched, and it
    # has to bound the BASELINED set as well. A baselined test in a file
    # nobody edited cannot have changed, and re-measuring all of them would
    # put a quarter of an hour on every push -- which is how a gate ends up
    # switched off. The unbounded --compare (no --scope-changed) is what
    # re-checks the whole baseline.
    changed_scope = (
        changed_test_files(root, args.base_ref) if args.scope_changed else None
    )
    for entry in (baseline or {}).get("vacuous", []):
        if changed_scope is not None and entry["file"] not in changed_scope:
            continue
        case = by_id.get(entry["id"])
        if case is None:
            # Keep it, so it is reported as DRIFT rather than silently dropped.
            selected.append(
                {
                    **entry,
                    "module": entry["file"][:-3].replace("/", "."),
                    "templates": [],
                    "needles": [],
                    "missing": True,
                }
            )
        else:
            selected.append(case)
        seen.add(entry["id"])

    if changed_scope is not None:
        for case in pool:
            if case["file"] in changed_scope and case["id"] not in seen:
                selected.append(case)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove a test fails when the behaviour it names is removed."
    )
    parser.add_argument("--compare", action="store_true", help="Ratchet mode (enforcing).")
    parser.add_argument(
        "--scope-changed",
        action="store_true",
        help="Also measure tests in files changed vs --base-ref (deterministic).",
    )
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="measure_all",
        help="Measure the WHOLE candidate population (what --update-baseline needs).",
    )
    parser.add_argument(
        "--sample", type=int, default=0, help="Discovery over N cases (report-only)."
    )
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--list", action="store_true", help="Population + baseline sizes.")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--keep-worktree", action="store_true")
    parser.add_argument("--in-worktree", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    baseline = load_baseline(BASELINE_PATH)

    if args.update_baseline and not (
        getattr(args, "measure_all", False) or args.sample or args.scope_changed
    ):
        print(
            "FAIL: --update-baseline needs a scope. Without one nothing is "
            "selected, nothing is measured, and the baseline is written as 0 -- "
            "after which --compare passes forever over an unmeasured "
            "population. Use --all (or --sample N / --scope-changed).",
            file=sys.stderr,
        )
        return 1

    if args.list:
        pool = candidates(ROOT)
        everything = candidates(ROOT, include_db_backed=True)
        print(
            f"candidate population : {len(pool)} test(s) that read a file, assert a "
            "substring and name a .html"
        )
        print(
            f"out of scope         : {len(everything) - len(pool)} more match the shape "
            "but sit in a TestCase (needs a DB this harness does not build)"
        )
        print(f"baselined vacuous    : {len((baseline or {}).get('vacuous', []))}")
        suffix = "" if baseline else "  (ABSENT)"
        print(f"baseline             : {BASELINE_PATH.relative_to(ROOT)}{suffix}")
        return 0

    if args.in_worktree:
        cases = _select(ROOT, args, baseline)
        measurable = [c for c in cases if not c.get("missing")]
        result = measure(ROOT, measurable)
        result["missing"] = [c["id"] for c in cases if c.get("missing")]
        print(json.dumps(result))
        return 0

    # Building a worktree costs ~3 minutes. The selection is a static scan,
    # so decide FIRST whether there is anything to measure; a push that
    # touches no test file has nothing in scope and does not need one.
    if args.scope_changed and not _select(ROOT, args, baseline):
        print(
            "OK: no test file in this push is in scope, so nothing was "
            "measured -- and nothing is claimed. The unbounded --compare "
            "re-checks the whole baseline."
        )
        return 0

    # Outer: measure in isolation, then judge.
    passthrough: list[str] = []
    if getattr(args, "measure_all", False):
        passthrough += ["--all"]
    if args.sample:
        passthrough += ["--sample", str(args.sample), "--seed", str(args.seed)]
    if args.scope_changed:
        passthrough += ["--scope-changed", "--base-ref", args.base_ref]
    rc, out = run_in_worktree(passthrough, args.timeout, args.keep_worktree)
    if rc == -9:
        print(
            "TIMEOUT: the measurement did not finish. That is a resource result, not a "
            "finding -- re-run it alone or raise --timeout.",
            file=sys.stderr,
        )
        return 1
    if rc != 0 or not out.strip():
        print(f"the in-worktree measurement failed (rc={rc}):\n{out[-2000:]}", file=sys.stderr)
        return 1
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(f"unreadable measurement output:\n{out[-2000:]}", file=sys.stderr)
        return 1

    verdicts = result["verdicts"]
    vacuous = [v for v in verdicts if v["verdict"] == "VACUOUS"]
    sound = [v for v in verdicts if v["verdict"] == "SOUND"]
    unmeasurable = [v for v in verdicts if v["verdict"] in {"UNMEASURABLE", "UNUSABLE"}]
    missing = result.get("missing", [])

    if args.json:
        print(
            json.dumps(
                {
                    "vacuous": vacuous,
                    "sound": sound,
                    "unmeasurable": unmeasurable,
                    "missing": missing,
                },
                indent=2,
            )
        )

    measured = len(vacuous) + len(sound)
    print(
        f"measured {measured} case(s): {len(vacuous)} VACUOUS, {len(sound)} SOUND, "
        f"{len(unmeasurable)} unmeasurable"
    )

    # An empty SELECTION is believable in one case only: --scope-changed on a
    # push that touched no test file. Anywhere else it means the selection,
    # the worktree or the loader broke, and reporting it as "nothing vacuous"
    # would be this harness committing the error it looks for -- which is
    # exactly what --update-baseline did before 2026-09-01, writing a
    # baseline of 0 over a population of 394.
    selected_count = len(verdicts) + len(missing)
    population = len(candidates(ROOT))
    if selected_count == 0 and population and not args.scope_changed:
        print(
            f"FAIL: selected 0 of {population} candidate(s) in an unbounded "
            "mode. A harness that measures nothing reports a clean zero, "
            "which is the finding it exists to catch.",
            file=sys.stderr,
        )
        return 1
    for v in sorted(vacuous, key=lambda v: v["id"]):
        print(f"  VACUOUS  {v['id']}  <- {v.get('template', '?')}")

    # An unmeasurable case is not a clean one, and a bare count of them is
    # not a report. The two reasons are different findings: UNUSABLE means
    # the test is red or will not load BEFORE any mutation; UNMEASURABLE
    # means it names a template it never actually reads, so emptying that
    # template cannot change its result either way.
    if unmeasurable:
        from collections import Counter

        reasons = Counter(v.get("why", "?") for v in unmeasurable)
        print()
        print(f"unmeasurable, by reason ({len(unmeasurable)} total):")
        for why, count in reasons.most_common():
            print(f"  {count:4d}  {why}")
        by_file = Counter(v["file"] for v in unmeasurable)
        print("  worst files:")
        for name, count in by_file.most_common(10):
            print(f"    {count:4d}  {name}")

    if args.update_baseline:
        write_baseline(
            BASELINE_PATH,
            vacuous,
            {
                "population": population,
                "measured": measured,
                "vacuous": len(vacuous),
                "sound": len(sound),
                "unmeasurable": len(unmeasurable),
            },
        )
        print(f"baseline written -> {BASELINE_PATH.relative_to(ROOT)} ({len(vacuous)} entries)")
        return 0

    if args.sample:
        known = {e["id"] for e in (baseline or {}).get("vacuous", [])}
        fresh_finds = [v for v in vacuous if v["id"] not in known]
        print(f"\nDISCOVERY (report-only): {len(fresh_finds)} vacuous test(s) not yet baselined.")
        for v in sorted(fresh_finds, key=lambda v: v["id"]):
            print(f"  NEW  {v['id']}")
        print(
            "Report-only on purpose: a sampled rate moves on its own, and a gate whose "
            "number moves without anyone touching the tree gets ignored. Fix these, or "
            "record them with --update-baseline as a reviewed edit."
        )
        return 0

    if not args.compare:
        return 0

    if baseline is None:
        print(
            f"FAIL: --compare needs a baseline at {BASELINE_PATH}; create it with "
            "--update-baseline.",
            file=sys.stderr,
        )
        return 1

    known = {e["id"] for e in baseline.get("vacuous", [])}
    findings: list[str] = []
    for test_id in missing:
        findings.append(f"baselined test no longer resolves (renamed or deleted): {test_id}")
    for v in sound:
        if v["id"] in known:
            findings.append(f"baselined test is now SOUND -- remove it from the baseline: {v['id']}")
    for v in unmeasurable:
        if v["id"] in known:
            findings.append(
                f"baselined test became unmeasurable ({v.get('why', '?')}): {v['id']}"
            )
    for v in vacuous:
        if v["id"] not in known:
            findings.append(f"NEW vacuous test in a changed file: {v['id']}")

    if findings:
        print(f"\nFAIL: {len(findings)} finding(s).", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nThe baseline ratchets DOWN only. Fix a test by asserting on rendered "
            "output, then drop its entry.",
            file=sys.stderr,
        )
        return 1

    # Say what was actually re-measured. Claiming all of them still measure
    # vacuous after a --scope-changed run that measured none of them would be
    # a message asserting something it did not check.
    rechecked = len([v for v in vacuous + sound if v["id"] in known])
    print()
    if args.scope_changed:
        print(
            f"OK: {rechecked} of {len(known)} baselined test(s) were in scope "
            "and still measure vacuous; no new vacuous test in a changed file. "
            "The rest sit in files this push did not touch -- the unbounded "
            "--compare is what re-checks those."
        )
    else:
        print(
            f"OK: all {len(known)} baselined test(s) still measure vacuous, and "
            "no new vacuous test in scope. The number goes down by fixing them."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
