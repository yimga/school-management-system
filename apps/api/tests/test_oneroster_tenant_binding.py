"""A tenant-bound OneRoster token must read one tenant's roster, and only one.

Two defects, one surface.

1. ``_authenticate`` enforced the token's bound tenant by comparing
   ``payload["tenant_schema"]`` to ``request.tenant.schema_name``.
   ``request.tenant`` is set only by django_tenants' TenantMainMiddleware, which
   is mounted only inside the ``USE_DJANGO_TENANTS`` branch of config/settings.py.
   On any RLS / self-host box (``USE_DJANGO_TENANTS=0`` --
   deploy/selfhost/.env.edge.example) ``req_schema`` stayed "" and the mismatch
   branch was unreachable: the check was structurally inert on exactly the
   topology that runs several schools in one schema.

2. The collection adapters were platform-scoped by construction --
   ``School.objects.all()``, ``User.objects.all()``, ``Classroom.objects.all()``.
   ``apps.accounts`` and ``apps.schools`` are SHARED_APPS, so the django-tenants
   search_path does not scope User or School either: the users and orgs
   collections returned every tenant's rows in BOTH topologies, not just RLS.

The suite runs with USE_DJANGO_TENANTS=0, which is precisely the configuration
where the original check did nothing -- so these tests exercise the real hole
rather than a simulation of it.
"""

from __future__ import annotations

import json
import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.api.oneroster_oauth2_token import _encode_access_token
from apps.schools.models import School, SchoolMembership

ROSTER_USERS_URL = "/api/roster/v1p2/users/"


class OneRosterTenantBindingTests(TestCase):
    def setUp(self) -> None:
        tag = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name="Roster A",
            slug=f"rosa-{tag}",
            subdomain=f"rosa-{tag}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Roster B",
            slug=f"rosb-{tag}",
            subdomain=f"rosb-{tag}",
            is_active=True,
        )
        self.user_a = self._member("alpha", tag, self.school_a)
        self.user_b = self._member("bravo", tag, self.school_b)
        self.token_a = _encode_access_token(
            client_id=f"client-{tag}",
            tenant_schema=self.school_a.slug,
            granted_scopes=["roster-core.readonly"],
        )

    def _member(self, name, tag, school):
        user = User.objects.create_user(
            username=f"{name}-{tag}",
            email=f"{name}-{tag}@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(user=user, school=school, role="TEACHER")
        return user

    def _get(self, host, token=None):
        return self.client.get(
            ROSTER_USERS_URL,
            {"limit": "1000"},
            HTTP_HOST=host,
            HTTP_AUTHORIZATION=f"Bearer {token or self.token_a}",
        )

    def _usernames(self, response):
        payload = json.loads(response.content.decode("utf-8"))
        return {row.get("username") for row in payload.get("users", [])}

    def test_the_token_reads_its_own_tenant(self) -> None:
        """Guard: the request must actually reach the collection.

        Without this, every "did not see the other school" assertion below would
        pass just as well against a 401, an empty envelope, or a route that moved.
        """
        response = self._get(f"{self.school_a.subdomain}.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.user_a.username, self._usernames(response))

    def test_the_token_does_not_read_the_other_tenant(self) -> None:
        response = self._get(f"{self.school_a.subdomain}.runmycampus.com")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.user_b.username, self._usernames(response))

    def test_a_token_for_one_tenant_is_refused_on_another_tenants_host(self) -> None:
        response = self._get(f"{self.school_b.subdomain}.runmycampus.com")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            json.loads(response.content.decode("utf-8")).get("error"),
            "tenant_mismatch",
        )

    def test_a_tenant_bound_token_is_refused_when_no_tenant_resolves(self) -> None:
        """Fail closed, matching this module's "no env token configured" branch.

        Honouring a tenant-named token on a request that resolves to no tenant is
        how the platform-wide projection was reachable with a scoped credential.
        """
        response = self._get("testserver")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            json.loads(response.content.decode("utf-8")).get("error"),
            "tenant_unresolved",
        )

    def test_a_token_naming_no_tenant_keeps_the_platform_projection(self) -> None:
        """An operator token with no bound tenant is unchanged by this fix."""
        unbound = _encode_access_token(
            client_id="operator",
            tenant_schema="",
            granted_scopes=["roster-core.readonly"],
        )
        response = self._get("testserver", token=unbound)
        self.assertEqual(response.status_code, 200)
        names = self._usernames(response)
        self.assertIn(self.user_a.username, names)
        self.assertIn(self.user_b.username, names)
