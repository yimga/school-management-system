"""Strict conversion single-primary UX: templates and guided surfaces (Experience Control)."""

from __future__ import annotations

import os
import re
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

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
        self.assertIn("data-rmc-teacher-hero-actions", body)
        start = body.find('data-rmc-teacher-hero-actions="1"')
        self.assertGreater(start, -1)
        end = body.find("tdm-hero__profile", start)
        chunk = body[start:end]
        self.assertEqual(chunk.count("btn-primary"), 1)
        self.assertIn("rmc-conversion-more-actions", chunk)

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_parent_dashboard_strict_one_primary_header_button(self):
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
        hdr_start = body.find('data-rmc-parent-header-actions="1"')
        self.assertGreater(hdr_start, -1)
        hdr_end = body.find("</header>", hdr_start)
        header_chunk = body[hdr_start:hdr_end]
        self.assertEqual(header_chunk.count("btn-primary"), 1)
        self.assertIn("data-rmc-parent-primary-header-cta", header_chunk)
        self.assertIn("Contact School", header_chunk)

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
        c = Client()
        c.login(username="ux_admin", password="Test1234!ab")
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

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_activation_first_action_single_list_cta(self):
        u = User.objects.create_user(
            username="ux_activation",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self._attach(u, User.Role.ADMIN)
        c = Client()
        c.login(username="ux_activation", password="Test1234!ab")
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
