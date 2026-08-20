#!/usr/bin/env python
"""CI guard: forbid the eager-resolution ``|default:<bare_var>`` template footgun.

Django resolves EVERY ``default`` filter ARGUMENT eagerly — unconditionally, and
regardless of whether the value being defaulted is truthy. So in BOTH of these::

    {{ a|default:pending_school_name }}                 # single fallback
    {{ a|default:pending_school_name|default:"safe" }}  # defeated double fallback

resolving the bare variable ``pending_school_name`` raises ``VariableDoesNotExist``
and the page 500s whenever that variable is undefined in the render path — even
when ``a`` is truthy, and even when a later ``"safe"`` literal "should" have caught
it. (A *base* variable like ``a`` is swallowed to ``string_if_invalid``; only
filter ARGS raise. This is exactly what caused the onboarding/done 500 via
``|default:pending_school_name``.) Empirically verified: ``{{ x|default:undefined }}``
raises; ``{{ x|default:True }}``/``False``/``None`` are SAFE (Django injects those
three as context builtins); quoted/numeric/``_("…")`` args are literals (safe);
``obj.attr`` args also raise if ``obj`` is absent but are accepted here by
convention (loop vars + context-processor globals, far lower blast radius).

The fix is always ``{% firstof a bare_var "safe" %}`` (optionally ``as x``), which
resolves every operand with ``ignore_failures`` so the fallback genuinely works.

This guard fails if a bare LOWERCASE single-token variable is used as a ``default``
filter argument anywhere under ``templates/``. Mark a deliberate, proven-safe site
(e.g. the arg is guaranteed-present) with ``default-fallback-allow: <reason>`` on
the same line. Run in CI / pre-deploy::

    python scripts/verify_no_defeated_default_fallback.py
"""

from __future__ import annotations

import pathlib
import re
import sys

# A bare lowercase single-token variable used as a `default` filter arg. Excludes:
#   - True/False/None (uppercase -> not [a-z]; injected as context builtins),
#   - attribute chains obj.attr (the (?!...) drops a trailing dot),
#   - calls _( ) and literals "x"/'x'/123 (the (?!...) drops ( ' " ; [a-z] drops digits),
#   - the next filter in a chain (a trailing | is fine — that IS the value being defaulted).
PATTERN = re.compile(r"\|default:([a-z]\w*)(?![\w.(:'\"])")
ALLOW = "default-fallback-allow:"

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


_COMMENT_BLOCK = re.compile(
    r"\{%-?\s*comment\b.*?-?%\}.*?\{%-?\s*endcomment\s*-?%\}",
    re.DOTALL | re.IGNORECASE,
)
_COMMENT_INLINE = re.compile(r"\{#.*?#\}", re.DOTALL)


def _mask_comments(text: str) -> str:
    """Blank out Django template comments, preserving line structure.

    ``{% comment %}`` blocks and ``{# ... #}`` are documentation, never a render
    path, so a ``|default:bare_var`` inside one cannot raise
    VariableDoesNotExist. Non-newline characters become spaces so that reported
    line numbers still match the file on disk.
    """

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = _COMMENT_BLOCK.sub(_blank, text)
    return _COMMENT_INLINE.sub(_blank, text)


def main() -> int:
    offenders: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Marker check reads the RAW line: `default-fallback-allow:` markers live
        # in `{# ... #}` comments, which masking blanks. Pattern check reads the
        # MASKED line so documentation inside {% comment %} is not a finding.
        masked = _mask_comments(text).splitlines()
        for lineno, (raw_line, line) in enumerate(zip(text.splitlines(), masked), 1):
            if ALLOW in raw_line:
                continue
            m = PATTERN.search(line)
            if m:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}  (|default:{m.group(1)})")

    if offenders:
        sys.stderr.write(
            "Eager-resolution default-arg template footgun found "
            f"({len(offenders)} occurrence(s)).\n"
            "Each `|default:<bare_var>` 500s when <bare_var> is undefined in any "
            "render path — Django resolves the filter arg eagerly. Use "
            "{% firstof value bare_var \"fallback\" %} (optionally `as var`), or mark a "
            "proven-safe site with `default-fallback-allow: <reason>`:\n\n"
        )
        for o in offenders:
            sys.stderr.write(f"  {o}\n")
        return 1

    print("OK: no eager-resolution default-arg footguns in templates/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
