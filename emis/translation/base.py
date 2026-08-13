"""Outbound Government / Ministry reporting-format registry.

Mirrors the *inbound* accelerator registry in
``apps.migration_cloud.accelerators.base`` (register / lookup / list), but runs
in the OTHER direction: instead of pulling a vendor export INTO the platform,
each registered serializer renders a school's canonical data OUT into one
government/ministry submission format — a country's official interchange
document.

The registry is the seam a future download view / management command binds to:
look up a format by key, call ``serialize``, stream the bytes. Increment 1 ships
ONE real format (US Ed-Fi JSON, in ``edfi_json``); every additional country
registers the same way, so the engine grows without touching this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class UnknownMinistryFormat(KeyError):
    """Raised when a ministry format key has no registered serializer."""


class MinistryFormatSerializer(ABC):
    """One serializer per supported government/ministry submission format.

    Subclasses set the class attributes below and implement :meth:`serialize`.
    A subclass registers itself by decorating with :func:`register_ministry_format`.
    """

    #: Stable registry key, e.g. ``"us-edfi-json"``.
    format_key: str = ""
    #: ISO-3166 alpha-2 country this format serves, e.g. ``"US"``.
    country_code: str = ""
    #: MIME type of the serialized document.
    content_type: str = "application/octet-stream"
    #: File extension WITHOUT the dot, e.g. ``"json"``.
    file_extension: str = "dat"
    #: Human-readable one-line description (surfaced by :func:`available_ministry_formats`).
    description: str = ""

    @abstractmethod
    def serialize(self, school: Any, academic_year: Any, term: Any = None) -> str:
        """Render ``school``'s data for ``academic_year`` (optionally one ``term``) as a document string."""


# --- Registry ---------------------------------------------------------------

MinistryFormatRegistry = dict[str, type[MinistryFormatSerializer]]
_REGISTRY: MinistryFormatRegistry = {}


def register_ministry_format(
    serializer_cls: type[MinistryFormatSerializer],
) -> type[MinistryFormatSerializer]:
    """Register a serializer class under its ``format_key``. Usable as a decorator.

    Last registration wins for a given key (mirrors ``register_accelerator``).
    Returns the class unchanged so it works as a class decorator.
    """
    key = getattr(serializer_cls, "format_key", "") or ""
    if not key:
        raise ValueError(f"{serializer_cls!r} must define a non-empty format_key to register")
    _REGISTRY[key] = serializer_cls
    return serializer_cls


def get_ministry_format(format_key: str) -> type[MinistryFormatSerializer]:
    """Look up a registered serializer class by key.

    Raises :class:`UnknownMinistryFormat` (a ``KeyError`` subclass) on a miss,
    naming the keys that ARE registered so the caller can correct the request.
    """
    try:
        return _REGISTRY[format_key]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise UnknownMinistryFormat(
            f"No ministry format registered for {format_key!r}. Available: {available}"
        ) from exc


def available_ministry_formats() -> list[dict]:
    """List registered formats as dicts (key, country, content_type, extension, description)."""
    out: list[dict] = []
    for key in sorted(_REGISTRY):
        cls = _REGISTRY[key]
        out.append(
            {
                "format_key": cls.format_key,
                "country_code": cls.country_code,
                "content_type": cls.content_type,
                "file_extension": cls.file_extension,
                "description": cls.description,
            }
        )
    return out
