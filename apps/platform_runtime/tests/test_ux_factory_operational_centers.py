"""Operational center shell contract — headers, primary actions, honest payment risks (Agent 4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term
from apps.finance.models import ComplianceProfile
from apps.finance.views_payment_readiness_dashboard import payment_readiness_dashboard
from apps.schools.models import School, SchoolMembership


ROOT = Path(__file__).resolve().parents[3]


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


def _store_rendered_templates_without_context_copy(store, signal, sender, template, context, **kwargs):
    store.setdefault("templates", []).append(template)
    store.setdefault("context", []).append(context)


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "testserver",
        "localhost",
        "127.0.0.1",
        "manager.runmycampus.com",
    ],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
)
class OperationalCenterShellTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = "uxop4"
        self.school = School.objects.create(
            name="UX Op School",
            slug=f"ux-op-{uid}",
            subdomain=f"uxop{uid}",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="CM UX",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username=f"staff_{uid}",
            password="Pass_test_1",
            email="staffux@example.com",
            is_staff=True,
        )

    def _attach_staff_admin(self) -> User:
        user = User.objects.create_user(
            username=f"adm_{self._testMethodName}_{id(self)}",
            password="Pass_test_1",
            email="opcenter@example.com",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": user.role, "is_primary": True},
        )
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )
        return user

    def _force_login_verified(self, client: Client, user: User) -> None:
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def _get_without_context_copy(self, client: Client, url: str):
        with patch(
            "django.test.client.store_rendered_templates",
            _store_rendered_templates_without_context_copy,
        ):
            return client.get(url)

    def _enable_analytics_feature_gate(self) -> None:
        # FeatureGatekeeperMiddleware requires `analytics` for `/analytics/` (schools.middleware).
        # Plan/policy stacks may still deny; complimentary waiver grants full module access (schools.is_feature_enabled).
        feats = dict(self.school.features or {})
        feats["analytics"] = True
        self.school.features = feats
        self.school.billing_type = School.BillingType.COMPLIMENTARY
        if not (self.school.waiver_note or "").strip():
            self.school.waiver_note = "Operational UX test tenant — complimentary waiver."
        self.school.save(
            update_fields=["features", "billing_type", "waiver_note"],
        )

    def _ensure_active_year_term_for_school(self) -> None:
        year = AcademicYear.objects.filter(school=self.school, is_active=True).first()
        if not year:
            year = AcademicYear.objects.create(
                school=self.school,
                name="2025/2026",
                start_date=date(2025, 9, 1),
                end_date=date(2026, 6, 30),
                is_active=True,
            )
        if not Term.objects.filter(academic_year=year, is_active=True).exists():
            Term.objects.create(
                name=Term.Name.FIRST,
                academic_year=year,
                start_date=date(2025, 9, 1),
                end_date=date(2025, 12, 1),
                is_active=True,
            )

    def _assert_single_os_page_header(self, body: str) -> None:
        self.assertEqual(
            body.count('data-rmc-os-page-header="1"'),
            1,
            msg="Operational center must not duplicate the default workspace OS header strip",
        )

    def _assert_single_os_page_header_source(self, template: str) -> None:
        self.assertEqual(
            template.count('include "components/rmc_os_page_header.html"'),
            1,
            msg="Operational center template must include one workspace OS header",
        )

    def test_payment_readiness_center_os_contract(self):
        factory = RequestFactory()
        request = factory.get("/finance/payment-readiness/")
        request.user = self.staff
        request.school = self.school
        with patch(
            "apps.finance.views_payment_readiness_dashboard._active_profile",
            return_value=self.profile,
        ):
            response = payment_readiness_dashboard(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("data-rmc-os-page-header", body)
        self.assertIn('data-rmc-os-center="payment_readiness"', body)
        self.assertIn("data-rmc-os-primary-action", body)
        self.assertIn("metadata-only", body.lower())
        self.assertIn("external", body.lower())
        self._assert_single_os_page_header(body)

    def test_money_center_portal_single_os_header_http(self):
        template = (ROOT / "templates" / "finance" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        self._assert_single_os_page_header_source(template)
        self.assertIn('data-rmc-os-center="money_center"', template)
        self.assertIn('os_center_key="money_center"', template)

    def test_configuration_center_hub_single_os_header_http(self):
        user = self._attach_staff_admin()
        c = Client(HTTP_HOST=_tenant_host(self.school))
        self._force_login_verified(c, user)
        r = self._get_without_context_copy(c, reverse("siteconfig:dashboard_hub"))
        self.assertEqual(r.status_code, 200)
        b = r.content.decode("utf-8")
        self._assert_single_os_page_header(b)
        self.assertIn('data-rmc-os-center="configuration_center"', b)

    def test_insights_center_analytics_dashboard_single_os_header_http(self):
        self._enable_analytics_feature_gate()
        self._ensure_active_year_term_for_school()
        user = self._attach_staff_admin()
        client = Client(HTTP_HOST=_tenant_host(self.school))
        self._force_login_verified(client, user)
        response = self._get_without_context_copy(
            client,
            reverse("analytics:dashboard"),
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self._assert_single_os_page_header(body)
        self.assertIn('data-rmc-os-center="insights_center"', body)
        self.assertIn('data-rmc-ux-role-dashboard="analytics-insights"', body)
        self.assertIn('id="portal-sidebar-col"', body)
        self.assertIn('id="main-content"', body)
        self.assertIn('id="analytics-filters"', body)
        self.assertEqual(body.count('id="insights-viz"'), 1)
        self.assertEqual(body.count('id="insights-secondary"'), 1)

        template = (ROOT / "templates" / "analytics" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("improvement_rows|length", template)
        self.assertNotIn("teacher_rows|length", template)
        premium_css = (ROOT / "static" / "css" / "rmc-premium-os.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "background: var(--surface-elevated, var(--rmc-premium-surface-strong))",
            premium_css,
        )
        header_template = (
            ROOT / "templates" / "components" / "rmc_os_page_header.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("bg-body-tertiary", header_template)
        self._assert_single_os_page_header_source(template)
        self.assertIn('data-rmc-os-center="insights_center"', template)
        self.assertIn('os_center_key="insights_center"', template)

    def test_event_console_template_renders_os_header_and_primary(self):
        req = RequestFactory().get("/events/")
        req.user = AnonymousUser()
        html = render_to_string(
            "events/event_console.html",
            {
                "LANGUAGE_CODE": getattr(settings, "LANGUAGE_CODE", "en"),
                "page_title": "Event Timeline",
                "page_subtitle": "Sub",
                "domain_rows": [],
                "platform_rows": [],
                "action_url": "/backend/",
                "dlq_url": "/events/dlq/",
                "analytics_url": "/events/analytics/",
            },
            request=req,
        )
        self.assertIn("data-rmc-os-page-header", html)
        self.assertIn('data-rmc-os-center="event_timeline"', html)
        self.assertIn("data-rmc-os-primary-action", html)

    def test_offline_sync_queue_contains_os_center_and_process_action(self):
        host = _tenant_host(self.school)
        principal = User.objects.create_user(
            username=f"pri_uxop_{id(self)}",
            password="Pass_test_1",
            role=User.Role.PRINCIPAL,
            is_staff=True,
        )
        SchoolMembership.objects.get_or_create(
            user=principal,
            school=self.school,
            defaults={"role": principal.role, "is_primary": True},
        )
        c = Client(HTTP_HOST=host)
        self._force_login_verified(c, principal)
        url = reverse("portal:offline_sync_queue")
        r = self._get_without_context_copy(c, url)
        self.assertEqual(r.status_code, 200)
        b = r.content.decode("utf-8")
        self.assertIn("data-rmc-os-page-header", b)
        self.assertIn('data-rmc-os-center="offline_sync_center"', b)
        self.assertIn("offline-process-queue", b)
        self._assert_single_os_page_header(b)
