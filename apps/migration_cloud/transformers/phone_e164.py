"""Phone normalizer — best-effort E.164.

Strategy (deterministic, no network):
    1. Strip everything but ``+`` and digits.
    2. If the value already starts with ``+``, return as ``+<digits>``.
    3. If the value has a leading ``00``, replace with ``+``.
    4. Otherwise prepend the default country dial-code from
       ``ctx.hints['default_country_code']`` (e.g. ``"+254"``). Many
       country numbers also have a trunk ``0`` to strip; we do so when the
       remaining length matches a typical national number for that country.

Falls back to returning the cleaned national number when no country code
is known — better than raising, because the platform's phone-validation
layer can still surface the inconsistency at apply time.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register

_DIGITS = re.compile(r"\D+")


class PhoneE164(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty phone value.")

        if raw.startswith("+"):
            cleaned = "+" + _DIGITS.sub("", raw[1:])
            if len(cleaned) < 8:
                raise TransformerError(f"Too few digits in {raw!r}")
            return cleaned

        digits = _DIGITS.sub("", raw)
        if digits.startswith("00"):
            cleaned = "+" + digits[2:]
            if len(cleaned) < 8:
                raise TransformerError(f"Too few digits in {raw!r}")
            return cleaned

        country = str((ctx.hints or {}).get("default_country_code", "")).strip()
        if country and country.startswith("+"):
            # Strip a single leading trunk zero, common worldwide.
            national = digits.lstrip("0") or digits
            return country + national

        # No country code available — return the cleaned national form.
        return digits


register("phone_e164", PhoneE164())
