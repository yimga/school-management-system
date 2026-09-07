#!/usr/bin/env python3
"""An authorization test must assert the absence of the EFFECT, not a refusal code.

THE DEFECT SHAPE
----------------
``self.assertEqual(resp.status_code, 403)`` is satisfied by ANY early refusal:
the permission check the test meant to exercise, a truncated RBAC catalog, an
MFA redirect, a middleware, a typo'd URL. Such a test cannot distinguish "the
endpoint refused a cross-tenant write" from "the request never reached the
endpoint" -- and when the second happens the test stays GREEN.

Not hypothetical. ``test_payment_create_blocks_cross_tenant_invoice_reference``
passed for weeks because the request was refused 403 for want of
``finance.view`` before it could reach the assertion it claimed to make. A red
test gets investigated eventually; a green that never reached its assertion is
invisible for the life of the tree, because nothing anywhere complains.

3xx counts as a refusal shape, not only 4xx: in this repo a 302 on a privileged
view is usually ``/mfa/setup/`` or the public login, which is the same "never
arrived" failure wearing a different number.

WHAT IS AND IS NOT A FINDING
----------------------------
A finding is a test method where EVERY assertion is about a status code, at
least one asserts a refusal code, and the method NAME claims an authorization
outcome (block / deny / cross_tenant / idor / isolat / scope / ...). A test that
also asserts state -- no row was written, the body lacks the other tenant's data
-- can tell the two cases apart and is not reported, however many status codes
it checks besides.

The name filter is what keeps this actionable. Tree-wide there are ~540
refusal-only tests; most are honest tests of an unambiguous refusal path
("a corrupt gzip body is a 400, not a 500"). The ~249 with authorization-shaped
names are the ones where a silent green is a SECURITY claim nobody is making.

WHY A RATCHET AND NOT A ZERO BASELINE
-------------------------------------
The existing 249 are not defects to be fixed under deadline; each needs a
judgement about what effect to assert instead. A zero baseline would be switched
off within a day. This freezes the count so the class cannot GROW, which is the
property worth having.

THE CURE, when this gate stops you: assert the absence of the effect.
Instead of only ``assertEqual(resp.status_code, 403)``, add an assertion that
no row landed -- under ``rls_bypass``, across the whole set, not just the
requester's scope. That fails on a real cross-tenant write whatever status code
the endpoint returns.

BASELINE WRITING IS EXPLICIT HERE, DELIBERATELY
-----------------------------------------------
Several scanners in this repo rewrite their baseline on a bare invocation, so
running one without ``--compare`` launders every new finding with no warning.
This one never writes unless asked with ``--update-baseline``. A bare run
reports and exits 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "refusal-only-authorization-baseline.json"

#: 3xx included on purpose -- see the module docstring.
REFUSAL_CODES = frozenset({301, 302, 303, 307, 308, 400, 401, 403, 404, 405, 409, 429})

#: Name fragments that make a refusal-only assertion an authorization CLAIM.
RISK_WORDS = (
    "block", "deny", "denied", "forbid", "cross_tenant", "unauthor", "isolat",
    "leak", "idor", "bola", "scope", "permission", "reject", "refuse", "cannot",
    "not_allowed", "no_access", "other_school", "tenant", "rls",
)


def _is_status_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "status_code"


def _literal_ints(node: ast.AST) -> list[int]:
    out: list[int] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        out.append(node.value)
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for elt in node.elts:
            out.extend(_literal_ints(elt))
    return out


def classify_assert(call: ast.Call) -> tuple[bool, list[int]]:
    """(asserts_only_a_status, refusal_codes_named)."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if not name.startswith("assert"):
        return False, []
    # assertContains(resp, text, status_code=403) also asserts CONTENT, so it can
    # tell a real refusal from a request that never arrived.
    if name in ("assertContains", "assertNotContains"):
        return False, []
    args = list(call.args)
    if not any(_is_status_attr(a) for a in args):
        return False, []
    codes: list[int] = []
    for a in args:
        if not _is_status_attr(a):
            codes.extend(_literal_ints(a))
    return True, [c for c in codes if c in REFUSAL_CODES]


def scan_source(path: str, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # verify_python_files_parse owns that failure; reporting it twice buries
        # the report that explains how to fix it.
        return []

    # Qualify by CLASS, not just file+name. Two classes in one module can define
    # the same test name -- apps/finance/tests/test_invoicing_is_school_scoped
    # does -- and a file::name key silently collapses them into one baseline
    # entry, so the count written and the count read back disagree by one and
    # one real test is un-ratcheted.
    owner: dict[int, str] = {}
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef):
            for child in cls.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owner[id(child)] = cls.name

    findings: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        risk = sorted({w for w in RISK_WORDS if w in node.name.lower()})
        if not risk:
            continue

        calls = [
            n for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))
                or (isinstance(n.func, ast.Name) and n.func.id.startswith("assert"))
            )
        ]
        if not calls:
            continue
        # A bare `assert x` is a state assertion too.
        if any(isinstance(n, ast.Assert) for n in ast.walk(node)):
            continue

        refusals: list[int] = []
        status_only = True
        for call in calls:
            is_status, codes = classify_assert(call)
            if not is_status:
                status_only = False
                break
            refusals.extend(codes)

        if status_only and refusals:
            findings.append(
                {
                    "key": "%s::%s::%s" % (path, owner.get(id(node), "-"), node.name),
                    "file": path,
                    "line": node.lineno,
                    "test": node.name,
                    "codes": sorted(set(refusals)),
                    "risk": risk,
                }
            )
    return findings


