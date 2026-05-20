"""
HITL review queue → KB draft article (batch 1348).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils.text import slugify


def create_kb_draft_from_review(review: Any, *, author: Any | None = None) -> Any:
    from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory

    category = KBCategory.objects.filter(is_active=True).order_by("display_order").first()
    if category is None:
        raise ValueError("no_kb_category")
    fp = (review.query_fingerprint or "review")[:12]
    title = f"Runbook: support AI review {fp}"
    base_slug = slugify(title)[:180] or f"ai-review-{fp}"
    slug = base_slug
    n = 0
    review_school = getattr(review, "school", None)
    while KBArticle.objects.filter(slug=slug, school=review_school).exists():
        n += 1
        slug = f"{base_slug}-{n}"[:200]
    audience = (
        HelpAudience.OPERATOR if getattr(review, "is_operator", False) else HelpAudience.TENANT
    )
    content = (
        "Draft generated from AI review queue.\n\n"
        f"Context URL: {(review.active_url or '')[:500]}\n"
        f"Outcome: {(review.outcome or '')[:64]}\n"
        f"Fingerprint: {fp}\n"
    )
    article = KBArticle.objects.create(
        title=title,
        slug=slug,
        category=category,
        summary="Operator draft from HITL queue — review before publish.",
        content=content,
        status="DRAFT",
        help_audience=audience,
        school=getattr(review, "school", None),
        author=author,
        locale_group_id=str(uuid.uuid4()),
    )
    review.kb_draft_article = article
    review.note = (review.note or "")[:400] + f"\nKB draft: {article.slug}"
    review.save(update_fields=["kb_draft_article", "note"])
    try:
        from apps.portal.kb_embeddings import refresh_kb_article_embedding

        refresh_kb_article_embedding(article, save=True)
    except Exception:
        pass
    return article


def publish_kb_article(article: Any, *, author: Any | None = None) -> Any:
    """One-click publish for HITL / content-gap drafts (batch 1354)."""
    from django.utils import timezone

    article.status = "PUBLISHED"
    if not article.published_at:
        article.published_at = timezone.now()
    if author is not None and not article.author_id:
        article.author = author
    article.save(update_fields=["status", "published_at", "author", "updated_at"])
    return article
