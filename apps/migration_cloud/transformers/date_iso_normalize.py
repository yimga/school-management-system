"""Date normalizer — accepts the dozen formats schools actually use.

Strategy:
    1. If the value already parses as ISO date (YYYY-MM-DD), return as-is.
    2. Try a tight list of common formats in priority order, preferring the
       artifact's ``locale_hints['date_format']`` when present (the
       profiler infers MM/DD/YYYY vs DD/MM/YYYY from the value distribution
       and stores it).
    3. As a last resort, try ``dateutil`` if available; if not, raise.

The day/month ambiguity in dates like ``03/04/2010`` is real — the
profiler resolves it at the *column* level (looking at all values) and
stores the verdict on ``locale_hints``. Per-value parsing here defers to
that verdict instead of guessing again.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register

_PRIORITY_FORMATS_DEFAULT = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d/%m/%Y",   # EU shape
    "%m/%d/%Y",   # US shape
    "%d-%m-%Y",
    "%m-%d-%Y",
)


class DateIsoNormalize(Transformer):
    """Returns ISO ``YYYY-MM-DD`` string, or raises ``TransformerError``."""

    def transform(self, value: Any, ctx: TransformerContext) -> str:
        if value is None or value == "":
            raise TransformerError("Empty value cannot be normalized to a date.")
        raw = str(value).strip()

        # Already ISO? bail fast.
        try:
            return _dt.date.fromisoformat(raw).isoformat()
        except ValueError:
            pass

        formats = self._formats_for(ctx)
        for fmt in formats:
            try:
                return _dt.datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue

        # Last-ditch: dateutil if installed (broad fuzzy parsing).
        try:
            from dateutil import parser as _du  # type: ignore[import-not-found]

            parsed = _du.parse(raw, dayfirst=self._dayfirst(ctx), fuzzy=True)
            return parsed.date().isoformat()
        except Exception as exc:  # noqa: BLE001
            raise TransformerError(
                f"Could not parse date value {raw!r}: {type(exc).__name__}"
            ) from exc

    def _formats_for(self, ctx: TransformerContext) -> tuple[str, ...]:
        hint = (ctx.hints or {}).get("date_format")
        if hint and isinstance(hint, str):
            return (hint,) + _PRIORITY_FORMATS_DEFAULT
        return _PRIORITY_FORMATS_DEFAULT

    def _dayfirst(self, ctx: TransformerContext) -> bool:
        loc = str((ctx.hints or {}).get("locale", "")).lower()
        # US locale is the unusual one — day-second. Everywhere else day-first
        # is the safer default for fuzzy parses.
        return not loc.startswith(("en_us", "en-us"))


register("date_iso_normalize", DateIsoNormalize())
