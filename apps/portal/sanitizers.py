try:
    import bleach
except ImportError:  # pragma: no cover - fallback when bleach is unavailable
    bleach = None

from django.utils.html import strip_tags


ALLOWED_TAGS = [
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}


def sanitize_html(value: str | None) -> str:
    if not value:
        return ""

    if bleach is None:
        return strip_tags(value)

    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )
    return cleaned
