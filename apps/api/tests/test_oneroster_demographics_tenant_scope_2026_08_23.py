"""A tenant-bound OneRoster token must not read another tenant's demographics.

``test_oneroster_tenant_binding.py`` closed the binding + collection-scoping hole
for orgs / users / classes in ``apps.api.oneroster``: ``_authenticate`` now falls
back to the RLS tenant handle, and every adapter there is bound to the resolved
school through ``_scoped``/``_roster_scope_school``.

``apps/api/oneroster_demographics.py`` was left behind. It imports ``_gate`` from
that module -- so it inherited the fixed AUTHENTICATION -- but none of its five
StudentProfile queries were ever narrowed: ``_iter_demographics`` did a bare
``StudentProfile.objects.all()``, and the detail / student / POST / PUT paths
resolved a profile by pk or user id with no tenant test at all. So a token minted
for school A, presented on school A's own host (which now passes the binding
check), read -- and WROTE -- every school's student demographics.

Demographics is the most sensitive projection on this surface: date of birth,
sex, place of birth.
"""

from __future__ import annotations

import json
import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.api.oneroster_oauth2_token import _encode_access_token
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership

COLLECTION_URL = "/api/roster/v1p2/demographics/"


class OneRosterDemographicsTenantScopeTests(TestCase):
    def setUp(self) -> None:
        tag = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name="Demo A", slug=f"dema-{tag}", subdomain=f"dema-{tag}", is_active=True
        )
        self.school_b = School.objects.create(
            name="Demo B", slug=f"demb-{tag}", subdomain=f"demb-{tag}", is_active=True
        )
        self.student_a = self._student("alpha", tag, self.school_a)
        self.student_b = self._student("bravo", tag, self.school_b)
        self.token_a = _encode_access_token(
            client_id=f"client-{tag}",
            tenant_schema=self.school_a.slug,
            granted_scopes=["roster-core.readonly"],
        )
        self.host_a = f"{self.school_a.subdomain}.runmycampus.com"

    def _student(self, name, tag, school) -> StudentProfile:
        user = User.objects.create_user(
            username=f"{name}-{tag}",
            email=f"{name}-{tag}@example.com",
            password="pass12345678",
            role=User.Role.STUDENT,
        )
        SchoolMembership.objects.create(user=user, school=school, role="STUDENT")
        return StudentProfile.objects.create(
            school=school,
            user=user,
            first_name=name.title(),
            last_name="Tester",
            place_of_birth=f"{name}-town",
        )

    def _get(self, url, token=None, host=None):
        return self.client.get(
            url,
            {"limit": "1000"},
            HTTP_HOST=host or self.host_a,
            HTTP_AUTHORIZATION=f"Bearer {token or self.token_a}",
        )

    def _sourced_ids(self, response):
        payload = json.loads(response.content.decode("utf-8"))
        return {row.get("sourcedId") for row in payload.get("demographics", [])}

    def test_the_token_reads_its_own_tenant(self) -> None:
        """Guard: the request must actually reach the collection.

        Without this, every "did not see the other school" assertion below would
        pass equally well against a 401, an empty envelope or a moved route.
        """
        response = self._get(COLLECTION_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"demo-{self.student_a.pk}", self._sourced_ids(response))

    def test_the_collection_does_not_leak_the_other_tenant(self) -> None:
        response = self._get(COLLECTION_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f"demo-{self.student_b.pk}", self._sourced_ids(response))

    def test_detail_by_sourced_id_finds_its_own_tenant(self) -> None:
        """Guard for the two detail assertions below: the route resolves and 200s."""
        response = self._get(f"{COLLECTION_URL}demo-{self.student_a.pk}/")
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content.decode("utf-8"))
        self.assertEqual(body["demographic"]["sourcedId"], f"demo-{self.student_a.pk}")

    def test_detail_by_sourced_id_refuses_the_other_tenant(self) -> None:
        response = self._get(f"{COLLECTION_URL}demo-{self.student_b.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_student_demographics_refuses_the_other_tenant(self) -> None:
        response = self._get(
            f"/api/roster/v1p2/students/{self.student_b.user_id}/demographics/"
        )
        self.assertEqual(response.status_code, 404)

    def _post(self, inner):
        return self.client.post(
            f"{COLLECTION_URL}put/",
            data=json.dumps({"demographic": inner}),
            content_type="application/json",
            HTTP_HOST=self.host_a,
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
        )

    def test_post_by_sourced_id_cannot_write_the_other_tenants_student(self) -> None:
        """The upsert falls through to ``studentSourcedId`` when the demo- id misses.

        Scoping the first lookup makes school B's profile miss, so the handler
        asks for the alternative identifier instead of writing the row -- a
        refusal, not a silent success.
        """
        response = self._post(
            {"sourcedId": f"demo-{self.student_b.pk}", "cityOfBirth": "overwritten"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.content.decode("utf-8")).get("error"),
            "missing_student_sourced_id",
        )
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.place_of_birth, "bravo-town")

    def test_post_by_student_sourced_id_cannot_write_the_other_tenant(self) -> None:
        response = self._post(
            {
                "studentSourcedId": str(self.student_b.user_id),
                "cityOfBirth": "overwritten",
            }
        )
        self.assertEqual(response.status_code, 404)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.place_of_birth, "bravo-town")

    def test_post_still_writes_its_own_tenants_student(self) -> None:
        """Guard: the write path is reachable, so the refusals above mean something."""
        response = self._post(
            {
                "studentSourcedId": str(self.student_a.user_id),
                "cityOfBirth": "alpha-city",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.place_of_birth, "alpha-city")

    def test_put_cannot_write_the_other_tenants_student(self) -> None:
        response = self.client.put(
            f"{COLLECTION_URL}demo-{self.student_b.pk}/put/",
            data=json.dumps({"demographic": {"cityOfBirth": "overwritten"}}),
            content_type="application/json",
            HTTP_HOST=self.host_a,
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
        )
        self.assertEqual(response.status_code, 404)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.place_of_birth, "bravo-town")

    def test_a_token_naming_no_tenant_keeps_the_platform_projection(self) -> None:
        """An operator token with no bound tenant is unchanged by this fix."""
        unbound = _encode_access_token(
            client_id="operator", tenant_schema="", granted_scopes=["roster-core.readonly"]
        )
        response = self._get(COLLECTION_URL, token=unbound, host="testserver")
        self.assertEqual(response.status_code, 200)
        ids = self._sourced_ids(response)
        self.assertIn(f"demo-{self.student_a.pk}", ids)
        self.assertIn(f"demo-{self.student_b.pk}", ids)
