#!/usr/bin/env python
"""CI guard: forbid the "defeated safety fallback" template footgun.

Django resolves EVERY filter argument eagerly, even when an earlier ``default``
already won. So in a chain like::

    {{ a|default:b|default:"safe" }}

if ``b`` is a bare variable that is undefined in some render path, resolving it
raises ``VariableDoesNotExist`` and the page 500s — BEFORE the ``"safe"`` literal
fallback can ever apply. The author's safety net is dead. (A *base* variable like
``a`` is swallowed to ``string_if_invalid``; only filter ARGS raise. This is what
caused the onboarding/done 500 via ``|default:pending_school_name``.)

The fix is always ``{% firstof a b "safe" %}`` (or ``{% firstof ... as x %}``),
which resolves every operand with ``ignore_failures`` so the fallback works.

This guard fails if the pattern ``|default:<bare_standalone_var>|default:`` is
reintroduced anywhere under ``templates/``. Run in CI / pre-deploy.

    python scripts/verify_no_defeated_default_fallback.py
"""

from __future__ import annotations

import pathlib
import re
import sys

# A standalone bare-variable default arg (no dot/paren/quote -> a top-level var
# that some render path may not provide) immediately followed by ANOTHER default.
# Attribute chains (obj.attr) and literals ("x", 'x', _( )) are NOT flagged.
PATTERN = re.compile(r"\|default:([a-z_]\w*)(?![\w.(])\s*\|default:")

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def main() -> int:
    offenders: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            m = PATTERN.search(line)
            if m:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}  (|default:{m.group(1)}|default:...)")

    if offenders:
        sys.stderr.write(
            "Defeated safety-fallback template pattern found "
            f"({len(offenders)} occurrence(s)).\n"
            "Each `|default:<bare_var>|default:<fallback>` 500s when <bare_var> is "
            "undefined — the fallback is dead. Use {% firstof a b \"fallback\" %} "
            "(optionally `as var`) instead:\n\n"
        )
        for o in offenders:
            sys.stderr.write(f"  {o}\n")
        return 1

    print("OK: no defeated default-fallback patterns in templates/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
