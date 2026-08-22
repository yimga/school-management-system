"""``sync_request_for_target`` must key its upsert on the school.

The lookup was ``(request_type, target_content_type, target_object_id)`` with the
school only in ``defaults``. ``target_object_id`` is ``str(target.pk)`` and
``ContentType`` is a global row, so that triple is not unique across tenants:
two schools requesting the same request_type against the same target collide.
``get_or_create`` then returned the FIRST school's AccessRequest to the second
school's caller -- and because ``school`` lived in ``defaults`` it was never
written, so the row kept the wrong tenant. Every later decision on that request
(approve, deny, audit trail) acted on another school's record.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.requests.models import AccessRequest
from apps.requests.services import sync_request_for_target
from apps.schools.models import School


class SyncRequestForTargetIsSchoolScopedTests(TestCase):
    def setUp(self) -> None:
        self.school_a = School.objects.create(
            name="Req A", slug=f"rq-a-{uuid.uuid4().hex[:8]}",
            subdomain=f"rq-a-{uuid.uuid4().hex[:8]}",
        )
        self.school_b = School.objects.create(
            name="Req B", slug=f"rq-b-{uuid.uuid4().hex[:8]}",
            subdomain=f"rq-b-{uuid.uuid4().hex[:8]}",
        )
        # A single shared target: the same content_type and the same pk for both
        # callers -- exactly the collision the old lookup could not tell apart.
        self.target = School.objects.create(
            name="Shared Target", slug=f"rq-t-{uuid.uuid4().hex[:8]}",
            subdomain=f"rq-t-{uuid.uuid4().hex[:8]}",
        )

    def _sync(self, school):
        return sync_request_for_target(
            request_type=AccessRequest.RequestType.choices[0][0],
            target=self.target,
            school=school,
            title="Access please",
        )

    def test_two_schools_get_two_distinct_requests(self) -> None:
        req_a = self._sync(self.school_a)
        req_b = self._sync(self.school_b)

        self.assertNotEqual(
            req_a.pk, req_b.pk,
            "school B must get its OWN request, not school A's row back",
        )
        self.assertEqual(AccessRequest.objects.count(), 2)
        self.assertEqual(req_a.school_id, self.school_a.pk)
        self.assertEqual(
            req_b.school_id,
            self.school_b.pk,
            "the second school's request must carry the second school",
        )

    def test_same_school_twice_is_idempotent(self) -> None:
        # The fix must not break the upsert it guards.
        req1 = self._sync(self.school_a)
        req2 = self._sync(self.school_a)
        self.assertEqual(req1.pk, req2.pk)
        self.assertEqual(AccessRequest.objects.count(), 1)
