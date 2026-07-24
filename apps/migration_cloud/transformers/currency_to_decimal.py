"""Currency normalizer -> decimal string.

Locale-aware separator resolution. The old implementation assumed US format
(comma = thousands, dot = decimal) and, for a comma-only value, *replaced the
comma with a dot* — so ``KES 125,000`` (the ontology's own ``finance.amount``
example) became ``125.000`` == 125, a silent 1000x under-count of every
XAF/NGN/KES/EU-formatted fee ledger. This resolver instead decides which
separator is the decimal point from its position and grouping, and consumes the
profiler's ``decimal_separator`` locale vote when present. See
docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (BLOCKER 2).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register

_KEEP = re.compile(r"[^0-9,.\-()]")


def _resolve_separators(cleaned: str, decimal_hint: str | None) -> str:
    """Return a canonical ``str`` with ``.`` as the sole decimal point.

    ``cleaned`` holds only digits, ``,`` and ``.`` (sign already stripped).
    Rules, in order:
      1. No separators              -> integer as-is.
      2. Both ``,`` and ``.``       -> the LAST-occurring one is the decimal
         separator, the other is a thousands grouping. Handles US ``1,234.56``
         and EU ``1.234,56`` / ``1.000.000,50`` alike.
      3. One separator type:
           - appears more than once  -> thousands grouping (``1,000,000``).
           - appears exactly once:
               * an explicit ``decimal_hint`` ("," or ".") decides it;
               * else 3 trailing digits -> thousands (``125,000`` -> ``125000``);
               * else (1, 2, or >3 trailing) -> decimal (``12,50`` -> ``12.50``).
    (3-decimal-minor-unit currencies e.g. KWD/BHD rely on the decimal_hint; the
    unhinted 3-trailing default matches whole-unit school fees, which dominate.)
    """
    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if not has_comma and not has_dot:
        return cleaned

    if has_comma and has_dot:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        return cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")

    sep = "," if has_comma else "."
    if cleaned.count(sep) > 1:
        return cleaned.replace(sep, "")  # repeated single separator == grouping

    if decimal_hint in (",", "."):
        if sep == decimal_hint:
            return cleaned.replace(sep, ".")
        return cleaned.replace(sep, "")  # sep is the thousands grouping

    trailing = len(cleaned.rsplit(sep, 1)[1])
    if trailing == 3:
        return cleaned.replace(sep, "")  # ambiguous -> thousands (125,000)
    return cleaned.replace(sep, ".")


class CurrencyToDecimal(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty currency value.")

        negative = (raw.startswith("(") and raw.endswith(")"))
        cleaned = _KEEP.sub("", raw).strip("()")
        neg_sign = cleaned.startswith("-")
        cleaned = cleaned.replace("-", "")
        if not cleaned:
            raise TransformerError(f"Could not parse currency value {raw!r}.")

        decimal_hint = ctx.hints.get("decimal_separator") if isinstance(ctx.hints, dict) else None
        resolved = _resolve_separators(cleaned, decimal_hint if decimal_hint in (",", ".") else None)

        if (negative or neg_sign) and not resolved.startswith("-"):
            resolved = f"-{resolved}"

        try:
            return str(Decimal(resolved))
        except InvalidOperation as exc:
            raise TransformerError(f"Could not parse currency value {raw!r}.") from exc


register("currency_to_decimal", CurrencyToDecimal())
