"""Pure-function validators for the Unified Wizard Framework.

No Django dependencies — fully unit-testable. Each validator returns
``(is_valid, error_token_or_none)`` so the engine can collect a per-field
error map without raising.

Error tokens map to i18n keys under ``wizards.errors.*``.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "DEFAULT_MAX_TEXT_FIELD_LENGTH",
    "validate_required",
    "validate_text_within_cap",
    "validate_max_length",
    "validate_min_length",
    "validate_pattern",
    "validate_in_choices",
    "validate_decimal_range",
    "validate_integer_range",
    "validate_domain_format",
    "validate_color_hex",
    "validate_file_extension",
    "validate_file_size_bytes",
    "validate_csv_header",
    "validate_pfx_certificate_shape",
    "validate_iso_country_code",
    "validate_iso_currency_code",
    "validate_email_shape",
]


# Global backstop for free-text length. A field that declares no explicit
# ``max_length`` rule must still not be able to write an unbounded string into
# SetupProgress.step_state (a JSONField) — that path is a cheap storage-DoS and
# bloats every subsequent read of the row. The engine resolves the effective cap
# (env-tunable) and only applies it when no explicit ``max_length`` is declared,
# so an author who opts into a specific bound always wins. 20k chars comfortably
# fits long-form descriptions / pasted policy text while blocking abuse.
DEFAULT_MAX_TEXT_FIELD_LENGTH = 20_000  # magic-number-allow: named-constant-definition (env-tunable free-text cap)

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ISO_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_required(value: Any) -> tuple[bool, str | None]:
    if value is None:
        return False, "wizards.errors.required"
    if isinstance(value, str) and value.strip() == "":
        return False, "wizards.errors.required"
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False, "wizards.errors.required"
    return True, None


def validate_text_within_cap(value: Any, cap: int) -> tuple[bool, str | None]:
    """Global free-text backstop — distinct token from the per-field max_length
    so telemetry can tell ``author set max_length=N, user exceeded it`` apart from
    ``unbounded field hit the platform cap``. Only strings are bounded; non-str
    values pass through (their own typed validators handle them)."""
    if isinstance(value, str) and len(value) > cap:
        return False, "wizards.errors.text_too_long"
    return True, None


def validate_max_length(value: Any, max_len: int) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if isinstance(value, str) and len(value) > max_len:
        return False, "wizards.errors.max_length"
    return True, None


def validate_min_length(value: Any, min_len: int) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if isinstance(value, str) and len(value) < min_len:
        return False, "wizards.errors.min_length"
    return True, None


def validate_pattern(value: Any, pattern: str) -> tuple[bool, str | None]:
    # Emptiness is the ``required`` validator's job, not the shape check's — an
    # optional field left blank submits "" and must not trip a pattern. Mirrors
    # validate_max_length / validate_min_length, which also pass on absent input.
    if value is None or not isinstance(value, str) or value == "":
        return True, None
    try:
        if not re.match(pattern, value):
            return False, "wizards.errors.pattern_mismatch"
    except re.error:
        return False, "wizards.errors.pattern_invalid"
    return True, None


def validate_in_choices(value: Any, choices: list[Any]) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if isinstance(value, list):
        for v in value:
            if v not in choices:
                return False, "wizards.errors.choice_not_in_set"
        return True, None
    if value not in choices:
        return False, "wizards.errors.choice_not_in_set"
    return True, None


def _to_decimal(value: Any) -> Decimal | None:
    """Decimal-only — money_float gate enforced. Returns None on parse fail."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def validate_decimal_range(
    value: Any,
    *,
    min: str | None = None,
    max: str | None = None,
) -> tuple[bool, str | None]:
    d = _to_decimal(value)
    if d is None and value is not None:
        return False, "wizards.errors.decimal_invalid"
    if d is None:
        return True, None
    if min is not None:
        min_d = _to_decimal(min)
        if min_d is not None and d < min_d:
            return False, "wizards.errors.decimal_below_min"
    if max is not None:
        max_d = _to_decimal(max)
        if max_d is not None and d > max_d:
            return False, "wizards.errors.decimal_above_max"
    return True, None


