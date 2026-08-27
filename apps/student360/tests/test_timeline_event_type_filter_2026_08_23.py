"""``get_student_timeline_feed(event_types=[...])`` returned nothing, always.

The queryset was ordered and SLICED (``[:limit]``) and only then filtered by
``event_type``. Django refuses that -- ``TypeError: Cannot filter a query once a
slice has been taken`` -- and ``TypeError`` is a member of
``_STUDENT360_SERVICE_ERRORS``, so the service swallowed it and returned ``[]``.
The documented parameter was dead, and silently so.

Ordering also mattered independently of the crash: slicing first takes the newest
``limit`` events of ANY type and then keeps whichever of those match, so a student
with 50 recent finance events and one older enrollment event would get an empty
"enrollment" feed even if filtering had worked.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.events.models import DomainEvent
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.student360.services import get_student_timeline_feed


class TimelineEventTypeFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"TL {uid}", slug=f"tl-{uid}", subdomain=f"tl{uid}", is_active=True
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school, first_name="Tim", last_name="Line",
            student_code=f"TL-{uid}",
        )
        for event_type in ("enrollment.created",) + ("finance.invoice.issued",) * 3:
            DomainEvent.objects.create(
                event_type=event_type,
                school_id=cls.school.id,
                payload={"student_id": cls.student.id},
            )

    def test_the_documented_filter_actually_filters(self) -> None:
        rows = get_student_timeline_feed(
            self.school.id, self.student.id, event_types=["enrollment.created"]
        )
        self.assertEqual(
            [r["event_type"] for r in rows],
            ["enrollment.created"],
            "event_types returned an empty feed -- the filter ran after the slice",
        )

    def test_the_filter_narrows_rather_than_empties(self) -> None:
        rows = get_student_timeline_feed(
            self.school.id, self.student.id, event_types=["finance.invoice.issued"]
        )
        self.assertEqual(len(rows), 3)

    def test_the_limit_applies_to_the_matching_events(self) -> None:
        """Slicing before filtering would have discarded matches to honour the
        limit; the limit belongs to the FILTERED set."""
        rows = get_student_timeline_feed(
            self.school.id, self.student.id,
            event_types=["finance.invoice.issued"], limit=2,
        )
        self.assertEqual(len(rows), 2)

    def test_no_filter_still_returns_everything(self) -> None:
        """Control: passes before and after the fix.

        Creating the StudentProfile itself emits a DomainEvent, so the
        unfiltered feed is a superset of the four written here rather than
        exactly four -- assert the superset relation, not a brittle count.
        """
        rows = get_student_timeline_feed(self.school.id, self.student.id)
        seen = [r["event_type"] for r in rows]
        self.assertEqual(seen.count("enrollment.created"), 1)
        self.assertEqual(seen.count("finance.invoice.issued"), 3)

    def test_another_schools_events_are_never_returned(self) -> None:
        other = School.objects.create(
            name="TL other", slug=f"tl-o-{uuid.uuid4().hex[:8]}",
            subdomain=f"tlo{uuid.uuid4().hex[:8]}",
        )
        DomainEvent.objects.create(
            event_type="enrollment.created",
            school_id=other.id,
            payload={"student_id": self.student.id},
        )
        rows = get_student_timeline_feed(
            self.school.id, self.student.id, event_types=["enrollment.created"]
        )
        self.assertEqual(len(rows), 1)
