"""Currency normalizer -> decimal string."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register

_KEEP = re.compile(r"[^0-9,.\-()]")


class CurrencyToDecimal(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty currency value.")

        negative = raw.startswith("(") and raw.endswith(")")
        cleaned = _KEEP.sub("", raw).strip("()")
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        if negative and not cleaned.startswith("-"):
            cleaned = f"-{cleaned}"

        try:
            return str(Decimal(cleaned))
        except InvalidOperation as exc:
            raise TransformerError(f"Could not parse currency value {raw!r}.") from exc


register("currency_to_decimal", CurrencyToDecimal())
