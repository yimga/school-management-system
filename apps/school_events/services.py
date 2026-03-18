from django.db import models
from django.db.models import Count, Sum
from django.utils import timezone

from apps.school_events.models import SchoolEvent


def upcoming_public_events_for_school(school, *, limit: int = 15) -> list[dict]:
    if school is None:
        return []
    events = (
        SchoolEvent.objects.filter(
            school=school,
            status=SchoolEvent.Status.PUBLISHED,
            is_public=True,
            start_at__gte=timezone.now(),
        )
        .select_related("venue")
        .order_by("start_at")[:limit]
    )
    return [
        {
            "title": event.title,
            "when": event.start_at,
            "detail": (
                event.summary
                or (event.venue.name if event.venue_id else "")
                or event.organizer_name
                or ""
            ).strip()
            or None,
            "kind": "event",
            "slug": event.slug,
        }
        for event in events
    ]


def event_operations_snapshot(school) -> dict:
    if school is None:
        return {
            "events_total": 0,
            "published_events": 0,
            "open_registrations": 0,
            "sponsor_commitments": 0,
            "sponsorship_total": 0,
        }
    totals = SchoolEvent.objects.filter(school=school).aggregate(
        events_total=Count("id"),
        published_events=Count(
            "id", filter=models.Q(status=SchoolEvent.Status.PUBLISHED)
        ),
        open_registrations=Count("registrations", distinct=True),
        sponsor_commitment_count=Count("sponsor_commitments", distinct=True),
        sponsorship_total=Sum("sponsor_commitments__pledged_amount"),
    )
    return {
        "events_total": totals.get("events_total") or 0,
        "published_events": totals.get("published_events") or 0,
        "open_registrations": totals.get("open_registrations") or 0,
        "sponsor_commitments": totals.get("sponsor_commitment_count") or 0,
        "sponsorship_total": totals.get("sponsorship_total") or 0,
    }
