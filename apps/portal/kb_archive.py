"""
KB auto-archive workflow from helpfulness signals (batch 1356).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class KbArchiveCandidate:
    article_id: int
    slug: str
    reason: str
    helpful: int
    unhelpful: int


def stale_kb_archive_candidates(
    *,
    min_votes: int = 5,
    unhelpful_ratio: float = 2.0,
    stale_days: int = 365,
    limit: int = 200,
) -> list[KbArchiveCandidate]:
    """
    Published articles eligible for archival:
    - unhelpful votes dominate (>= min_votes total, unhelpful > helpful * ratio), or
    - no updates for stale_days and net negative helpfulness.
    """
    from apps.portal.kb_context import published_kb_queryset

    cutoff = timezone.now() - timedelta(days=stale_days)
    out: list[KbArchiveCandidate] = []
    qs = (
        published_kb_queryset()
        .exclude(status="ARCHIVED")
        .order_by("-unhelpful_count", "-updated_at")[: max(limit * 3, limit)]
    )
    for art in qs:
        helpful = int(art.helpful_count or 0)
        unhelpful = int(art.unhelpful_count or 0)
        total = helpful + unhelpful
        reason = ""
        if total >= min_votes and unhelpful > helpful * unhelpful_ratio:
            reason = "unhelpful_skew"
        elif (
            art.updated_at
            and art.updated_at < cutoff
            and total >= 3
            and unhelpful > helpful
        ):
            reason = "stale_negative"
        if reason:
            out.append(
                KbArchiveCandidate(
                    article_id=art.pk,
                    slug=art.slug,
                    reason=reason,
                    helpful=helpful,
                    unhelpful=unhelpful,
                )
            )
        if len(out) >= limit:
            break
    return out


def archive_kb_articles(
    candidates: list[KbArchiveCandidate],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    from apps.portal.models_kb import KBArticle

    ids = [c.article_id for c in candidates]
    if dry_run:
        return {"dry_run": True, "would_archive": len(ids), "ids": ids[:50]}
    # tenant-isolation-allow: archive-by-explicit-pk-list-from-stale-candidate-scan
    updated = KBArticle.objects.filter(pk__in=ids).exclude(status="ARCHIVED").update(
        status="ARCHIVED", updated_at=timezone.now()
    )
    return {"dry_run": False, "archived": updated, "ids": ids[:50]}
