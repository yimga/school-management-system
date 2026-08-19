"""Strict conversion single-primary UX: templates and guided surfaces (Experience Control)."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.academics.models import AcademicYear, Term
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


class NextActionStripTemplateTests(SimpleTestCase):
    """Unit tests for `templates/components/next_action_strip.html`."""

    def _req(self, auth: bool = True):
        rf = RequestFactory()
        request = rf.get("/portal/")
        request.user = (
            User(username="t", pk=1)
            if auth
            else AnonymousUser()
        )
        return request

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_strict_renders_single_chip_when_multiple_actions(self):
        ctx = {
            "request": self._req(True),
            "rmc_system_actions_available": True,
            "rmc_system_actions": [
                {
                    "title": "First",
                    "action_url": "/a/",
                    "type": "task",
                    "source": "engine",
                    "description": "",
                },
                {
                    "title": "Second",
                    "action_url": "/b/",
                    "type": "task",
                    "source": "engine",
                    "description": "",
                },
            ],
            "rmc_conversion_single_action_enforced": True,
        }
        html = render_to_string("components/next_action_strip.html", ctx)
        self.assertEqual(html.count('class="rmc-nas-chip"'), 1)
        self.assertIn("First", html)
        self.assertNotIn("Second", html)
        self.assertEqual(html.count("data-rmc-primary-action="), 1)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=False)
    def test_relaxed_renders_multiple_chips(self):
        ctx = {
            "request": self._req(True),
            "rmc_system_actions_available": True,
            "rmc_system_actions": [
                {
                    "title": "One",
                    "action_url": "/1/",
                    "type": "task",
                    "source": "engine",
                    "description": "",
                },
                {
                    "title": "Two",
                    "action_url": "/2/",
                    "type": "task",
                    "source": "engine",
                    "description": "",
                },
            ],
            "rmc_conversion_single_action_enforced": False,
        }
        html = render_to_string("components/next_action_strip.html", ctx)
        self.assertEqual(html.count('class="rmc-nas-chip"'), 2)


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "ux-single.example.com"],
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="example.com",
)
class GuidedSurfaceSinglePrimaryTests(TestCase):
    """HTTP integration: one dominant primary CTA when CONVERSION_SINGLE_ACTION_ENFORCED is True."""

    host = "ux-single.example.com"

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="UX Single School",
            slug="ux-single",
            subdomain="ux-single",
            is_active=True,
            settings={},
        )
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )

    def _attach(self, user: User, role: str):
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": role, "is_primary": True},
        )

    def _mark_mfa_verified(self, client: Client):
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def _enable_mfa(self, user: User):
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )

    @staticmethod
    def _store_rendered_templates_without_context_copy(
        store, signal, sender, template, context, **kwargs
    ):
        store.setdefault("templates", []).append(template)
        store.setdefault("context", []).append(context)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_teacher_dashboard_strict_one_primary_in_hero_row(self):
        u = User.objects.create_user(
            username="ux_teacher",
            password="Test1234!ab",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=u)
        self._attach(u, User.Role.TEACHER)
        c = Client()
        c.login(username="ux_teacher", password="Test1234!ab")
        r = c.get("/portal/teacher/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        # Retargeted 2026-08-18. This asserted `data-rmc-teacher-hero-actions` inside a
        # `tdm-hero__profile` chunk -- markup from the retired teacher-dashboard-modern
        # hero. The v3 role home renders components/dashboard/rmc_dh_hero.html, and the
        # single dominant CTA is owned by components/rmc_page_explain_strip.html (which
        # is also why components/next_action_strip.html suppresses itself here). Neither
        # `tdm-hero__profile` nor the old marker exists anywhere in templates/ now, so
        # the original assertion could never pass. The CONTRACT is unchanged: exactly
        # one primary action on the surface.
        self.assertEqual(
            body.count("data-rmc-primary-action"),
            1,
            "strict mode must leave exactly one primary action on the teacher role home",
        )

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_parent_dashboard_strict_one_primary_header_button(self):
        # Retargeted 2026-08-18. This read templates/parent/dashboard.html off disk and
        # required a <header> carrying `data-rmc-parent-header-actions` with a single
        # "Contact School" btn-primary. That header belonged to the pre-v3 parent
        # dashboard; the current file has no <header> and no btn-primary at all (the v3
        # family home + page-explain strip own the greeting and the next action). Assert
        # the live contract instead of dead markup.
        u = User.objects.create_user(
            username="ux_parent",
            password="Test1234!ab",
            role=User.Role.PARENT,
        )
        self._attach(u, User.Role.PARENT)
        c = Client()
        c.login(username="ux_parent", password="Test1234!ab")
        r = c.get("/portal/parent/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertEqual(
            body.count("data-rmc-primary-action"),
            1,
            "strict mode must leave exactly one primary action on the parent role home",
        )

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_backend_dashboard_strict_primary_marker_or_collapsed_strip(self):
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        u = User.objects.create_user(
            username="ux_admin",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(perm)
        self._attach(u, User.Role.ADMIN)
        self._enable_mfa(u)
        # The overview module -- which hosts the strict primary CTA and the collapsed
        # "more actions" strip -- is deliberately hidden while a school is still
        # onboarding: _resolve_setup_landing() returns True below the setup threshold
        # and BACKEND_SETUP_LANDING_HIDDEN_MODULES flips "overview" off, replacing the
        # ops centre with the focused setup surface. This fixture school was never
        # launched, so the assertion below was testing a surface that is intentionally
        # absent. Record the launch (what execute_launch does) so the overview renders.
        from apps.setup_studio.models import SetupProgress
        from django.utils import timezone

        SetupProgress.objects.update_or_create(
            school=self.school,
            defaults={"launched_at": timezone.now()},
        )
        c = Client()
        c.login(username="ux_admin", password="Test1234!ab")
        self._mark_mfa_verified(c)
        r = c.get(
            reverse("accounts:backend_dashboard"),
            HTTP_HOST=self.host,
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertTrue(
            ('data-rmc-backend-primary-overview-cta="1"' in body)
            or ("rmc-conversion-more-actions" in body),
            msg="Expected overview primary marker or collapsed secondary actions in strict mode.",
        )

    @patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
        clear=False,
    )
    @override_settings(
        CONVERSION_SINGLE_ACTION_ENFORCED=True,
        ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
        ROOT_URLCONF="config.urls",
    )
    def test_founder_dashboard_strict_collapses_secondary_toolbar_cta(self):
        from apps.schools.super_views_founder_dashboard import super_founder_dashboard

        u = User.objects.create_user(
            username="ux_founder",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        url = reverse("super:founder_dashboard")
        req = rf.get(url, HTTP_HOST="manager.runmycampus.com")
        req.user = u
        req.public_host_kind = "manager"
        r = super_founder_dashboard(req)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        nav_start = body.find('data-rmc-founder-toolbar-actions="1"')
        self.assertGreater(nav_start, -1)
        nav_end = body.find("</nav>", nav_start)
        nav = body[nav_start:nav_end]
        self.assertEqual(nav.count("btn-primary"), 1)
        self.assertIn("rmc-conversion-more-actions", nav)
        self.assertNotIn("Open Kanban pipeline", body)

    @patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
        clear=False,
    )
    @override_settings(
        CONVERSION_SINGLE_ACTION_ENFORCED=True,
        ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
        ROOT_URLCONF="config.urls",
    )
    def test_app_catalog_strict_hero_primary_and_more_actions(self):
        from apps.marketplace.views import app_catalog

        user = User.objects.create_user(
            username="ux_catalog_strict",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        url = reverse("super:app_catalog", urlconf="config.manager_urls")
        req = rf.get(url, HTTP_HOST="manager.runmycampus.com")
        req.user = user
        req.public_host_kind = "manager"
        r = app_catalog(req)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-catalog-primary-cta="1"', body)
        self.assertIn("rmc-conversion-more-actions", body)
        self.assertIn('data-rmc-catalog-hero-actions="1"', body)

    @patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
        clear=False,
    )
    @override_settings(
        CONVERSION_SINGLE_ACTION_ENFORCED=True,
        ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
        ROOT_URLCONF="config.urls",
    )
    def test_installation_health_strict_hero_primary_and_more_actions(self):
        from apps.marketplace.views import installation_health

        user = User.objects.create_user(
            username="ux_inst_health",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        url = reverse(
            "super:marketplace_installation_health", urlconf="config.manager_urls"
        )
        req = rf.get(url, HTTP_HOST="manager.runmycampus.com")
        req.user = user
        req.public_host_kind = "manager"
        r = installation_health(req)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-install-health-primary="1"', body)
        self.assertIn("rmc-conversion-more-actions", body)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_activation_first_action_single_list_cta(self):
        u = User.objects.create_user(
            username="ux_activation",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self._enable_mfa(u)
        self._attach(u, User.Role.ADMIN)
        c = Client()
        c.login(username="ux_activation", password="Test1234!ab")
        self._mark_mfa_verified(c)
        r = c.get("/activation/first-action/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-activation-single-action="1"', body)
        self.assertEqual(len(re.findall(r"class=\"[^\"]*list-group-item-primary", body)), 1)


@override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=False)
class RelaxedModeChipTests(SimpleTestCase):
    def test_relaxed_multiple_chips_from_template(self):
        req = RequestFactory().get("/")
        req.user = User(username="z", pk=2)
        html = render_to_string(
            "components/next_action_strip.html",
            {
                "request": req,
                "rmc_system_actions_available": True,
                "rmc_system_actions": [
                    {
                        "title": "A",
                        "action_url": "/a/",
                        "type": "t",
                        "source": "s",
                        "description": "",
                    },
                    {
                        "title": "B",
                        "action_url": "/b/",
                        "type": "t",
                        "source": "s",
                        "description": "",
                    },
                ],
                "rmc_conversion_single_action_enforced": False,
            },
        )
        self.assertGreaterEqual(html.count('class="rmc-nas-chip"'), 2)
