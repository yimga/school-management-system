"""``{% collapsable_body "partials/…" as body %}`` — render a partial, or nothing at all.

THE PROBLEM THIS EXISTS FOR. ``partials/cockpit/_collapsable_section.html`` wraps a
cockpit partial in a ``<details>`` so operators can fold it. Every inner partial
self-gates on ``cockpit.<section>.enabled`` and on having data, so a section with
nothing to say renders nothing — but the WRAPPER renders its chrome regardless, and
the user is left looking at a stack of empty expandables with a rule under each one.
The wrapper's own docstring admitted this and pushed the fix onto callers:

    "the partial renders nothing and the user still sees an empty expandable.
     Callers who want to avoid that should gate the include itself."

Forty-two call sites did not, which is the expected outcome of a contract that asks
every caller to remember something. The founder dashboard stacks ten of them, and the
operator sees six blank rules above the first real content on the page.

A caller-side gate also cannot be written correctly in general: the wrapper key
(``founder__tenant_heatmap``) is not the cockpit section key (``tenant_heatmap``), and
"enabled" is only half the condition — a section can be enabled with an empty data
list. The only thing that knows whether a partial rendered anything is the partial,
after it has run. So run it, then decide.

WHY NOT ``{% include %}`` PLUS A LENGTH CHECK IN THE TEMPLATE. Django templates cannot
capture ``{% include %}`` output; that is the whole reason this tag exists.

WHAT COUNTS AS "NOTHING". Whitespace, HTML comments, and the invisible
``rmc-empty-state-sentinel`` markers this codebase sprinkles for its scanners. Anything
else — including a deliberate empty-state card — is real content and is shown. The test
is deliberately conservative: a partial that renders any visible markup always survives.

COST. The partial is rendered exactly once, against the caller's own context, which is
what ``{% include %}`` already did. This tag adds a string scan, not a second render.
"""
from __future__ import annotations

import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# The hidden sentinel divs are emitted for scanners, never seen by a person. A partial
# whose entire output is one of these has rendered nothing as far as the reader is
# concerned, and a <details> wrapped around it is exactly the empty row we are removing.
_SENTINEL_RE = re.compile(
    r"<div[^>]*rmc-empty-state-sentinel[^>]*>\s*</div>", re.IGNORECASE | re.DOTALL
)


def has_visible_output(rendered: str) -> bool:
    """True when `rendered` contains anything a person would actually see."""
    if not rendered:
        return False
    stripped = _SENTINEL_RE.sub("", _COMMENT_RE.sub("", rendered))
    return bool(stripped.strip())


@register.simple_tag(takes_context=True)
def collapsable_body(context, template_name):
    """Render `template_name` in the caller's context; return "" if it renders nothing.

    Mirrors ``{% include %}`` semantics on purpose — same engine, same context, same
    template cache — so a partial cannot behave differently depending on which of the
    two pulled it in.
    """
    if not template_name:
        return ""
    engine = context.template.engine
    inner = engine.get_template(str(template_name))
    with context.push():
        rendered = inner.render(context)
    return mark_safe(rendered) if has_visible_output(rendered) else ""
