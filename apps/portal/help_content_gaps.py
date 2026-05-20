"""
Zero-result search → content ops workflow (batch 1354).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.utils import timezone


def ensure_content_gap_task(*, fingerprint: str, increment: int = 1) -> Any:
    """Upsert a gap task from zero-result telemetry (fingerprint only)."""
    from apps.feedback.models import HelpContentGapTask

    fp = (fingerprint or "").strip()[:64]
    if not fp:
        raise ValueError("fingerprint_required")
    row, _created = HelpContentGapTask.objects.get_or_create(
        query_fingerprint=fp,
        defaults={"hit_count": max(1, increment)},
    )
    if not _created and increment:
        row.hit_count = int(row.hit_count or 0) + increment
        row.save(update_fields=["hit_count", "updated_at"])
    return row


def assign_content_gap(
    task: Any,
    *,
    assignee: Any | None,
    due_date: date | None = None,
    note: str = "",
) -> Any:
    task.assigned_to = assignee
    if due_date:
        task.due_date = due_date
    elif not task.due_date:
        task.due_date = timezone.localdate() + timedelta(days=14)
    if note:
        task.note = (note or "")[:500]
    task.status = task.Status.ASSIGNED
    task.save(
        update_fields=["assigned_to", "due_date", "note", "status", "updated_at"]
    )
    return task


def create_kb_draft_from_content_gap(
    task: Any,
    *,
    author: Any | None = None,
) -> Any:
    """Draft KB article for a zero-result fingerprint cluster."""
    import uuid

    from django.utils.text import slugify

    from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory

    category = KBCategory.objects.filter(is_active=True).order_by("display_order").first()
    if category is None:
        raise ValueError("no_kb_category")
    fp = (task.query_fingerprint or "gap")[:12]
    title = f"Runbook: content gap {fp}"
    base_slug = slugify(title)[:180] or f"content-gap-{fp}"
    slug = base_slug
    n = 0
    while KBArticle.objects.filter(slug=slug, school__isnull=True).exists():
        n += 1
        slug = f"{base_slug}-{n}"[:200]
    article = KBArticle.objects.create(
        title=title,
        slug=slug,
        category=category,
        summary="Draft from zero-result content gap — expand before publish.",
        content=(
            "Draft generated from help search zero-result cluster.\n\n"
            f"Fingerprint: {fp}\n"
            f"Observed hits: {task.hit_count}\n"
        ),
        status="DRAFT",
        help_audience=HelpAudience.OPERATOR,
        author=author,
        locale_group_id=str(uuid.uuid4()),
    )
    task.kb_draft_article = article
    task.status = task.Status.DRAFTED
    task.save(update_fields=["kb_draft_article", "status", "updated_at"])
    try:
        from apps.portal.kb_embeddings import refresh_kb_article_embedding

        refresh_kb_article_embedding(article, save=True)
    except Exception:
        pass
    return article
