"""AI-assisted duplicate detection for people records.

Operators occasionally find two ``StudentProfile`` (or ``TeacherProfile``,
``StudentGuardian``) rows that *might* be the same person — same family
name + similar first name + matching guardian phone, for example. This
helper produces a confidence score + reasoning for one candidate pair so
the operator can decide whether to merge.

Used by:
- The ``people_management`` admin view (proposes candidates).
- The Migration Cloud guardian/staff landers as a second-pass cleanup
  after upsert — surfaces near-dupes for operator review.

Graceful degradation: when AI is unavailable the helper returns ``None``
and the caller falls back to a deterministic heuristic
(``deterministic_score``) that compares normalised names + birthdate +
guardian contact.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DedupProposal:
    same_person: bool
    confidence: float
    reasoning: str
    tier: str


def propose_match(
    *,
    school: Any | None,
    left: dict[str, Any],
    right: dict[str, Any],
) -> DedupProposal | None:
    """Ask the gateway whether two person records refer to the same person.

    ``left`` and ``right`` should each contain a subset of: first_name,
    last_name, middle_name, date_of_birth, gender, phone, email,
    guardian_phone, guardian_email, grade_level, address. Empty fields
    are allowed; the helper sends whatever is supplied.

    Returns ``None`` if AI is disabled or the response is unparseable.
    """
    from services.ai_helpers import invoke_json_task, looks_like_pii

    sensitivity = "high_pii" if looks_like_pii(*_iter_pii_chunks(left), *_iter_pii_chunks(right)) else "standard"
    prompt = _build_prompt(left, right)

    parsed = invoke_json_task(
        school=school,
        task_type_name="DOC_CLASSIFY",
        prompt=prompt,
        prompt_type="people.duplicate_detector",
        content_sensitivity=sensitivity,
    )
    if parsed is None:
        return None

    obj, meta = parsed
    return DedupProposal(
        same_person=bool(obj.get("same_person", False)),
        confidence=_clip(obj.get("confidence")),
        reasoning=str(obj.get("reasoning", "")).strip()[:280],
        tier=str(meta.get("tier", "unknown")),
    )


# Ceiling for a match that has NO individual-discriminator corroboration
# (only shared family / household signals). Kept just below the migration_cloud
# auto-link floor (default 0.95) so such a pair falls to review instead of
# auto-merging two distinct people.
_NO_INDIVIDUAL_MATCH_CAP = 0.90


def deterministic_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Cheap deterministic similarity (0..1).

    Used as the AI fallback and as a pre-filter before AI is even invoked:
    if the deterministic score is < 0.4 we don't ask the model — clearly
    different people. If > 0.95 we don't ask either — clearly the same.
    The middle band is where AI judgment helps.
    """
    score = 0.0
    weights = 0.0

    def normalise(v: Any) -> str:
        return " ".join(str(v or "").strip().lower().split())

    fields = ("last_name", "first_name", "middle_name", "date_of_birth", "guardian_phone", "phone", "email")
    weights_map = {"last_name": 0.30, "first_name": 0.25, "middle_name": 0.10,
                   "date_of_birth": 0.20, "guardian_phone": 0.05, "phone": 0.05, "email": 0.05}
    # Fields that distinguish an INDIVIDUAL within a family / household. A match
    # here (not just on shared family signals) is required to reach the
    # auto-link band — see the cap below.
    individual_fields = ("first_name", "email")
    individual_match = False

    for field in fields:
        l = normalise(left.get(field))
        r = normalise(right.get(field))
        if not l or not r:
            continue
        weights += weights_map[field]
        if l == r:
            score += weights_map[field]
            if field in individual_fields:
                individual_match = True
        else:
            # Partial credit on first-name overlap and substring matches.
            if field in ("first_name", "last_name") and (l[:3] == r[:3]):
                score += weights_map[field] * 0.4
                if field == "first_name":
                    individual_match = True
    if weights == 0:
        return 0.0
    result = round(score / weights, 3)
    if not individual_match:
        # Skipping a blank field shrinks the denominator, so a match on FAMILY /
        # HOUSEHOLD signals alone (last_name + date_of_birth, or last_name + a
        # shared guardian_phone) saturated the ratio to 1.0 — but twins share a
        # surname + birthdate and a household shares a surname + phone, so those
        # signals do NOT establish the SAME PERSON. Without a matching individual
        # discriminator (first name or email) the pair must fall to review / AI,
        # never silently auto-merge two distinct people. Cap below the auto-link
        # floor (migration_cloud.dedup.autolink_min_score defaults to 0.95).
        result = min(result, _NO_INDIVIDUAL_MATCH_CAP)
    return result


def _build_prompt(left: dict[str, Any], right: dict[str, Any]) -> str:
    safe_left = {k: v for k, v in left.items() if v not in (None, "")}
    safe_right = {k: v for k, v in right.items() if v not in (None, "")}
    return (
        "You are a person-records dedup assistant for a school management "
        "platform. Decide whether two person records refer to the same "
        "person. Return JSON only.\n\n"
        f"Record A: {safe_left}\n"
        f"Record B: {safe_right}\n\n"
        'Return JSON exactly: {"same_person": <true|false>, '
        '"confidence": <0..1>, "reasoning": "<one sentence citing the strongest evidence>"}'
    )


def _iter_pii_chunks(record: dict[str, Any]):
    for key in ("first_name", "last_name", "middle_name", "email", "phone",
                "guardian_phone", "guardian_email", "address", "date_of_birth"):
        v = record.get(key)
        if v:
            yield str(v)


def _clip(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))
