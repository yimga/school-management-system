"""``{% emit_once "key" %}…{% endemit_once %}`` — render a block at most once per request.

Several chrome partials (``partials/rmc_platform_chrome_scripts.html``,
``components/back_to_top.html``) are pulled in from more than one place on a single
page: a shell includes the chrome-scripts bundle *and* separately includes back-to-top,
while the bundle itself also includes back-to-top — and some shells include the bundle
twice. The net effect is the same ``<script src>`` emitted up to 5× on one page, which a
browser then *re-executes* each time (wasted parse/CPU + double-bound handlers).

Wrapping a partial's body in ``{% emit_once "<key>" %}…{% endemit_once %}`` makes the first
emission render normally and every later emission in the same request render nothing — so
each asset loads once, regardless of include topology. Nothing is removed from any template
(no ``{% include %}`` deleted), so no page can lose an asset it needs; repeats are simply
suppressed. When there is no request in context (rare), the block always renders (safe
default — never suppress when we can't track).
"""
from __future__ import annotations

from django import template

register = template.Library()

_REQUEST_ATTR = "_rmc_emit_once_keys"


class EmitOnceNode(template.Node):
    def __init__(self, key: str, nodelist):
        self.key = key
        self.nodelist = nodelist

    def render(self, context):
        request = context.get("request")
        if request is not None:
            seen = getattr(request, _REQUEST_ATTR, None)
            if seen is None:
                seen = set()
                setattr(request, _REQUEST_ATTR, seen)
            if self.key in seen:
                return ""  # already emitted this request → suppress the repeat
            seen.add(self.key)
        return self.nodelist.render(context)


@register.tag("emit_once")
def emit_once(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(
            "emit_once takes exactly one argument: a quoted dedupe key"
        )
    key = bits[1].strip("\"'")
    nodelist = parser.parse(("endemit_once",))
    parser.delete_first_token()
    return EmitOnceNode(key, nodelist)
