"""``/api/v1/crdt/apply/`` is a write sink, so it must be a BOUNDED one.

Two holes, both reachable by any signed-in user:

* ``parse_wire_op`` caps neither key length nor value size, and ``_write_state``
  merges the accumulated state into ``School.settings`` -- a JSONField on the row
  ``_resolve_school_from_request`` loads on EVERY request to that tenant.  200 ops
  of padded keys and fat values per request, repeated, degrade every page load for
  the whole school.  Nothing reads ``crdt_state`` back, so nothing evicts it either.
* the only gate was ``login_required``, so standing in the tenant was never checked
  at all -- ``_bound_actor_id`` and ``_validate_key_namespace`` are scoping guards,
  not authorization.

The rail's own doc says it "is sized for the small, approved namespaces above; it
is not a general document store" -- these pin that in code.
"""

from __future__ import annotations

import json
import uuid

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.views_crdt import CRDTOpsApplyView


class _CRDTBoundsFixture(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="CRDT {0}".format(uid),
            slug="crdt-{0}".format(uid),
            subdomain="crdt{0}".format(uid),
        )
        self.user = User.objects.create_user(
            username="member-{0}".format(uid), password="x"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="TEACHER", is_primary=True
        )

    def _post(self, ops, *, user=None, school=None):
        request = self.factory.post(
            "/api/v1/crdt/apply/",
            data=json.dumps({"ops": ops, "device_id": "device-a"}),
            content_type="application/json",
        )
        request.user = user or self.user
        request.tenant = school or self.school
        return CRDTOpsApplyView().post(request)

    @staticmethod
    def _lww(key, value):
        return {
            "kind": "LWW",
            "entity": "student_note",
            "key": key,
            "value": value,
            "hlc": "100:0:wire",
        }


class CRDTKeyAndValueAreBoundedTests(_CRDTBoundsFixture):
    def test_an_oversized_key_is_rejected(self):
        response = self._post([self._lww("student_note:" + "p" * 40_000, "x")])
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 0)
        self.assertTrue(body["rejected"])

    def test_an_oversized_value_is_rejected(self):
        response = self._post([self._lww("student_note:draft-1", "y" * 200_000)])
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 0)
        self.assertTrue(body["rejected"])

    def test_an_ordinary_op_still_applies(self):
        """Not vacuous: the caps must not have simply broken the endpoint."""
        response = self._post([self._lww("student_note:draft-1", "a local draft")])
        body = json.loads(response.content)
        self.assertEqual(body["applied"], 1, body)
        self.school.refresh_from_db()
        self.assertIn("student_note:draft-1", self.school.settings["crdt_state"]["lww"])

    def test_the_persisted_state_has_a_ceiling(self):
        """Many individually-legal ops must not add up to an unbounded settings blob."""
        from apps.sync_engine import views_crdt

        cap = views_crdt._max_state_bytes()
        chunk = "z" * 2000
        # Enough legal ops to blow past the ceiling if nothing is watching the total.
        needed = (cap // len(chunk)) + 50
        for start in range(0, needed, 100):
            self._post(
                [
                    self._lww("student_note:d{0}".format(i), chunk)
                    for i in range(start, min(start + 100, needed))
                ]
            )
        self.school.refresh_from_db()
        stored = json.dumps(self.school.settings.get("crdt_state") or {})
        self.assertLessEqual(len(stored.encode("utf-8")), cap)


class CRDTStandingInTheTenantIsRequiredTests(_CRDTBoundsFixture):
    def test_a_user_with_no_membership_in_this_school_is_refused(self):
        outsider = User.objects.create_user(username="outsider", password="x")
        response = self._post(
            [self._lww("student_note:draft-1", "not mine to write")], user=outsider
        )
        self.assertEqual(response.status_code, 403)
        self.school.refresh_from_db()
        self.assertNotIn("crdt_state", self.school.settings)

    def test_a_member_of_another_school_is_refused(self):
        other = School.objects.create(
            name="Other", slug="other-crdt-bounds", subdomain="othercrdtbounds"
        )
        stranger = User.objects.create_user(username="stranger", password="x")
        SchoolMembership.objects.create(
            user=stranger, school=other, role="ADMIN", is_primary=True
        )
        response = self._post(
            [self._lww("student_note:draft-1", "wrong tenant")], user=stranger
        )
        self.assertEqual(response.status_code, 403)

    def test_a_suspended_membership_is_refused(self):
        from django.utils import timezone

        SchoolMembership.objects.filter(user=self.user, school=self.school).update(
            suspended_at=timezone.now()
        )
        response = self._post([self._lww("student_note:draft-1", "suspended")])
        self.assertEqual(response.status_code, 403)

    def test_platform_staff_still_pass(self):
        staff = User.objects.create_superuser(
            username="platform-staff", email="s@test.com", password="x"
        )
        response = self._post([self._lww("student_note:draft-1", "ok")], user=staff)
        self.assertEqual(response.status_code, 200)
