"""AppRating helpers: submit/edit a rating, aggregate stats, publisher reply."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.marketplace.models import (
    AppInstallation,
    AppRating,
    MarketplaceApp,
)


@transaction.atomic
def submit_rating(
    *,
    app: MarketplaceApp,
    school,
    author,
    stars: int,
    headline: str = "",
    body: str = "",
) -> AppRating:
    if stars < 1 or stars > 5:
        raise ValueError("stars must be 1..5")
    verified = AppInstallation.objects.filter(
        app=app, school=school, status=AppInstallation.Status.ACTIVE
    ).exists()
    rating, _ = AppRating.objects.update_or_create(
        app=app,
        school=school,
        defaults={
            "author": author if (author and getattr(author, "is_authenticated", False)) else None,
            "stars": stars,
            "headline": headline.strip()[:120],
            "body": body.strip(),
            "verified_install": verified,
            "status": AppRating.Status.PUBLISHED,
        },
    )
    return rating


def aggregate_for_app(app: MarketplaceApp) -> dict:
    qs = AppRating.objects.filter(app=app, status=AppRating.Status.PUBLISHED)
    aggregate = qs.aggregate(
        avg=Avg("stars"),
        total=Count("id"),
        five=Count("id", filter=Q(stars=5)),
        four=Count("id", filter=Q(stars=4)),
        three=Count("id", filter=Q(stars=3)),
        two=Count("id", filter=Q(stars=2)),
        one=Count("id", filter=Q(stars=1)),
    )
    avg = aggregate["avg"] or 0
    return {
        "average": round(float(avg), 2),
        "count": aggregate["total"] or 0,
        "histogram": {
            5: aggregate["five"] or 0,
            4: aggregate["four"] or 0,
            3: aggregate["three"] or 0,
            2: aggregate["two"] or 0,
            1: aggregate["one"] or 0,
        },
    }


@transaction.atomic
def publisher_reply(rating: AppRating, *, reply_text: str) -> AppRating:
    rating.publisher_reply = reply_text.strip()
    rating.publisher_replied_at = timezone.now()
    rating.save(update_fields=["publisher_reply", "publisher_replied_at", "updated_at"])
    return rating
