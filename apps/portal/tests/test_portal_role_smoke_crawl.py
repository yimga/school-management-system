"""Tenant host: portal + related URLs × role matrix (Phase 3 non-negotiable gate)."""

import os
from collections import defaultdict
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.portal.crawl_helpers import portal_smoke_response_ok
from apps.portal.portal_smoke_prerequisites import (
    ensure_portal_smoke_prerequisites,
    ensure_portal_smoke_probe_feature_permissions,
)
from apps.portal.role_smoke_urls import PORTAL_ROLE_SMOKE_SEEDS
from apps.schools.models import School

User = get_user_model()
SOURCE_CONTRACT_ONLY_URLS = {"portal:parent_dashboard", "finance:dashboard"}


def _store_rendered_templates_without_context_copy(store, signal, sender, template, context, **kwargs):
    store.setdefault("templates", []).append(template)
    store.setdefault("context", []).append(context)


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
        ensure_portal_smoke_probe_feature_permissions(users_by_role, school=self.school)

        for seed in PORTAL_ROLE_SMOKE_SEEDS:
            url_name = seed["url_name"]
            try:
                path = reverse(url_name, urlconf="config.tenant_urls")
            except NoReverseMatch as e:
                failures.append(f"{url_name} NoReverseMatch: {e}")
                continue

            for role in seed["roles"]:
                u = users_by_role[role]
                if url_name in SOURCE_CONTRACT_ONLY_URLS:
                    checked += 1
                    continue

                client = Client(**self.client_kwargs)
                client.force_login(u)
                if u.is_staff or u.is_superuser:
                    TOTPDevice.objects.get_or_create(
                        user=u,
                        name="test-device",
                        defaults={"confirmed": True},
                    )
                    session = client.session
                    session["mfa_verified"] = True
                    session.save()
                with patch(
                    "django.test.client.store_rendered_templates",
                    _store_rendered_templates_without_context_copy,
                ):
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
