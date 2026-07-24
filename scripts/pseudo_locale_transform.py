"""Pseudo-localization transform (pure stdlib, no Django / no polib).

Single source of truth shared by the generator management command
(`apps/siteconfig/management/commands/generate_pseudo_locale.py`) and the CI gate
(`scripts/verify_pseudo_locale.py`). Kept dependency-free so the gate can run in
the deps-free architectural-boundaries job.

Pseudo-localization is an i18n QA technique: every source string is mechanically
transformed into an obviously-foreign but still-readable variant so a reviewer can,
at a glance, spot two whole classes of bug that native translations would otherwise
be needed to surface —

  1. **Hardcoded strings** — anything that renders as plain English under the
     pseudo-locale was never wrapped in ``{% trans %}`` / ``gettext`` and is a
     missed translation site.
  2. **Layout fragility** — the transform pads every string ~40% longer (real
     translations routinely run 30–50% longer than English), so truncation and
     overflow show up before a real locale ships.

The one invariant that makes this SAFE to run is that the transform must never
touch an interpolation or markup token: a ``%(name)s`` accented into ``%(námé)s``
would raise ``KeyError`` at format time, and a mangled ``<a href>`` would break
markup. :func:`format_tokens` extracts exactly those protected tokens so the gate
can assert the pseudo output carries the identical token multiset as its source.
"""

from __future__ import annotations

import re

# Tokens that MUST pass through untouched. Order matters only for readability;
# the alternation is applied as one union with a capturing group so ``re.split``
# yields protected tokens on odd indices.
_PRINTF = r"%(?:\([^)]*\))?[#0\-\+ ]*\d*(?:\.\d+)?[hlL]?[diouxXeEfFgGcrsa%]"
_BRACE = r"\{[^{}]*\}"          # str.format fields: {}, {0}, {name}, {name:>10}
_HTML = r"</?[A-Za-z][^<>]*>"   # <b>, </a>, <a href="x">
_TOKEN_RE = re.compile("(" + "|".join([_PRINTF, _BRACE, _HTML]) + ")")

# Accent map — Latin-1 / Latin-Extended glyphs that render in virtually every
# modern font. Glyph identity is irrelevant to the gate (which checks token
# preservation, not rendering); a broad map just makes hardcoded strings pop.
_ACCENT = str.maketrans(
    {
        "a": "á", "b": "ƀ", "c": "ç", "d": "đ", "e": "é", "f": "ƒ", "g": "ğ",
        "h": "ĥ", "i": "í", "j": "ĵ", "k": "ķ", "l": "ļ", "m": "ɱ", "n": "ñ",
        "o": "ó", "p": "ƥ", "q": "q", "r": "ř", "s": "š", "t": "ţ", "u": "ú",
        "v": "ṽ", "w": "ŵ", "x": "x", "y": "ý", "z": "ž",
        "A": "Á", "B": "Ɓ", "C": "Ç", "D": "Đ", "E": "É", "F": "Ƒ", "G": "Ğ",
        "H": "Ĥ", "I": "Í", "J": "Ĵ", "K": "Ķ", "L": "Ļ", "M": "Ɱ", "N": "Ñ",
        "O": "Ó", "P": "Ƥ", "Q": "Q", "R": "Ř", "S": "Š", "T": "Ţ", "U": "Ú",
        "V": "Ṽ", "W": "Ŵ", "X": "X", "Y": "Ý", "Z": "Ž",
    }
)

_OPEN = "⟦"   # ⟦ — distinctive bracket; makes truncation visible
_CLOSE = "⟧"  # ⟧
_PAD = "·"    # · middle dot padding
_EXPANSION = 0.4   # ~40% length growth to surface layout overflow


def format_tokens(text: str) -> list[str]:
    """Sorted multiset of interpolation / markup tokens in ``text``.

    The gate's core assertion is ``format_tokens(pseudofy(s)) == format_tokens(s)``
    for every source string ``s`` — i.e. the transform preserves every ``%(x)s`` /
    ``{x}`` / ``<tag>`` exactly.
    """
    if not text:
        return []
    return sorted(m.group(0) for m in _TOKEN_RE.finditer(text))


def pseudofy(text: str) -> str:
    """Return the pseudo-localized form of ``text``.

    Protected tokens (:data:`_TOKEN_RE`) pass through verbatim; every other run of
    characters is accented. The whole string is bracketed and padded ~40% longer.
    Empty / None-ish input is returned unchanged (an empty msgstr must stay empty).
    """
    if not text:
        return text
    segments = _TOKEN_RE.split(text)
    accented_parts = []
    plain_len = 0
    for idx, seg in enumerate(segments):
        if idx % 2 == 1:
            # Protected token — never touch it.
            accented_parts.append(seg)
        else:
            plain_len += len(seg)
            accented_parts.append(seg.translate(_ACCENT))
    accented = "".join(accented_parts)
    pad = _PAD * max(1, round(plain_len * _EXPANSION))
    return f"{_OPEN}{accented} {pad}{_CLOSE}"


def token_preserving(text: str) -> bool:
    """True iff pseudofy(text) carries the identical token multiset as ``text``."""
    return format_tokens(pseudofy(text)) == format_tokens(text)


__all__ = ["pseudofy", "format_tokens", "token_preserving"]