SELF_CHECK = [
    ("def test_cross_tenant_blocked(self):\n    self.assertEqual(r.status_code, 403)\n",
     1, "sole refusal assertion on an authorization-named test"),
    ("def test_cross_tenant_blocked(self):\n    self.assertEqual(r.status_code, 200)\n",
     0, "200 is not a refusal"),
    ("def test_cross_tenant_blocked(self):\n    self.assertEqual(r.status_code, 403)\n"
     "    self.assertFalse(Payment.objects.exists())\n",
     0, "also asserts state -- this is the cure"),
    ("def test_cross_tenant_blocked(self):\n    self.assertIn(r.status_code, (401, 403))\n",
     1, "membership form is still status-only"),
    ("def test_cross_tenant_blocked(self):\n    self.assertContains(r, 'x', status_code=403)\n",
     0, "assertContains checks content as well"),
    ("def test_cross_tenant_blocked(self):\n    assert r.status_code == 403\n",
     0, "a bare assert is a statement, not an assert* call"),
    ("def test_corrupt_body_is_a_400(self):\n    self.assertEqual(r.status_code, 400)\n",
     0, "no authorization claim in the name"),
    ("def helper_cross_tenant_blocked(self):\n    self.assertEqual(r.status_code, 403)\n",
     0, "not a test method"),
    ("def test_tenant_isolation(self):\n    self.assertEqual(r.status_code, 302)\n",
     1, "302 is a refusal shape here (MFA / public login)"),
]


def self_check() -> bool:
    ok = True
    for src, expected, label in SELF_CHECK:
        got = len(scan_source("s.py", src))
        if got != expected:
            print("SELF-CHECK FAIL: %s -- expected %d, got %d" % (label, expected, got))
            ok = False
    return ok


def candidate_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", "apps/*/tests/*.py", "apps/*/tests/**/*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return [REPO_ROOT / p for p in out.stdout.splitlines() if p.endswith(".py")]


def collect() -> tuple[list[dict], int]:
    findings: list[dict] = []
    files = candidate_files()
    for path in files:
        try:
            src = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        findings.extend(scan_source(rel, src))
    return findings, len(files)


def _load_baseline() -> set[str] | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["keys"])
    except (OSError, ValueError, KeyError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Refusal-only authorization assertions.")
    ap.add_argument("--compare", action="store_true", help="fail on NEW findings")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite the baseline (never happens implicitly)")
    args = ap.parse_args()

    if not self_check():
        print("\nRefusing to report: the classifier disagrees with its known-good cases.")
        return 1
    if args.self_check:
        print("self-check: %d cases OK" % len(SELF_CHECK))
        return 0

    findings, n_files = collect()
    if not n_files:
        # A zero over an empty corpus is not a zero.
        print("scan_refusal_only_assertions: FAIL -- no test files found; discovery "
              "is broken (is this a git worktree?).")
        return 1

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps({"count": len(findings),
                        "keys": sorted(f["key"] for f in findings)},
                       indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("wrote baseline: %d entries -> %s"
              % (len(findings), BASELINE_PATH.relative_to(REPO_ROOT)))
        return 0

    if args.json:
        print(json.dumps({"inspected_files": n_files, "count": len(findings),
                          "findings": findings}, indent=1))
        return 0

    if args.compare:
        baseline = _load_baseline()
        if baseline is None:
            print("scan_refusal_only_assertions: FAIL -- baseline missing or "
                  "unreadable at %s. Regenerate with --update-baseline."
                  % BASELINE_PATH.relative_to(REPO_ROOT))
            return 1
        new = sorted(f for f in findings if f["key"] not in baseline)
        # Report what was INSPECTED beside what was found: a count with no
        # denominator cannot be told apart from a broken scan.
        print("scan_refusal_only_assertions: %d refusal-only authorization test(s) "
              "across %d file(s); baseline %d; new %d"
              % (len(findings), n_files, len(baseline), len(new)))
        if not new:
            fixed = len(baseline) - len([f for f in findings if f["key"] in baseline])
            if fixed > 0:
                print("  %d baseline entr(ies) no longer match -- run "
                      "--update-baseline to ratchet the count down." % fixed)
            return 0
        print("\nNEW refusal-only authorization test(s):")
        for f in findings:
            if f["key"] in new:
                print("  %s:%d  %s  codes=%s" % (f["file"], f["line"], f["test"], f["codes"]))
        print(
            "\nSuch a test asserts only that the request was refused, which ANY early\n"
            "refusal satisfies -- a permission gap, an MFA redirect, a renamed URL. It\n"
            "cannot fail when the thing it claims to test breaks.\n\n"
            "Fix: assert the absence of the EFFECT as well. Check that no row landed,\n"
            "under rls_bypass, across the whole set -- that fails on a real cross-tenant\n"
            "write whatever status code comes back."
        )
        return 1

    for f in sorted(findings, key=lambda x: (-len(x["risk"]), x["file"], x["line"])):
        print("%s:%d  %s  codes=%s  risk=%s"
              % (f["file"], f["line"], f["test"], f["codes"], ",".join(f["risk"])))
    print("\n%d refusal-only authorization test(s) across %d file(s) inspected."
          % (len(findings), n_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