def validate_integer_range(
    value: Any,
    *,
    min: int | None = None,
    max: int | None = None,
) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    try:
        i = int(value)
    except (TypeError, ValueError):
        return False, "wizards.errors.integer_invalid"
    if min is not None and i < min:
        return False, "wizards.errors.integer_below_min"
    if max is not None and i > max:
        return False, "wizards.errors.integer_above_max"
    return True, None


def validate_domain_format(value: Any) -> tuple[bool, str | None]:
    if value is None or value == "":
        return True, None
    if not isinstance(value, str):
        return False, "wizards.errors.domain_invalid"
    candidate = value.strip().lower()
    if not _DOMAIN_RE.match(candidate):
        return False, "wizards.errors.domain_invalid"
    return True, None


def validate_color_hex(value: Any) -> tuple[bool, str | None]:
    if value is None or value == "":
        return True, None
    if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
        return False, "wizards.errors.color_hex_invalid"
    return True, None


def validate_file_extension(value: Any, allowed: list[str]) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    # File-like objects (Django UploadedFile etc.) carry the filename on .name
    if not isinstance(value, str) and hasattr(value, "name"):
        filename = getattr(value, "name", None)
    else:
        filename = value
    if not isinstance(filename, str) or "." not in filename:
        return False, "wizards.errors.file_extension_invalid"
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in [a.lower().lstrip(".") for a in allowed]:
        return False, "wizards.errors.file_extension_not_allowed"
    return True, None


def validate_file_size_bytes(value: Any, max_bytes: int) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    # File-like objects carry the byte count on .size
    if not isinstance(value, (int, str)) and hasattr(value, "size"):
        size = getattr(value, "size", None)
    else:
        size = value
    try:
        s = int(size)
    except (TypeError, ValueError):
        return False, "wizards.errors.file_size_invalid"
    if s > max_bytes:
        return False, "wizards.errors.file_too_large"
    return True, None


def validate_csv_header(headers: Any, required: list[str]) -> tuple[bool, str | None]:
    if headers is None:
        return False, "wizards.errors.csv_header_missing"
    if not isinstance(headers, list):
        return False, "wizards.errors.csv_header_invalid"
    norm = {str(h).strip().lower() for h in headers}
    for req in required:
        if req.strip().lower() not in norm:
            return False, "wizards.errors.csv_header_required_missing"
    return True, None


def validate_pfx_certificate_shape(b: Any) -> tuple[bool, str | None]:
    """Shape-only. Confirms PKCS#12 ASN.1 magic prefix. Live validation deferred."""
    if b is None:
        return True, None
    if not isinstance(b, (bytes, bytearray)):
        return False, "wizards.errors.pfx_not_bytes"
    if len(b) < 16:
        return False, "wizards.errors.pfx_too_small"
    # PKCS#12 files start with ASN.1 SEQUENCE tag (0x30) followed by length bytes.
    if b[0] != 0x30:
        return False, "wizards.errors.pfx_magic_invalid"
    return True, None


def validate_iso_country_code(value: Any) -> tuple[bool, str | None]:
    if value is None or value == "":
        return True, None
    if not isinstance(value, str) or not _ISO_COUNTRY_RE.match(value):
        return False, "wizards.errors.country_code_invalid"
    return True, None


def validate_iso_currency_code(value: Any) -> tuple[bool, str | None]:
    if value is None or value == "":
        return True, None
    if not isinstance(value, str) or not _ISO_CURRENCY_RE.match(value):
        return False, "wizards.errors.currency_code_invalid"
    return True, None


def validate_email_shape(value: Any) -> tuple[bool, str | None]:
    if value is None or value == "":
        return True, None
    if not isinstance(value, str) or not _EMAIL_SHAPE_RE.match(value):
        return False, "wizards.errors.email_invalid"
    return True, None
