#!/usr/bin/env python3
"""Local pre-push mirror of the fast, deps-free architectural-boundary gates.

Why this exists
---------------
`architectural-boundaries.yml` only triggers on ``pull_request`` (plus manual
``workflow_dispatch``), so a commit pushed straight to ``main`` never runs the
boundary gates — redness lands on the default branch and is only discovered
later, when some unrelated PR finally runs the workflow. On this repository a
required-status-check (GitHub branch protection) is not available (private repo
on the free plan), so the only enforcement lever left is *local*: run the gates
before the push leaves the machine.

This runner shells out to the exact same CSS/template zero-tolerance gates the
CI job runs, with the exact same flags, so a green run here means a green
`architectural-boundaries` job there. It intentionally covers ONLY the
stdlib-only gates (no Django import), which is both the fast subset and the
subset that catches the CSS/template redness that has repeatedly shipped to
``main`` (undefined CSS classes, off-token colours, theme-locked text, inline
styles, render safety, attribute-context includes, service-worker monotonicity).

Behaviour
---------
* Default is WARN mode: every gate runs, failures are reported loudly, but the
  process still exits 0 so a push is never blocked. This keeps it safe to
  install into a shared clone (it will never wedge a teammate/agent mid-push).
* STRICT mode (``--strict`` or env ``RMC_PREPUSH_STRICT=1``) exits non-zero when
  any gate fails, so `git push` aborts. Turn this on once your working tree is
  clean and you want the machine to hold the line.

Usage
-----
    python scripts/pre_push_boundary_check.py            # warn-only
    python scripts/pre_push_boundary_check.py --strict   # block on red
    RMC_PREPUSH_STRICT=1 git push                        # block via env
    python scripts/pre_push_boundary_check.py --list     # show the gate list
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Repo root = parent of this file's directory (scripts/), so the runner works
# regardless of the caller's cwd (a git hook runs from the worktree root, but a
# developer may invoke it from anywhere).
REPO_ROOT = Path(__file__).resolve().parent.parent

# (label, argv) — argv mirrors the CI step invocations in
# .github/workflows/architectural-boundaries.yml exactly. Keep this list in sync
# with that workflow's stdlib-only jobs; the whole point is byte-for-byte parity
# with what CI would say.
GATES: list[tuple[str, list[str]]] = [
    # First: a module that does not compile cannot be imported at all, and every
    # gate below it is answering about a tree that does not run.
    ("python-files-parse", ["verify_python_files_parse.py"]),
    # Its sibling, and for a worse failure mode: a JavaScript file that does not parse
    # fails SILENTLY in the browser - the tag 200s, the console throws, and the page
    # renders normally with one feature dead. Skipped (not failed) when Node is absent,
    # so a Python-only environment is not blocked by a toolchain it does not have.
    ("javascript-files-parse", ["verify_javascript_files_parse.py"]),
    # And the third: markup that does not close. Quieter than either of the above,
    # because it does not fail anywhere - the page 200s and the browser silently
    # reparents everything after the unclosed element. Nine served templates were
    # found this way on 2026-08-20, one of them shipping a </motion> end tag.
    ("template-html-structure", ["verify_template_html_structure.py"]),
    # And the fourth floor gate, for code that parses, imports, and never runs.
    # EdgeAutosyncMiddleware was defined, correct, and referenced NOWHERE but its own
    # class statement — written to keep a LAN box syncing when nothing pings /health/,
    # and never added to MIDDLEWARE, so the box it existed for never synced. Nothing
    # else can see this: it imports cleanly and has no unused-import warning.
    ("unregistered-middleware", ["scan_unregistered_middleware.py", "--strict"]),
    ("undefined-css-classes", ["scan_undefined_css_classes.py", "--compare"]),
    ("off-token-colors", ["scan_off_token_colors.py", "--strict"]),
    ("theme-locked-token-text", ["scan_theme_locked_token_text.py", "--strict"]),
    ("inline-style-off-token", ["scan_inline_style_off_token.py", "--compare"]),
    # M9 CSP enforce seal: no inline on*= event handlers in served (non-admin)
    # templates — a strict script-src (no 'unsafe-inline') blocks them.
    ("inline-event-handlers", ["scan_inline_event_handlers.py", "--compare"]),
    ("template-render-safety", ["audit_template_render_safety.py", "--compare"]),
    ("attribute-context-includes", ["scan_attribute_context_includes.py"]),
    # {% include with x|default:missing_var %} → VariableDoesNotExist 500 (ops_surface class).
    # |default:missing_var anywhere (not only {% include with %}) → VariableDoesNotExist 500.
    # Static-only completion proof (full Django rows run in ci.yml).
    ("include-with-default-context-var", ["scan_include_with_default_context_var.py", "--strict"]),
    ("eager-filter-arg-completion-static", ["verify_eager_filter_arg_completion.py", "--static-only"]),
    ("nav-engine-coverage-static", ["verify_nav_engine_coverage.py", "--static-only"]),
    ("report-entity-coverage", ["verify_report_entity_coverage.py"]),
    ("service-worker-version", ["verify_service_worker_version.py", "--check-monotonic"]),
    # Approval HTML → live admin: fails if build lock / visible chip / grid drift.
    # Prevents another "CSS-only commit looks unchanged after deploy" silent miss.
    ("django-admin-preview-parity", ["verify_django_admin_preview_parity.py"]),
    # Freeze the set of direct request.FILES intake sites that skip the shared
    # upload validator (apps.security.upload_validation). Enforced here — the
    # real gate on direct pushes — and mirrored as the architectural-boundaries
    # `upload-validation-coverage` job for pull_request runs.
    ("upload-validation-coverage", ["scan_upload_validation_coverage.py", "--compare"]),
    # "6 access requests awaiting approval" with no link. An attention row must
    # carry the page that RESOLVES it, or say why it has none. Runs WITHOUT
    # --compare on purpose: the class is at zero, so there is no baseline to hide
    # behind and the very next dead end blocks the push.
    ("actionless-attention-surfaces", ["scan_actionless_attention_surfaces.py"]),
    # A Migration Cloud lander must KEEP the row it rejected and declare WHY.
    # You cannot replay a row you did not keep, so this is the prerequisite for
    # every automated-remediation step in the zero-touch spec. Zero-tolerance and
    # deliberately WITHOUT --compare: there is no baseline to hide behind, and the
    # next lander that throws a row away blocks the push.
    ("lander-row-error-contract", ["scan_lander_row_error_contract.py", "--strict"]),
]

# Gates that CANNOT answer without the live Django app registry, and are therefore not
# part of the deps-free contract above. They run only when Django imports, and report
# SKIP (never PASS) when it does not.
#
# WHY THEY ARE HERE AT ALL, given this runner exists to mirror the deps-free CI job:
# these gates live in `ci.yml::django-tests`, and GitHub Actions has run NO jobs on this
# repository since 2026-08-15 (billing). So "it is covered in CI" is currently false for
# every one of them, and this runner is the only thing standing between a red gate and
# `main`. That is not hypothetical -- `scan_rls_table_coverage` is a ZERO-baseline gate
# that went red the moment PR #184 merged (three tenant-scoped pairing tables enumerated
# in no enable_rls migration) and stayed red on main until someone ran it by hand.
#
# Kept deliberately short. Each entry pays ~8s for django.setup(), so this list earns its
# place one gate at a time: zero-tolerance, security-relevant, and invisible to every
# stdlib gate above.
DJANGO_GATES: list[tuple[str, list[str]]] = [
    ("rls-table-coverage", ["scan_rls_table_coverage.py", "--compare"]),
]

_PER_GATE_TIMEOUT_S = 120


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# Exit code a gate uses to say "my toolchain is not installed here, so I did not run".
# Distinct from pass and from fail: reporting SKIP is honest, while reporting PASS would
# be a gate that silently stops gating, and reporting FAIL would block every developer
# who does not have that toolchain.
_SKIPPED_EXIT_CODE = 2


def _run_gate(label: str, argv: list[str]) -> tuple[bool | None, str]:
    """Run one gate; return ``(passed, captured_output)``.

    ``passed`` is ``None`` when the gate reported that it could not run at all.
    """
    script = REPO_ROOT / "scripts" / argv[0]
    if not script.is_file():
        # A missing gate script must not silently pass — report it as a failure
        # so the drift is visible, but the caller decides whether it blocks.
        return False, f"gate script not found: {script}"
    cmd = [sys.executable, str(script), *argv[1:]]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_PER_GATE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, f"gate timed out after {_PER_GATE_TIMEOUT_S}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == _SKIPPED_EXIT_CODE:
        return None, output.strip()
    return proc.returncode == 0, output.strip()


def _django_available() -> bool:
    """Can a subprocess import Django and load settings? Probed once, cheaply."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_PER_GATE_TIMEOUT_S,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": os.environ.get(
                "DJANGO_SETTINGS_MODULE", "config.settings"
            )},
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _tail(text: str, lines: int = 15) -> str:
    rows = [r for r in text.splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any gate fails (also enabled by RMC_PREPUSH_STRICT=1).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the gate list and exit.",
    )
    args, _ignored = parser.parse_known_args(argv)

    if args.list:
        print("Pre-push boundary gates (mirror of architectural-boundaries.yml):")
        for label, gate_argv in GATES:
            print(f"  - {label}: python scripts/{' '.join(gate_argv)}")
        for label, gate_argv in DJANGO_GATES:
            print(f"  - {label}: python scripts/{' '.join(gate_argv)}  [needs Django]")
        return 0

    strict = args.strict or _truthy(os.environ.get("RMC_PREPUSH_STRICT"))

    print("Pre-push boundary gates (deps-free subset of CI, plus Django-only gates)...")
    failures: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for label, gate_argv in GATES:
        passed, output = _run_gate(label, gate_argv)
        if passed is None:
            # Said so out loud rather than counted as green: a gate that cannot run is
            # not a gate that passed, and hiding that is how coverage quietly evaporates.
            print(f"  SKIP  {label}")
            skipped.append((label, output))
        elif passed:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}")
            failures.append((label, output))

    if DJANGO_GATES:
        if _django_available():
            for label, gate_argv in DJANGO_GATES:
                passed, output = _run_gate(label, gate_argv)
                if passed is None:
                    print(f"  SKIP  {label}")
                    skipped.append((label, output))
                elif passed:
                    print(f"  PASS  {label}")
                else:
                    print(f"  FAIL  {label}")
                    failures.append((label, output))
        else:
            for label, _argv in DJANGO_GATES:
                print(f"  SKIP  {label}")
                skipped.append((label, "Django could not be imported in this environment"))

    for label, output in skipped:
        print("")
        print(f"  -- {label} did NOT run --")
        for row in _tail(output, 3).splitlines():
            print(f"    {row}")

    if not failures:
        print("All boundary gates green - safe to push.")
        return 0

    print("")
    print(f"{len(failures)} boundary gate(s) FAILED:")
    for label, output in failures:
        print(f"\n  -- {label} --")
        tail = _tail(output)
        for row in tail.splitlines():
            print(f"    {row}")

    print("")
    if strict:
        print(
            "STRICT mode: push aborted. Fix the gate(s) above, or re-run with "
            "RMC_PREPUSH_STRICT unset to warn-only.",
        )
        return 1

    print(
        "WARN mode: push NOT blocked. These will turn the "
        "`architectural-boundaries` CI job red once a PR runs it.\n"
        "  Set RMC_PREPUSH_STRICT=1 (or pass --strict) to block red pushes locally.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
