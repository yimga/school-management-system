"""Entity-grounding guardrail for AI-generated narratives.

12-pillar audit P8 follow-up. The platform's AI narration paths
(``apps/analytics/management/commands/ai_narrate_risk_digest.py``,
the at-risk explainer, and future narrative endpoints) emit
text that may reference students, classes, or schools. A
hallucinating LLM can introduce names that weren't in the input
context — a privacy and trust defect.

This module provides a deterministic grounding check:

  * :func:`assert_grounded(narrative, allowed_names, ...)` —
    raises :class:`UngroundedNarrativeError` when the narrative
    mentions a proper-noun-shaped token that isn't in the
    allowlist (after a small list of safe stopwords).

The check is **conservative**: a proper noun is any whitespace-
delimited token that starts with an uppercase letter and is at
least 2 characters long. It treats consecutive capitalized
tokens as a single multi-word name ("Aisha Mohammed", "St. Mary").
The allowlist is the set of names + first/last components
already present in the input context (typically the
``_fact_bullets`` student names).

Caller pattern (recommended for new narration code paths):

    from apps.analytics.ai_narration_grounding import assert_grounded

    allowed = collect_entities_from_input(facts)
    narrative = ai_gateway.invoke(prompt=prompt, ...)
    try:
        assert_grounded(narrative, allowed)
    except UngroundedNarrativeError as exc:
        logger.warning("AI narrative ungrounded: %s", exc.unknown_entities)
        narrative = ""  # fall back to bullets only

The existing ``ai_narrate_risk_digest`` already has a safe
fallback (empty string when the gateway fails); plugging this
guardrail in is a one-call-site change covered by
``apps/analytics/tests/test_ai_narration_grounding.py``.
"""

from __future__ import annotations

import re
from typing import Iterable

# Safe capitalized words that aren't entity names. Keep the list
# conservative -- false negatives leak hallucinations; false positives
# are merely noisy logs.
_SAFE_CAPITALIZED_TOKENS = frozenset({
    # Sentence-start English connectives + auxiliaries.
    "The", "A", "An", "This", "That", "These", "Those",
    "We", "I", "You", "They", "He", "She", "It",
    "Their", "His", "Her", "Our", "My", "Your", "Its",
    "Today", "Tomorrow", "Yesterday", "Now", "Soon", "Next",
    "However", "Therefore", "Meanwhile", "Also", "And", "Or", "But",
    "Note", "Tip", "Important", "Warning", "If", "When", "While",
    "Because", "Since", "Although", "Despite", "After", "Before",
    # Common sentence-start verbs.
    "Reach", "Call", "Email", "Schedule", "Send", "Talk", "Speak",
    "Meet", "Review", "Check", "Follow", "Continue", "Start", "Stop",
    "Consider", "Note", "Look", "See", "Watch", "Try", "Use", "Make",
    "Take", "Give", "Get", "Set", "Run", "Build", "Plan",
    # Common school-domain non-entities.
    "School", "Student", "Students", "Teacher", "Teachers",
    "Parent", "Parents", "Class", "Classes", "Grade", "Grades",
    "Term", "Subject", "Subjects", "Risk", "Score", "Band",
    "Action", "Step", "Plan", "Goal", "Success", "Team",
    "Attendance", "Math", "Reading", "English", "Science", "History",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    # Common digest scaffold tokens.
    "Narrative", "Header", "Footer",
})

# Regex: match a single capitalized token. We assemble multi-word
# entities downstream by sliding the window forward.
_CAP_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z'\-\.]{1,}\b")


class UngroundedNarrativeError(ValueError):
    """Narrative contains entities not present in the input context."""

    def __init__(self, narrative: str, unknown_entities: list[str]):
        self.narrative = narrative
        self.unknown_entities = unknown_entities
        super().__init__(
            f"Narrative references {len(unknown_entities)} ungrounded "
            f"entity token(s): {unknown_entities!r}"
        )


def extract_proper_nouns(text: str) -> list[str]:
    """Return all proper-noun-shaped tokens in ``text``.

    Algorithm: scan single capitalized tokens, drop safe stopwords
    (sentence-start verbs, articles, weekdays, school-domain
    vocabulary), then coalesce *adjacent* unsafe capitalized tokens
    into a single entity ("Aisha Mohammed" -> one entity).
    """
    if not text:
        return []
    # Find each capitalized token + its character span.
    raw_hits: list[tuple[int, int, str]] = [
        (m.start(), m.end(), m.group(0).strip("."))
        for m in _CAP_TOKEN_RE.finditer(text)
    ]
    # Drop safe stopwords.
    unsafe_hits: list[tuple[int, int, str]] = [
        (s, e, t) for (s, e, t) in raw_hits
        if t and t not in _SAFE_CAPITALIZED_TOKENS
    ]
    # Coalesce adjacent unsafe tokens that are separated only by a
    # whitespace run in the source text (no intervening punctuation).
    entities: list[str] = []
    i = 0
    while i < len(unsafe_hits):
        s, e, token = unsafe_hits[i]
        parts = [token]
        last_end = e
        j = i + 1
        while j < len(unsafe_hits):
            ns, ne, ntoken = unsafe_hits[j]
            gap = text[last_end:ns]
            # Allow merging only when the gap is a single space run.
            if gap.strip() == "" and "\n" not in gap and len(gap) <= 2:
                parts.append(ntoken)
                last_end = ne
                j += 1
                continue
            break
        entities.append(" ".join(parts))
        i = j
    # De-dup preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for ent in entities:
        if ent in seen:
            continue
        seen.add(ent)
        ordered.append(ent)
    return ordered


def _expand_allowed(allowed_names: Iterable[str]) -> set[str]:
    """Build a permissive allowlist that also accepts each space-
    separated part of a multi-word name. "Aisha Mohammed" implicitly
    allows "Aisha" and "Mohammed" individually."""
    expanded: set[str] = set()
    for raw in allowed_names:
        if not raw:
            continue
        name = raw.strip().strip(".")
        if not name:
            continue
        expanded.add(name)
        for part in name.split():
            part = part.strip().strip(".")
            if part and part not in _SAFE_CAPITALIZED_TOKENS:
                expanded.add(part)
    return expanded


def assert_grounded(narrative: str, allowed_names: Iterable[str]) -> None:
    """Raise :class:`UngroundedNarrativeError` on ungrounded entities.

    ``allowed_names`` is the set of entity names the narrative is
    permitted to reference (typically student / class / school
    names extracted from the prompt input).
    """
    allowed = _expand_allowed(allowed_names)
    found = extract_proper_nouns(narrative)
    unknown = [t for t in found if t not in allowed]
    if unknown:
        raise UngroundedNarrativeError(narrative, unknown)


def is_grounded(narrative: str, allowed_names: Iterable[str]) -> bool:
    """Non-raising convenience wrapper."""
    try:
        assert_grounded(narrative, allowed_names)
    except UngroundedNarrativeError:
        return False
    return True


__all__ = [
    "UngroundedNarrativeError",
    "extract_proper_nouns",
    "assert_grounded",
    "is_grounded",
]
