"""Thin entry point over the ministry-format registry.

``translate_school_to_ministry_format`` is the reusable API a future download
view / management command binds to: resolve the serializer by key, render the
document, and return it alongside the transport metadata a download response
needs (content-type, extension, filename). View + command are a NOTED follow-up,
not part of this increment.
"""

from __future__ import annotations

from typing import Any

from .base import get_ministry_format


def translate_school_to_ministry_format(
    school: Any,
    academic_year: Any,
    format_key: str,
    term: Any = None,
) -> dict:
    """Render ``school``'s data for ``academic_year`` in the ministry format ``format_key``.

    Returns ``{"format_key", "content_type", "file_extension", "filename", "content"}``.
    Raises :class:`~emis.translation.base.UnknownMinistryFormat` for an unregistered key.
    """
    serializer_cls = get_ministry_format(format_key)
    serializer = serializer_cls()
    content = serializer.serialize(school, academic_year, term=term)

    ext = serializer.file_extension
    school_slug = getattr(school, "slug", None) or getattr(school, "pk", None) or "school"
    year_label = _year_label(academic_year)
    filename = f"{school_slug}_{year_label}_{format_key}.{ext}"
    return {
        "format_key": format_key,
        "content_type": serializer.content_type,
        "file_extension": ext,
        "filename": filename,
        "content": content,
    }


def _year_label(academic_year: Any) -> str:
    """Filename-safe label for an academic year (its ``name`` preferred, pk fallback)."""
    raw = getattr(academic_year, "name", None) or getattr(academic_year, "pk", None) or ""
    label = str(raw).strip().replace(" ", "-").replace("/", "-")
    return label or "year"
