from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User


class FakeSiteSettings(SimpleNamespace):
    def __getattr__(self, name):
        defaults = {
            "theme_brightness": "system",
            "footer_links": [],
            "footer_badges": [],
            "footer_status_text": "",
            "footer_support_hours": "",
            "footer_whatsapp_url": "",
            "site_name": "School Management System",
            "tagline": "",
            "show_header_search": True,
            "show_header_notifications": True,
            "show_header_profile_menu": True,
            "show_header_theme_toggle": True,
            "brand_font": "",
            "secondary_font": "",
            "use_secondary_font_for_headings": False,
            "base_font_size": 16,
        }
        return defaults.get(name, None)

    def get_theme_background(self, *args, **kwargs):
        return None

    def get_theme_logo_opacity(self):
        return 1.0

    def get_theme_logo_bg_mode(self):
        return "light"

    def get_admin_theme(self):
        return None


class FakeLinkList(list):
    def prefetch_related(self, *args, **kwargs):
        return self

    def count(self):
        return len(self)

    def exists(self):
        return bool(self)


class DashboardCustomLayoutTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            "parentbro", "parent@example.com", "testpass123"
        )
        self.user.role = User.Role.PARENT
        self.user.save()
        self.student_stub = SimpleNamespace(id=1)
        link = SimpleNamespace(student=self.student_stub)
        self.links = FakeLinkList([link])

    def _fake_guardian_links(self, user, results_only=False, finance_only=False):
        if finance_only:
            return FakeLinkList()
        return self.links if results_only else self.links

    def _fake_widget_data(self):
        return {
            "attendance": {"overall": 0, "per_student": []},
            "attendance_trend": [],
            "grade_trend": [],
            "subject_performance": [],
            "performance": {"per_student": []},
            "finance": {
                "total_due": Decimal("0.00"),
                "paid": Decimal("0.00"),
                "balance": Decimal("0.00"),
            },
            "tasks": {"pending_evaluations": 0},
            "analytics": {"label": "N/A", "highlights": [], "lowlights": []},
            "fees_breakdown": {
                "percent": 0,
                "paid": "0.00",
                "due": "0.00",
                "overdue": 0,
            },
            "assignment_completion": {
                "percent": 0,
                "complete": 0,
                "pending": 0,
                "total": 0,
            },
            "events": [],
        }

    def test_parent_dashboard_exposes_custom_layout_context(self):
        site_payload = FakeSiteSettings(
            portal_quick_actions=[],
            portal_announcements=[],
            portal_recent_grades=[],
            portal_upcoming_assessments=[],
            portal_features={},
            backend_feature_flags={},
            active_theme=None,
            report_downloads_enabled=False,
            preview_mode_enabled=False,
            preview_note="",
        )
        widget_data = self._fake_widget_data()
        url = reverse("portal:parent_dashboard")
        self.client.force_login(self.user)

        # django.shortcuts.render() returns HttpResponse without template context attached;
        # the test client therefore cannot expose response.context. Capture the dict here.
        render_context = {}

        def _fake_render(request, template_name, context=None, **_kwargs):
            render_context.clear()
            if context:
                render_context.update(context)
            return HttpResponse(b"ok", status=200)

        with (
            patch(
                "apps.portal.services.guardian_student_links",
                side_effect=self._fake_guardian_links,
            ),
            patch(
                "apps.portal.services.parent_dashboard_widget_data",
                return_value=widget_data,
            ),
            patch(
                "apps.portal.services.class_announcements_for_parent", return_value=[]
            ),
            patch("apps.portal.services.class_threads_for_parent", return_value=[]),
            patch("apps.portal.views_parent._portal_features_status", return_value=[]),
            patch(
                "apps.platform_runtime.helpers.get_effective_site_settings",
                return_value=site_payload,
            ),
            patch(
                "apps.siteconfig.models_support.filter_portal_items",
                side_effect=lambda items, role: items or [],
            ),
            patch(
                "apps.runtime_blueprints.models.get_dashboard_widget_metadata",
                return_value={},
            ),
            patch("apps.portal.views_parent.render", side_effect=_fake_render),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        context = render_context
        self.assertTrue(context["allow_custom_layout"])
        self.assertIn("dashboard_settings", context)
        self.assertEqual(context["dashboard_settings"]["tile_variant"], "default")
        self.assertEqual(context["dashboard_settings"]["show_sidebar"], False)
        self.assertEqual(len(context["available_sidebar_items"]), 4)
        self.assertEqual(context["widget_meta_json"], "{}")
        self.assertIn("finance_access_banner", context)
