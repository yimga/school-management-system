"""Government / Ministry reporting translation engine (M32, increment 1).

Public surface: the outbound format registry (``base``) + the thin entry point
(``service``). Importing this package registers every bundled serializer — the
``edfi_json`` import below runs ``@register_ministry_format`` as a side effect,
so ``get_ministry_format("us-edfi-json")`` resolves after ``import emis.translation``.
"""

from __future__ import annotations

from .base import (
    MinistryFormatSerializer,
    UnknownMinistryFormat,
    available_ministry_formats,
    get_ministry_format,
    register_ministry_format,
)
from .service import translate_school_to_ministry_format

# Side-effect import: registers EdFiJsonSerializer via @register_ministry_format.
# Keep last so the registry funcs above are defined before registration runs.
from . import edfi_json  # noqa: F401  (imported for its registration side effect)

__all__ = [
    "MinistryFormatSerializer",
    "UnknownMinistryFormat",
    "available_ministry_formats",
    "get_ministry_format",
    "register_ministry_format",
    "translate_school_to_ministry_format",
    "edfi_json",
]
