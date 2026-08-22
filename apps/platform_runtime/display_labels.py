"""One humanizer for internal tokens that reach a human eye.

A support engineer opened Tenant 360 and read:

    Exact next confirmations: funding_type, learner_scale, connectivity,
    operating_model

Four internal dict keys, presented as the platform's own advice. The banner
promises *exactness* and then hands over the variable names. The same page
showed "Inputcompleteness" beside it, and the tenant lifecycle strip on every
school page showed "dailyoperations" — all three produced by the same mistake
in three different files.

WHY ``|cut:"_"`` IS NEVER THE ANSWER
------------------------------------
Django's ``cut`` filter *deletes* the character. It has no notion of a word
separator, so ``daily_operations`` becomes ``dailyoperations`` — the token is
now less readable than the raw slug it replaced, and CSS ``text-capitalize``
cannot rescue it because capitalize works on whitespace-delimited words and
there is no longer any whitespace. Every ``cut`` on ``_`` or ``-`` in a
template is this bug; ``scripts/scan_raw_token_in_ui.py`` is the seal.

THE TWO LAYERS
--------------
1. **A curated label**, when the token belongs to a closed vocabulary. A
   lifecycle state named ``conception`` does not mean anything to a school no
   matter how prettily it is cased; it needs the words "Being created". Closed
   vocabularies keep their labels *next to the members* (see
   ``tenant_operational_lifecycle.OPERATIONAL_STATE_LABELS`` and
   ``schools.onboarding_recommendations.CRITICAL_EVIDENCE_LABELS``) so that
   adding a member without a label is a diff a reviewer sees, and a finding the
   scanner reports.

2. **``humanize_token``**, the fallback, for open sets where the token really
   is its own explanation: ``input_completeness`` -> "Input completeness".
   Never good enough for a closed vocabulary; always better than a raw slug.

Sentence case, not Title Case: these render as *values* — inside a chip, a
banner, a sentence — not as headings. (``setup_studio.wizard_labels
.humanize_wizard_token`` title-cases because it labels wizard STEPS, which are
headings. The two are deliberately different and both are pinned by tests.)
"""

from __future__ import annotations

import re

# Segments that are uppercased whole rather than sentence-cased. Kept in sync
# with ``setup_studio.wizard_labels._ACRONYMS`` by
# ``test_display_labels_2026_08_22.AcronymParityTests`` — two humanizers that
# disagree about whether "sms" is "SMS" are worse than one that is wrong.
ACRONYMS: frozenset[str] = frozenset(
    {
        "mfa", "sms", "qr", "totp", "otp", "ai", "id", "url", "api", "sso",
        "kpi", "pos", "csv", "pdf", "dob", "sis", "lms", "pin", "2fa",
    }
)

_SEPARATORS = re.compile(r"[_\-\s]+")


def humanize_token(token: object) -> str:
    """``daily_operations`` -> ``Daily operations``; ``sms_verify`` -> ``SMS verify``.

    Safe for any input: non-strings and empties return ``""``. A word that
    already carries internal capitals (``PowerSchool``) is left alone — it is
    a proper noun someone typed on purpose, not a slug.

    The return value never contains ``_``; that is the whole point, and
    ``test_humanize_never_returns_a_separator`` holds it to that.
    """
    if not isinstance(token, str):
        return ""
    words = [w for w in _SEPARATORS.split(token.strip()) if w]
    if not words:
        return ""
    out: list[str] = []
    for index, word in enumerate(words):
        low = word.lower()
        if low in ACRONYMS:
            out.append(word.upper())
        elif any(ch.isupper() for ch in word[1:]):
            # "PowerSchool", "openSIS" — deliberate capitals, not a slug.
            out.append(word)
        elif index == 0:
            out.append(word[:1].upper() + word[1:].lower())
        else:
            out.append(low)
    return " ".join(out)


def label_for(
    registry: dict[str, object], token: object, *, default: str = ""
) -> str:
    """Curated label for ``token``, falling back to ``humanize_token``.

    ``default`` is returned only when ``token`` is empty or unusable — a
    *present but unregistered* token still gets humanized rather than
    disappearing, because a strange-looking label is recoverable and a blank
    one is not (``report_library.html`` shipped an empty ``<caption>`` for
    exactly this reason: the fallback was nothing at all).
    """
    if not isinstance(token, str) or not token.strip():
        return default
    label = registry.get(token)
    if label is None:
        return humanize_token(token)
    return str(label)


def humanize_all(tokens: object) -> list[str]:
    """Humanize an iterable of tokens, dropping anything that resolves to ``""``."""
    if isinstance(tokens, (str, bytes)) or tokens is None:
        return []
    try:
        candidates = list(tokens)  # type: ignore[arg-type]
    except TypeError:
        return []
    return [text for text in (humanize_token(t) for t in candidates) if text]


def labels_for(
    registry: dict[str, object], tokens: object
) -> list[str]:
    """``label_for`` across an iterable, preserving order and dropping blanks."""
    if isinstance(tokens, (str, bytes)) or tokens is None:
        return []
    try:
        candidates = list(tokens)  # type: ignore[arg-type]
    except TypeError:
        return []
    return [
        text for text in (label_for(registry, t) for t in candidates) if text
    ]
