"""Plan XVII: Adaptive learning / gamification kernel.

v4.00.12: closed the v3.95.0 documentation-only stub. This module is now
a working kernel:

* ``recommend_next_topic`` — given a student's recent assessment scores,
  proposes the next topic to study using a 3-tier band rule (struggling /
  on-track / advanced). Pure-Python — no DB writes.
* ``compute_leaderboard`` — given an iterable of (student_id, points)
  tuples, returns the top-N rows with ranks + ties handled.
* ``award_badge_for_achievement`` — DB integration hook (Badge + BadgeType).

Learning paths and leaderboard persistence remain in ``apps.people.Badge``
and downstream cockpit aggregators — this module is the kernel they call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopicRecommendation:
    """One next-step suggestion from the adaptive kernel."""

    topic_key: str
    rationale: str
    difficulty_band: str  # "remedial" | "on_track" | "advanced"
    confidence: float     # 0..1


def recommend_next_topic(
    *,
    recent_scores: list[float],
    current_topic_key: str,
    follow_on_topic_key: str | None = None,
    remedial_topic_key: str | None = None,
    advanced_topic_key: str | None = None,
) -> TopicRecommendation:
    """Return a topic recommendation given recent assessment scores.

    Scores expected normalized to [0, 1]. The kernel does NOT decide what
    the actual topic graph looks like — the caller passes follow-on +
    remedial + advanced keys based on their curriculum. The kernel decides
    the BAND only.

    Bands:
    * recent average < 0.55 → remedial
    * 0.55 <= average < 0.80 → on_track
    * average >= 0.80 → advanced
    """
    cleaned = [s for s in (recent_scores or []) if isinstance(s, (int, float))]
    if not cleaned:
        return TopicRecommendation(
            topic_key=follow_on_topic_key or current_topic_key,
            rationale="no recent scores; default forward",
            difficulty_band="on_track",
            confidence=0.3,
        )
    avg = sum(cleaned) / len(cleaned)
    n = len(cleaned)
    # Confidence scales with sample size (caps at n=6).
    confidence = min(1.0, max(0.3, n / 6.0))
    if avg < 0.55:
        return TopicRecommendation(
            topic_key=remedial_topic_key or current_topic_key,
            rationale=f"remedial: {n} recent scores averaged {avg:.2f}",
            difficulty_band="remedial",
            confidence=round(confidence, 3),
        )
    if avg < 0.80:
        return TopicRecommendation(
            topic_key=follow_on_topic_key or current_topic_key,
            rationale=f"on track: {n} recent scores averaged {avg:.2f}",
            difficulty_band="on_track",
            confidence=round(confidence, 3),
        )
    return TopicRecommendation(
        topic_key=advanced_topic_key or follow_on_topic_key or current_topic_key,
        rationale=f"advanced: {n} recent scores averaged {avg:.2f}",
        difficulty_band="advanced",
        confidence=round(confidence, 3),
    )


def compute_leaderboard(
    rows: list[tuple[str, int]],
    *,
    limit: int = 20,
) -> list[dict[str, int | str]]:
    """Rank ``rows`` of (student_id, points) descending by points, tie-aware.

    Returns ``[{rank, student_id, points}]`` capped at ``limit``. Ties share
    a rank; the next rank skips by the number of tied entries (standard
    competition ranking, 1224 not dense).
    """
    cleaned = [(str(sid), int(pts)) for sid, pts in (rows or []) if isinstance(pts, int)]
    sorted_rows = sorted(cleaned, key=lambda r: -r[1])
    out: list[dict[str, int | str]] = []
    prev_points: int | None = None
    prev_rank = 0
    for index, (sid, pts) in enumerate(sorted_rows[: max(1, int(limit))], start=1):
        if prev_points is not None and pts == prev_points:
            rank = prev_rank
        else:
            rank = index
        out.append({"rank": rank, "student_id": sid, "points": pts})
        prev_points = pts
        prev_rank = rank
    return out


def get_leaderboard(school, scope="school", limit=20):
    """DB-backed shim: walks ``Badge`` rows for ``school`` + uses ``compute_leaderboard``.

    Defensive: returns [] on missing models.
    """
    try:
        from apps.people.models import Badge

        if school is None or getattr(school, "pk", None) is None:
            return []
        qs = Badge.objects.filter(student__school=school)  # tenant-isolation-allow: scoped-via-student-school-filter-adaptive-leaderboard
        # Count badges per student as a proxy for "points" — schools that
        # want real points wire their own counter.
        counts: dict[str, int] = {}
        for b in qs.iterator():
            sid = str(getattr(b.student, "pk", "") or "")
            if sid:
                counts[sid] = counts.get(sid, 0) + 1
        return compute_leaderboard(list(counts.items()), limit=int(limit))
    except Exception as exc:  # noqa: BLE001 — best-effort; leaderboard widget hides on failure
        logger.debug("get_leaderboard fallback: %s", exc)
        return []


def award_badge_for_achievement(school, student, badge_type_code: str, reason: str = ""):
    """Integration hook: award a badge to a student (uses people.Badge)."""
    from apps.people.models import Badge, BadgeType

    bt = BadgeType.objects.filter(school=school, code=badge_type_code).first()  # tenant-isolation-allow: scoped-via-school-filter-badge-type-lookup
    if not bt:
        return None
    return Badge.objects.create(
        student=student,
        badge_type=bt,
        criteria_met={"reason": reason or badge_type_code},
    )
