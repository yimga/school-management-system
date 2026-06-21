"""Template helpers for the messaging surface (IM-7)."""

import re

from django.template import Library
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = Library()

#: Same @handle shape the server resolves mentions with (see views_groups).
_MENTION_RE = re.compile(r"@([A-Za-z0-9._\-]{2,40})")


@register.filter(needs_autoescape=True)
def render_message_body(value, autoescape=True):
    """Escape message text, highlight ``@mentions``, and preserve line breaks.

    The mention token charset is HTML-safe ([A-Za-z0-9._-]), so wrapping it in a
    span after escaping cannot introduce markup. Returns safe HTML.
    """
    if value is None:
        return ""
    escaped = str(conditional_escape(value) if autoescape else value)
    highlighted = _MENTION_RE.sub(
        r'<span class="rmc-mention">@\1</span>', escaped
    )
    highlighted = highlighted.replace("\n", "<br>")
    return mark_safe(highlighted)
