#!/usr/bin/env python
"""Studio OS Mission Cockpit shell contract (v3.53.0, 2026-05-21).

The Mission Cockpit is RETIRED. templates/studio_os/shell.html parks its markup
behind an `{% if False %}` branch with the reason inline ("Retired v3.53 empty
Mission Cockpit chrome. Kept unreachable for historical audit context while the
v4.10 one-workspace contract owns the page", v4.10.0 / 2026-07-04), and
apps/studio_os/tests/test_cockpit_shell_contract.py asserts positively that the
stylesheet must NOT load: "the retired cockpit stylesheet must not load in the
active shell".

The original gate therefore had it backwards in two directions at once:

  * it demanded studio-os-cockpit.css, contradicting that live Django test --
    the one assertion the product had cleaned up correctly was the only one it
    could see, so it failed every run; and
  * its other five assertions PASSED on text inside the retired branch. A raw
    substring test cannot tell shipped markup from parked markup, so the three
    includes and the .rmc-cockpit class "verified" against a branch no browser
    will ever receive.

What is asserted now is that the cockpit is in ONE of its two coherent states,
because a half state is the only thing that can actually break:

  WIRED   -- the block is reachable, so all three partials must be reachable,
             the .rmc-cockpit grid class must be in shipped markup, and
             studio-os-cockpit.css must be delivered.
  RETIRED -- the block is unreachable, so the stylesheet must NOT load (it would
             be dead CSS on every Studio page), and the historical partials must
             still carry their .rmc-cockpit__* hooks so the block stays revivable.

Stdlib-only. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import shell_css_contract  # noqa: E402

SHELL = REPO_ROOT / "templates" / "studio_os" / "shell.html"
PARTIALS = REPO_ROOT / "templates" / "studio_os" / "partials"

REQUIRED_INCLUDES = (
    "studio_os/partials/cockpit_signal_strip.html",
    "studio_os/partials/cockpit_canvas.html",
    "studio_os/partials/cockpit_copilot_rail.html",
)
REQUIRED_CLASSES = ("rmc-cockpit",)
REQUIRED_STYLESHEET = "studio-os-cockpit.css"

PARTIAL_EXPECTATIONS = {
    "cockpit_signal_strip.html": "rmc-cockpit__signal",
    "cockpit_canvas.html": "rmc-cockpit__canvas",
    "cockpit_copilot_rail.html": "rmc-cockpit__rail",
}


SHELL_REL = "templates/studio_os/shell.html"


def main() -> int:
    failures: list[str] = []

    if not SHELL.exists():
        print(f"FAIL: shell template missing: {SHELL.relative_to(REPO_ROOT)}")
        return 1

    raw_text = SHELL.read_text(encoding="utf-8")
    # Everything the browser actually receives: comment blocks and retired
    # `if False` branches removed.
    shipped = shell_css_contract.reachable_text(SHELL_REL)
    wired = all(inc in shipped for inc in REQUIRED_INCLUDES)
    parked = (not wired) and all(inc in raw_text for inc in REQUIRED_INCLUDES)

    if not wired and not parked:
        failures.append(
            "cockpit markup is neither wired nor parked: shell.html no longer "
            "carries all three cockpit includes, in shipped OR retired form"
        )

    for partial_name, expected_class in PARTIAL_EXPECTATIONS.items():
        path = PARTIALS / partial_name
        if not path.exists():
            failures.append(f"partial missing: {path.relative_to(REPO_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if expected_class not in text:
            failures.append(
                f"{partial_name} missing CSS hook {expected_class!r}"
            )

    css_finding = shell_css_contract.missing_stylesheet(SHELL_REL, REQUIRED_STYLESHEET)
    css_delivered = css_finding is None

    if wired:
        for cls in REQUIRED_CLASSES:
            if cls not in shipped:
                failures.append(
                    f"shell.html: cockpit is wired but {cls!r} is not in shipped markup"
                )
        if css_finding:
            failures.append(
                f"cockpit is WIRED but its stylesheet is not delivered -- {css_finding}"
            )
    elif css_delivered:
        failures.append(
            f"cockpit is RETIRED (markup parked in an unreachable branch) but "
            f"{REQUIRED_STYLESHEET} still loads on the Studio shell -- dead CSS on "
            f"every Studio page, and apps/studio_os/tests/"
            f"test_cockpit_shell_contract.py asserts it must not load"
        )

    if failures:
        print(f"FAIL: studio_os cockpit contract -- {len(failures)} violation(s)")
        for f in failures:
            print(f"  - {f}")
        return 1

    state = "WIRED" if wired else "RETIRED"
    print("PASS: studio_os cockpit contract clean")
    print(f"  shell.html: {SHELL.relative_to(REPO_ROOT)}")
    print(f"  cockpit state: {state}")
    print(f"  partials: {len(REQUIRED_INCLUDES)} historical hooks verified")
    print(
        f"  stylesheet: {REQUIRED_STYLESHEET} "
        + ("delivered" if css_delivered else "correctly absent")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
