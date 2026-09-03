#!/usr/bin/env python3
"""Bundle verifier for CP v8 closeout: layout assets, MFA flow, dropdowns, spacing.

Why the reporting was rewritten (2026-09-02)
--------------------------------------------
Every failing child used to be recorded as ``out[-500:]`` or ``out[-300:]`` -- the
LAST few hundred characters of its output. The children sort their findings by
DESCENDING severity, so the tail of a child's report is the mildest end of its list.
This gate was therefore printing each child's least important findings and silently
dropping its worst.

Measured on main the day this was rewritten: ``audit_large_collection_surfaces.py``
reports **11** findings. This gate printed **3** -- the three lowest-scoring -- and
dropped the eight above them, including the two worst: an 8-column staff caseload
with 2 forms and 7 input controls inside repeated rows, and a bulk console with 2
forms, 10 controls and no pagination at all. Someone reading the CI failure would
have fixed three minor rows and concluded the surface was clean.

A partial tally is worse than no tally, because it reads as a complete one. So a
failing child now reports its findings in full, and on the rare occasion a cap is
hit the number of suppressed lines is PRINTED rather than implied.

The ``surface_spacing`` check also parsed its child by substring, and one of its two
conditions could never be false:

    '"finding_count": 0' not in out.replace(" ", "")

The needle carries a space; the haystack has had every space removed. It read as a
defensive second opinion and was dead code. The substring approach was wrong in
principle too -- a nested ``"finding_count": 0`` anywhere in the payload would have
satisfied a nonzero top-level count. The child emits real JSON under ``--json``, so
this now parses it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Generous ceiling on how much of a failing child we reproduce. Reached only by a
#: child that has gone badly wrong; a normal findings list is far smaller. Whatever
#: it cuts is REPORTED as a count -- see ``_excerpt``.
MAX_REPORT_CHARS = 20000


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _excerpt(out: str) -> str:
    """A failing child's output, head-anchored, with any suppression stated.

    Head-anchored, not tail-anchored, because the children sort by descending
    severity: if anything has to be dropped it must be the mild end of the list, and
    the reader has to be told it happened. The old tail slice did the exact reverse.
    """
    out = out.strip()
    if not out:
        return "(child produced no output)"
    if len(out) <= MAX_REPORT_CHARS:
        return out
    dropped = out.count("\n", MAX_REPORT_CHARS) + 1
    return (
        out[:MAX_REPORT_CHARS]
        + f"\n  ... {dropped} further line(s) suppressed at {MAX_REPORT_CHARS} chars; "
        "run this child directly for the full list"
    )


def _finding_count(out: str) -> int | None:
    """The child's top-level ``finding_count``, or None if it cannot be read.

    None is NOT treated as zero. A spacing report this gate cannot parse is a gate
    that does not know the answer, and "could not tell" must never render as "passed".
    """
    try:
        payload = json.loads(out)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("finding_count")
    return value if isinstance(value, int) else None


def main() -> int:
    checks: list[tuple[str, list[str]]] = [
        ("header_dropdown_viewport", ["python", "scripts/verify_header_dropdown_viewport.py"]),
        ("dead_hrefs_strict", ["python", "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
        ("surface_spacing", ["python", "scripts/audit_surface_spacing_contract.py", "--json"]),
        ("interaction_integrity", ["python", "scripts/verify_interaction_integrity_completion.py"]),
        ("template_render_safety", ["python", "scripts/audit_template_render_safety.py"]),
        ("split_hero_action_rows", ["python", "scripts/audit_split_hero_action_rows.py"]),
        ("admin_steering_strip", ["python", "scripts/verify_admin_steering_strip_contract.py"]),
        (
            "surface_preview_interactivity",
            ["python", "scripts/verify_surface_preview_interactivity.py"],
        ),
        (
            "unbounded_collection",
            ["python", "scripts/verify_unbounded_collection_surfaces.py"],
        ),
        ("large_collection", ["python", "scripts/audit_large_collection_surfaces.py"]),
    ]
    assets = [
        "static/css/rmc-cp-v8-layout-contract.css",
        "static/css/rmc-cp-v8-full-width.css",
        "static/css/rmc-dropdown-viewport-safe.css",
        "static/js/rmc-dropdown-viewport-safe.js",
        "apps/accounts/mfa_setup_flow.py",
        "templates/accounts/partials/_mfa_setup_wizard_inline.html",
        "templates/accounts/partials/_profile_security_hub.html",
        "templates/components/user_dropdown.html",
        "templates/components/rmc_operator_workspace_dropdown.html",
    ]
    missing = [a for a in assets if not (ROOT / a).is_file()]
    if missing:
        print("verify_cp_v8_operator_closeout: FAIL missing assets", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    failed = []
    for name, cmd in checks:
        code, out = _run(cmd)
        if code != 0:
            failed.append((name, _excerpt(out)))
            continue
        # Several of these children exit 0 while printing findings -- they are
        # reporters, not gates -- so the exit code above is necessary and nowhere
        # near sufficient. Each success sentinel below is anchored to the child's
        # own name: a bare `"OK" in out` would have been satisfied by any output
        # containing the word TOKEN.
        if name == "surface_spacing":
            count = _finding_count(out)
            if count is None:
                failed.append(
                    (
                        name,
                        "could not parse the child's --json output; a spacing report "
                        "this gate cannot read is not a pass.\n" + _excerpt(out),
                    )
                )
            elif count:
                failed.append((name, f"{count} spacing finding(s)\n" + _excerpt(out)))
        if name == "dead_hrefs_strict" and "0 finding" not in out:
            failed.append((name, _excerpt(out)))
        if name == "interaction_integrity" and "INTERACTION_INTEGRITY_PASS" not in out:
            failed.append((name, _excerpt(out)))
        if name == "template_render_safety" and "Total findings: 0" not in out:
            failed.append((name, _excerpt(out)))
        if name == "split_hero_action_rows" and "0 findings" not in out:
            failed.append((name, _excerpt(out)))
        if name == "admin_steering_strip" and "verify_admin_steering_strip_contract: OK" not in out:
            failed.append((name, _excerpt(out)))
        if name == "surface_preview_interactivity" and "verify_surface_preview_interactivity: OK" not in out:
            failed.append((name, _excerpt(out)))
        if name == "unbounded_collection" and "UNBOUNDED_COLLECTION_SURFACE_PASS" not in out:
            failed.append((name, _excerpt(out)))
        if name == "large_collection" and "LARGE_COLLECTION_SURFACE_PASS" not in out:
            failed.append((name, _excerpt(out)))

    if failed:
        print("verify_cp_v8_operator_closeout: FAIL", file=sys.stderr)
        for name, snippet in failed:
            print(f"  [{name}]", file=sys.stderr)
            for line in snippet.splitlines():
                print(f"    {line}", file=sys.stderr)
        return 1

    print("verify_cp_v8_operator_closeout: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
