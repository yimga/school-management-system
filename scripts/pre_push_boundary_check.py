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
    ("undefined-css-classes", ["scan_undefined_css_classes.py", "--compare"]),
    ("off-token-colors", ["scan_off_token_colors.py", "--strict"]),
    ("theme-locked-token-text", ["scan_theme_locked_token_text.py", "--strict"]),
    ("inline-style-off-token", ["scan_inline_style_off_token.py", "--compare"]),
    ("template-render-safety", ["audit_template_render_safety.py", "--compare"]),
    ("attribute-context-includes", ["scan_attribute_context_includes.py"]),
    # {% include with x|default:missing_var %} → VariableDoesNotExist 500 (ops_surface class).
    # |default:missing_var anywhere (not only {% include with %}) → VariableDoesNotExist 500.
    # Static-only completion proof (full Django rows run in ci.yml).
    ("include-with-default-context-var", ["scan_include_with_default_context_var.py", "--strict"]),
    ("eager-filter-arg-completion-static", ["verify_eager_filter_arg_completion.py", "--static-only"]),
    ("service-worker-version", ["verify_service_worker_version.py", "--check-monotonic"]),
    # Approval HTML → live admin: fails if build lock / visible chip / grid drift.
    # Prevents another "CSS-only commit looks unchanged after deploy" silent miss.
    ("django-admin-preview-parity", ["verify_django_admin_preview_parity.py"]),
]

_PER_GATE_TIMEOUT_S = 120


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _run_gate(label: str, argv: list[str]) -> tuple[bool, str]:
    """Run one gate; return (passed, captured_output)."""
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
    return proc.returncode == 0, output.strip()


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
        return 0

    strict = args.strict or _truthy(os.environ.get("RMC_PREPUSH_STRICT"))

    print("Pre-push boundary gates (fast, deps-free subset of CI)...")
    failures: list[tuple[str, str]] = []
    for label, gate_argv in GATES:
        passed, output = _run_gate(label, gate_argv)
        if passed:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}")
            failures.append((label, output))

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
