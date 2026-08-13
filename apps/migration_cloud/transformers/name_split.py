"""Name splitter — turns full-name strings into (first, middle, last).

Two registered variants:
    * ``name_split_first_last``: source values look like "Ada Lovelace" or
      "Ada Augusta Lovelace".
    * ``name_split_last_first``: source values look like "Lovelace, Ada"
      or "Lovelace, Ada Augusta".

The mapper picks which to use based on the column profile (the profiler
detects the comma pattern). When unsure, the AI tiebreaker picks.

Honors locales where the family-name-first convention is the cultural
default (Hungarian, Japanese, Korean, Vietnamese, etc.) via the
``ctx.hints['name_order']`` hint when present.

Returns the *requested component* — the canonical field on the mapping
edge specifies which one we want. ``ctx.options['component']`` must be
one of ``first``, ``middle``, ``last``, ``full``.
"""

from __future__ import annotations

from typing import Any

from .base import Transformer, TransformerContext, TransformerError, register


def _split_first_last(raw: str) -> tuple[str, str, str]:
    parts = [p for p in raw.split() if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _split_last_first(raw: str) -> tuple[str, str, str]:
    if "," in raw:
        last_chunk, first_chunk = (s.strip() for s in raw.split(",", 1))
        given_parts = [p for p in first_chunk.split() if p]
        if not given_parts:
            return "", "", last_chunk
        if len(given_parts) == 1:
            return given_parts[0], "", last_chunk
        return given_parts[0], " ".join(given_parts[1:]), last_chunk

    # No comma — treat as space-separated "Lastname Firstname [Middle…]"
    # which is the cultural default in many East Asian + Hungarian + some
    # African contexts. Two tokens: last + first. Three+ tokens: last,
    # first, then middle parts get rolled into middle_name.
    parts = [p for p in raw.split() if p]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[1], "", parts[0]
    return parts[1], " ".join(parts[2:]), parts[0]


class NameSplitFirstLast(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty name.")
        first, middle, last = _split_first_last(raw)
        return _pick(ctx, first, middle, last, full=raw)


class NameSplitLastFirst(Transformer):
    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty name.")
        first, middle, last = _split_last_first(raw)
        return _pick(ctx, first, middle, last, full=raw)


def _split_spanish_double(raw: str) -> tuple[str, str, str, str]:
    """Split a Hispanic-style 'Given Paterno Materno' or 'Given Given Paterno Materno'.

    Returns (first_name, middle_name, paternal_surname, maternal_surname).
    Heuristic: last token = maternal_surname, second-to-last = paternal,
    everything before = first + middle.
    """
    parts = [p for p in raw.split() if p]
    if not parts:
        return "", "", "", ""
    if len(parts) == 1:
        return parts[0], "", "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1], ""
    if len(parts) == 3:
        return parts[0], "", parts[1], parts[2]
    # 4+ tokens: first + middles + paternal + maternal
    return parts[0], " ".join(parts[1:-2]), parts[-2], parts[-1]


class NameSplitSpanishDouble(Transformer):
    """Hispanic two-surname convention (paternal + maternal).

    ``ctx.options['component']`` accepts the four-component vocabulary plus
    a back-compat ``last`` that returns paternal+maternal joined.
    """

    def transform(self, value: Any, ctx: TransformerContext) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise TransformerError("Empty name.")
        first, middle, paternal, maternal = _split_spanish_double(raw)
        component = str((ctx.options or {}).get("component", "")).strip().lower()
        if not component:
            cf = (ctx.canonical_field or "").lower()
            if cf.endswith(("first_name", "given_name")):
                component = "first"
            elif cf.endswith("middle_name"):
                component = "middle"
            elif cf.endswith(("paternal_surname", "apellido_paterno")):
                component = "paternal"
            elif cf.endswith(("maternal_surname", "apellido_materno")):
                component = "maternal"
            elif cf.endswith(("last_name", "family_name", "surname", "apellido")):
                component = "last"
            else:
                component = "full"
        if component == "first":
            return first
        if component == "middle":
            return middle
        if component == "paternal":
            return paternal
        if component == "maternal":
            return maternal
        if component == "last":
            joined = " ".join(p for p in (paternal, maternal) if p)
            return joined or raw
        return raw


class NameSplitLocale(Transformer):
    """Locale-aware dispatcher.

    Picks the right split variant based on the country (``ctx.hints['country']``)
    or an explicit ``ctx.options['name_order']`` (``first_last`` |
    ``last_first`` | ``spanish_double``). Falls back to the comma heuristic.
    """

    _FALLBACK = NameSplitFirstLast()
    _LAST_FIRST = NameSplitLastFirst()
    _SPANISH = NameSplitSpanishDouble()

    def transform(self, value: Any, ctx: TransformerContext) -> str:
        order = str((ctx.options or {}).get("name_order", "")).strip().lower()
        if not order:
            country = (ctx.hints or {}).get("country") or (ctx.options or {}).get("country")
            if country:
                from apps.migration_cloud.country_profiles import resolved_country_profile

                profile = resolved_country_profile(str(country))
                if profile is not None:
                    order = profile.name_order
        raw = str(value or "")
        if order == "last_first" or ("," in raw and not order):
            return self._LAST_FIRST.transform(value, ctx)
        if order == "spanish_double":
            return self._SPANISH.transform(value, ctx)
        return self._FALLBACK.transform(value, ctx)


def _pick(
    ctx: TransformerContext, first: str, middle: str, last: str, *, full: str
) -> str:
    component = str((ctx.options or {}).get("component", "")).strip().lower()
    if not component:
        # Infer from the canonical_field if no explicit option.
        cf = (ctx.canonical_field or "").lower()
        if cf.endswith(("first_name", "given_name")):
            component = "first"
        elif cf.endswith(("last_name", "family_name", "surname")):
            component = "last"
        elif cf.endswith("middle_name"):
            component = "middle"
        else:
            component = "full"

    if component == "first":
        return first
    if component == "middle":
        return middle
    if component == "last":
        return last
    return full


def split_full_name(
    raw: Any, *, order: str | None = None, country: str | None = None
) -> tuple[str, str, str]:
    """Split a single combined-name string into ``(first, middle, last)``.

    Locale-aware: an explicit ``order`` (``first_last`` | ``last_first`` |
    ``spanish_double``) wins; otherwise the destination ``country``'s
    ``name_order`` profile is consulted; finally the comma heuristic decides.
    This is the plain-function twin of ``NameSplitLocale`` for callers that
    need every component at once (the student/staff landers splitting a
    combined ``full_name`` column into first + last so the row is not
    quarantined for "missing first/last").
    """
    raw = str(raw or "").strip()
    if not raw:
        return "", "", ""
    order = (order or "").strip().lower()
    if not order and country:
        try:
            from apps.migration_cloud.country_profiles import resolved_country_profile

            profile = resolved_country_profile(str(country))
            if profile is not None:
                order = (profile.name_order or "").strip().lower()
        except Exception:  # noqa: BLE001 — profile lookup never blocks a split
            order = ""
    if order == "last_first" or ("," in raw and not order):
        return _split_last_first(raw)
    if order == "spanish_double":
        first, middle, paternal, maternal = _split_spanish_double(raw)
        last = " ".join(p for p in (paternal, maternal) if p)
        return first, middle, last
    return _split_first_last(raw)


register("name_split_first_last", NameSplitFirstLast())
register("name_split_last_first", NameSplitLastFirst())
register("name_split_spanish_double", NameSplitSpanishDouble())
register("name_split_locale", NameSplitLocale())
