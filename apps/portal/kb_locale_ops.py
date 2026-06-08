"""
KB translation family ops: create locale variant + publish group (batch 1356).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils.text import slugify

LOCALE_VARIANT_TARGETS = ("fr", "es", "pt", "ar")


def create_locale_variant(
    canonical: Any,
    *,
    locale: str,
    author: Any | None = None,
) -> Any:
    from apps.portal.models_kb import KBArticle

    loc = (locale or "").strip().lower()[:12]
    if not loc:
        raise ValueError("locale_required")
    group_id = (canonical.locale_group_id or "").strip() or str(uuid.uuid4())
    if not canonical.locale_group_id:
        canonical.locale_group_id = group_id
        canonical.save(update_fields=["locale_group_id"])
    base_slug = slugify(canonical.slug or canonical.title)[:160] or f"article-{canonical.pk}"
    slug = f"{base_slug}-{loc}"[:200]
    n = 0
    school_kw = (
        {"school_id": canonical.school_id}
        if canonical.school_id
        else {"school__isnull": True}
    )
    while KBArticle.objects.filter(slug=slug, **school_kw).exists():
        n += 1
        slug = f"{base_slug}-{loc}-{n}"[:200]
    variant = KBArticle.objects.create(
        title=f"{canonical.title} ({loc})",
        slug=slug,
        category=canonical.category,
        summary=canonical.summary,
        content=canonical.content,
        content_html=canonical.content_html,
        difficulty=canonical.difficulty,
        estimated_read_time=canonical.estimated_read_time,
        tags=canonical.tags,
        author=author or canonical.author,
        status="DRAFT",
        help_audience=canonical.help_audience,
        school=canonical.school,
        is_global_article=canonical.is_global_article,
        locale=loc,
        locale_group_id=group_id,
        translation_of=canonical,
    )
    try:
        from apps.portal.kb_embeddings import refresh_kb_article_embedding

        refresh_kb_article_embedding(variant, save=True)
    except Exception:
        pass
    return variant


def publish_locale_article(article: Any, *, author: Any | None = None) -> Any:
    """Publish a single locale variant (batch 1647)."""
    from apps.portal.kb_hitl_publish import publish_kb_article

    return publish_kb_article(article, author=author)


def publish_locale_group(
    group_id: str,
    *,
    author: Any | None = None,
    school_id: int | None = None,
) -> int:
    from django.utils import timezone

    from apps.portal.kb_hitl_publish import publish_kb_article
    from apps.portal.models_kb import KBArticle

    gid = (group_id or "").strip()
    if not gid:
        return 0
    if school_id:
        group_qs = KBArticle.objects.filter(locale_group_id=gid, school_id=school_id)
    else:
        group_qs = KBArticle.objects.filter(locale_group_id=gid, school__isnull=True)
    count = 0
    for art in group_qs.exclude(status="ARCHIVED"):
        if art.status != "PUBLISHED":
            publish_kb_article(art, author=author)
            count += 1
        elif not art.published_at:
            art.published_at = timezone.now()
            art.save(update_fields=["published_at", "updated_at"])
            count += 1
    return count


def ensure_locale_variants_for_group(
    canonical: Any,
    *,
    locales: tuple[str, ...] = LOCALE_VARIANT_TARGETS,
    author: Any | None = None,
) -> list[Any]:
    created: list[Any] = []
    gid = (canonical.locale_group_id or "").strip()
    if not gid:
        gid = str(uuid.uuid4())
        canonical.locale_group_id = gid
        canonical.save(update_fields=["locale_group_id"])
    from apps.portal.models_kb import KBArticle

    if canonical.school_id:
        existing_qs = KBArticle.objects.filter(
            locale_group_id=gid, school_id=canonical.school_id
        )
    else:
        existing_qs = KBArticle.objects.filter(
            locale_group_id=gid, school__isnull=True
        )
    existing = {(a.locale or "").lower() for a in existing_qs.only("locale")}
    for loc in locales:
        if loc.lower() in existing:
            continue
        created.append(create_locale_variant(canonical, locale=loc, author=author))
    return created
