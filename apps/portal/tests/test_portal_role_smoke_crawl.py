"""Tenant host: portal + related URLs × role matrix (Phase 3 non-negotiable gate)."""

import os
from collections import defaultdict
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.portal.crawl_helpers import portal_smoke_response_ok
from apps.portal.portal_smoke_prerequisites import ensure_portal_smoke_prerequisites
from apps.portal.role_smoke_urls import PORTAL_ROLE_SMOKE_SEEDS
from apps.schools.models import School

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
@patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
class PortalRoleSmokeCrawlTests(TestCase):
    """Every seed URL must respond without auth-wall or hard errors for at least one declared role."""

    def setUp(self):
        self.school = School.objects.create(
            name="Smoke Crawl School",
            slug="smoke-crawl",
            subdomain="smoke-crawl",
            is_active=True,
        )
        self.host = "smoke-crawl.example.com"
        self.client_kwargs = {"HTTP_HOST": self.host}

    def test_portal_role_smoke_matrix(self):
        failures: list[str] = []
        checked = 0
        role_flags: dict = defaultdict(lambda: {"staff": False, "super": False})
        for seed in PORTAL_ROLE_SMOKE_SEEDS:
            for role in seed["roles"]:
                role_flags[role]["staff"] |= bool(seed.get("requires_staff"))
                role_flags[role]["super"] |= bool(seed.get("requires_superuser"))

        users_by_role: dict = {}
        for role, flags in role_flags.items():
            slug = role.value.lower()
            u = User.objects.create_user(
                username=f"smoke_{slug}",
                email=f"{slug}@smoke.example.com",
                password="pw",
                is_staff=flags["staff"],
                is_superuser=flags["super"],
            )
            u.role = role
            u.is_active = True
            u.save()
            users_by_role[role] = u

        ensure_portal_smoke_prerequisites(
            school=self.school,
            teacher_user=users_by_role.get(User.Role.TEACHER),
        )

        for seed in PORTAL_ROLE_SMOKE_SEEDS:
            url_name = seed["url_name"]
            try:
                path = reverse(url_name, urlconf="config.tenant_urls")
            except NoReverseMatch as e:
                failures.append(f"{url_name} NoReverseMatch: {e}")
                continue

            for role in seed["roles"]:
                u = users_by_role[role]

                client = Client(**self.client_kwargs)
                client.force_login(u)
                response = client.get(path, follow=False)
                checked += 1
                ok, reason = portal_smoke_response_ok(response)
                if not ok:
                    failures.append(
                        f"{url_name} as {role}: {reason} (HTTP {response.status_code})"
                    )

        self.assertEqual(
            failures,
            [],
            msg=f"{len(failures)} failure(s) after {checked} checks; first: {failures[:8]}",
        )
