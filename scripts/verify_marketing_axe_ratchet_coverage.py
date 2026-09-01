#!/usr/bin/env python3
"""Guard the COVERAGE of the marketing axe ratchet.

Why this exists
---------------
The ratchet itself (``scripts/run_marketing_axe_sweep.mjs``, driven by
``scripts/run_marketing_axe_ratchet.sh``) needs a browser, a booted Django and
~3.5 minutes, so it lives in a workflow. That leaves one failure mode nothing
else can see, and it is the one that actually happened here:

    The sweep was written against the 15 paths in
    ``tests/e2e/marketing-visual-truth.spec.js`` and reported the marketing
    surface CLEAN, while ``/platform/analytics/`` and ``/platform/security/``
    were failing ``color-contrast`` at 1.08:1 on both viewports. The pages were
    simply not in the list. The other spec,
    ``tests/e2e/marketing-accessibility.spec.js``, did cover them -- and had
    been red long enough that nobody read it.

A ratchet that scans the wrong pages reports zero for the same reason a broken
detector does, and both look identical in CI. This gate is the cheap, always-on
half of the pair: it asserts the sweep still covers at least every path the two
specs cover, that the baseline it ratchets against exists and is well-formed,
and that something actually invokes the sweep.

This is a WIRING gate, so it reads source. It makes no claim about contrast --
that is the sweep's job, in a browser, on the rendered page.

Usage
-----
    python scripts/verify_marketing_axe_ratchet_coverage.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

SWEEP = REPO_ROOT / "scripts" / "run_marketing_axe_sweep.mjs"
BASELINE = REPO_ROOT / "var" / "a11y-marketing-axe-baseline.json"
VISUAL_TRUTH_SPEC = REPO_ROOT / "tests" / "e2e" / "marketing-visual-truth.spec.js"
ACCESSIBILITY_SPEC = REPO_ROOT / "tests" / "e2e" / "marketing-accessibility.spec.js"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# The accessibility spec rewrites "/" to "/marketing/" before navigating (the
# marketing home is served at both). Treat them as the same page.
_PATH_ALIASES = {"/marketing/": "/"}

_PAIR_RE = re.compile(r"^[a-z0-9-]+\|#[0-9a-f]{3,8}\|#[0-9a-f]{3,8}$")


def _normalise(path: str) -> str:
    return _PATH_ALIASES.get(path, path)


def _array_paths(source: str, array_name: str) -> set[str]:
    """Collect every "/..." string literal inside `const <array_name> = [ ... ]`."""
    start = source.find(f"const {array_name} = [")
    if start == -1:
        return set()
    depth = 0
    end = start
    for i in range(source.index("[", start), len(source)):
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = source[start:end]
    return {_normalise(m) for m in re.findall(r"[\"'](/[^\"']*)[\"']", body)}


def main() -> int:
    problems: list[str] = []

    for path in (SWEEP, VISUAL_TRUTH_SPEC, ACCESSIBILITY_SPEC):
        if not path.is_file():
            problems.append(f"missing file: {path.relative_to(REPO_ROOT)}")
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1

    sweep_src = SWEEP.read_text(encoding="utf-8")
    sweep_pages = _array_paths(sweep_src, "PAGES")
    if not sweep_pages:
        problems.append(
            "scripts/run_marketing_axe_sweep.mjs: could not read its PAGES array — "
            "if it was renamed, update this gate rather than leaving it blind"
        )

    truth_pages = _array_paths(VISUAL_TRUTH_SPEC.read_text(encoding="utf-8"), "PAGES")
    a11y_pages = _array_paths(
        ACCESSIBILITY_SPEC.read_text(encoding="utf-8"), "ACCESSIBILITY_PATHS"
    )
    if not truth_pages:
        problems.append("marketing-visual-truth.spec.js: could not read its PAGES array")
    if not a11y_pages:
        problems.append(
            "marketing-accessibility.spec.js: could not read its ACCESSIBILITY_PATHS array"
        )

    for label, expected in (
        ("marketing-visual-truth.spec.js", truth_pages),
        ("marketing-accessibility.spec.js", a11y_pages),
    ):
        missing = sorted(expected - sweep_pages)
        if missing:
            problems.append(
                f"the axe sweep does not cover {len(missing)} path(s) that {label} "
                f"covers — a page outside the sweep can fail forever without "
                f"moving the ratchet: {', '.join(missing)}"
            )

    # Baseline shape. A ratchet with no baseline, or with a baseline whose
    # allowed-pair keys are unreadable, silently degrades to 'anything goes'.
    if not BASELINE.is_file():
        problems.append(
            f"missing baseline {BASELINE.relative_to(REPO_ROOT)} — re-cut it with "
            "AXE_RATCHET_MODE=--write-baseline bash scripts/run_marketing_axe_ratchet.sh"
        )
    else:
        try:
            data = json.loads(BASELINE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            data = None
            problems.append(f"baseline is not valid JSON: {exc}")
        if isinstance(data, dict):
            cap = data.get("max_failing_pages")
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
                problems.append(
                    f"baseline max_failing_pages must be a non-negative int, got {cap!r}"
                )
            pairs = data.get("allowed_contrast_pairs")
            if not isinstance(pairs, list):
                problems.append(
                    f"baseline allowed_contrast_pairs must be a list, got {type(pairs).__name__}"
                )
            else:
                for entry in pairs:
                    if not isinstance(entry, str) or not _PAIR_RE.match(entry):
                        problems.append(
                            f"baseline allowed_contrast_pairs entry is not "
                            f"'rule|#fg|#bg': {entry!r}"
                        )
        elif data is not None:
            problems.append("baseline must be a JSON object")

    # Something must actually run the sweep.
    invoked_by = []
    if WORKFLOW_DIR.is_dir():
        for wf in sorted(WORKFLOW_DIR.glob("*.yml")):
            text = wf.read_text(encoding="utf-8", errors="replace")
            if "run_marketing_axe_sweep.mjs" in text or "run_marketing_axe_ratchet.sh" in text:
                invoked_by.append(wf.name)
    if not invoked_by:
        problems.append(
            "no .github/workflows/*.yml invokes run_marketing_axe_ratchet.sh or "
            "run_marketing_axe_sweep.mjs — the ratchet exists but nothing runs it"
        )

    if problems:
        print("marketing-axe-ratchet-coverage: FAIL", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(
        "marketing-axe-ratchet-coverage: OK — sweep covers "
        f"{len(sweep_pages)} path(s), a superset of both specs "
        f"({len(truth_pages)} + {len(a11y_pages)}); baseline present and well-formed; "
        f"invoked by {', '.join(invoked_by)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
