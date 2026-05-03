"""Closure slice: lifecycle state machine + operator dashboard + cohort metrics gates."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.billing.models import BillingAccount, TenantSubscription
from apps.platform_runtime.customer_health import calculate_school_health
from apps.platform_runtime.onboarding import (
    get_school_onboarding_steps,
    mark_school_onboarding_step_complete,
)
from apps.platform_runtime.tenant_lifecycle_operator import (
    build_lifecycle_dashboard_context,
    build_lifecycle_operator_row,
    compute_portfolio_activation_metrics,
    resolve_primary_action_url,
)
from apps.platform_runtime.tenant_lifecycle_state_machine import (
    STATE_ACTIVATED,
    STATE_AT_RISK,
    STATE_EXPANSION_READY,
    STATE_PAYING,
    STATE_SIGNUP_STARTED,
    resolve_tenant_lifecycle_state,
)
from apps.platform_runtime.views_tenant_lifecycle import tenant_lifecycle_dashboard
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.models import TenantReportSchedule
from apps.schools.models import MarketingFunnelEvent, School


def _funnel_row(school, event_type: str, *, minutes: int = 0):
    return MarketingFunnelEvent.objects.create(
        event_type=event_type,
        school=school,
        session_key="",
        utm_source="",
        utm_medium="",
        metadata={},
        created_at=timezone.now() + timedelta(minutes=minutes),
    )


class TenantLifecycleClosureSliceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Life A",
            slug="life-a",
            subdomain="life-a",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )
        cls.school_b = School.objects.create(
            name="Life B",
            slug="life-b",
            subdomain="life-b",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )

    def test_activation_after_first_action_event(self):
        _funnel_row(self.school_a, "signup_completed")
        _funnel_row(self.school_a, "first_action", minutes=1)
        out = resolve_tenant_lifecycle_state(self.school_a)
        self.assertEqual(out["state"], STATE_ACTIVATED)

    def test_paying_after_subscription_active_and_payment_success(self):
        ba, _ = BillingAccount.objects.get_or_create(
            school=self.school_a,
            defaults={"status": BillingAccount.Status.ACTIVE},
        )
        TenantSubscription.objects.create(
            billing_account=ba,
            school=self.school_a,
            status=TenantSubscription.Status.ACTIVE,
            billed_amount=Decimal("120.00"),
        )
        _funnel_row(self.school_a, "subscription_started", minutes=0)
        _funnel_row(self.school_a, "payment_success", minutes=1)
        out = resolve_tenant_lifecycle_state(self.school_a)
        self.assertEqual(out["state"], STATE_PAYING)

    def test_at_risk_from_payment_failed_after_success(self):
        ba, _ = BillingAccount.objects.get_or_create(
            school=self.school_a,
            defaults={"status": BillingAccount.Status.ACTIVE},
        )
        TenantSubscription.objects.create(
            billing_account=ba,
            school=self.school_a,
            status=TenantSubscription.Status.ACTIVE,
            billed_amount=Decimal("50.00"),
        )
        _funnel_row(self.school_a, "subscription_started", minutes=0)
        _funnel_row(self.school_a, "payment_success", minutes=1)
        _funnel_row(self.school_a, "payment_failed", minutes=120)
        out = resolve_tenant_lifecycle_state(self.school_a)
        self.assertEqual(out["state"], STATE_AT_RISK)
        self.assertIn("latest_payment_event_failed", out["reasons"])

    def test_time_to_first_value_from_funnel_snapshot(self):
        _funnel_row(self.school_a, "onboarding_start", minutes=0)
        _funnel_row(self.school_a, "first_result", minutes=60)
        from apps.schools.funnel_metrics import get_school_funnel_metrics_snapshot

        snap = get_school_funnel_metrics_snapshot(self.school_a.id)
        self.assertIsNotNone(snap.get("time_to_first_value_seconds"))
        self.assertGreater(snap["time_to_first_value_seconds"], 0)

    def test_portfolio_metrics_insufficient_without_sample(self):
        sid = self.school_b.id
        MarketingFunnelEvent.objects.filter(school_id=sid).delete()
        _funnel_row(self.school_b, "onboarding_start")
        m = compute_portfolio_activation_metrics(min_sample=50, school_ids=[sid])
        self.assertTrue(m["insufficient_data"])

    def test_primary_action_urls_nonempty(self):
        for sk in (
            STATE_ACTIVATED,
            STATE_PAYING,
            STATE_AT_RISK,
            STATE_EXPANSION_READY,
        ):
            self.assertTrue(
                resolve_primary_action_url(sk, viewer_scope="tenant", school_id=1)
            )
            self.assertTrue(
                resolve_primary_action_url(sk, viewer_scope="platform", school_id=1)
            )

    def test_tenant_dashboard_context_only_own_school_rows(self):
        ctx = build_lifecycle_dashboard_context([self.school_a], viewer_scope="tenant")
        self.assertEqual(len(ctx["rows"]), 1)
        self.assertEqual(ctx["rows"][0]["school_id"], self.school_a.id)

    def test_platform_context_lists_multiple_when_passed(self):
        ctx = build_lifecycle_dashboard_context(
            [self.school_a, self.school_b], viewer_scope="platform"
        )
        self.assertEqual(len(ctx["rows"]), 2)

    def test_operator_row_has_contract_fields(self):
        _funnel_row(self.school_a, "signup_completed")
        row = build_lifecycle_operator_row(self.school_a, viewer_scope="tenant")
        for key in (
            "state_key",
            "label",
            "reason",
            "evidence",
            "primary_action_url",
            "severity",
            "computed_at",
        ):
            self.assertIn(key, row)

    def _seed_deep_school(self, school: School, *, admin: User):
        ay = AcademicYear.objects.create(
            school=school,
            name="LY",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_active=True,
        )
        dept = Department.objects.create(school=school, name="Core", code=f"d-{school.pk}")
        Classroom.objects.create(
            academic_year=ay,
            department=dept,
            name="Form 1A",
            code=f"c-{school.pk}-1a",
            school=school,
        )
        for i in range(5):
            tu = User.objects.create_user(
                username=f"t{school.pk}_{i}",
                email=f"t{school.pk}_{i}@e.test",
                password="x" * 8,
                role=User.Role.TEACHER,
            )
            TeacherProfile.objects.create(school=school, user=tu)
        for i in range(48):
            su = User.objects.create_user(
                username=f"s{school.pk}_{i}",
                email=f"s{school.pk}_{i}@e.test",
                password="x" * 8,
                role=User.Role.STUDENT,
            )
            StudentProfile.objects.create(
                school=school,
                user=su,
                first_name="S",
                last_name=str(i),
                date_of_birth=date(2014, 1, 1),
                student_code=f"st-{school.pk}-{i}",
                is_active=True,
            )
        TenantReportSchedule.objects.create(
            school=school,
            name="Weekly digest",
            report_key="summary",
            schedule_frequency=TenantReportSchedule.Frequency.WEEKLY,
            schedule_time=timezone.now().time(),
            recipients=["cfo@school.test"],
            next_run=timezone.now(),
            created_by=admin,
        )
        for key in ("ccc", "marketplace", "data_migration", "guided_configuration"):
            mark_school_onboarding_step_complete(school, key)
        for row in get_school_onboarding_steps(school):
            if not row.get("done"):
                mark_school_onboarding_step_complete(school, str(row.get("key")))

    def test_expansion_ready_when_paid_depth_signals(self):
        admin = User.objects.create_user(
            username="adm_exp",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        s = School.objects.create(
            name="ExpandCo",
            slug="expand-co",
            subdomain="expand-co",
            is_active=True,
            last_activity=timezone.now(),
            billing_type=School.BillingType.REGULAR,
        )
        self._seed_deep_school(s, admin=admin)
        health = calculate_school_health(s)
        self.assertGreaterEqual(
            health["score"],
            77,
            msg=f"fixture score too low for expansion gate: {health}",
        )
        ba, _ = BillingAccount.objects.get_or_create(
            school=s,
            defaults={"status": BillingAccount.Status.ACTIVE},
        )
        TenantSubscription.objects.create(
            billing_account=ba,
            school=s,
            status=TenantSubscription.Status.ACTIVE,
            billed_amount=Decimal("200.00"),
        )
        _funnel_row(s, "first_action")
        _funnel_row(s, "payment_success", minutes=1)
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_EXPANSION_READY)

    @override_settings(
        ALLOWED_HOSTS=[
            "*",
            "testserver",
            "127.0.0.1",
            "localhost",
            "manager.runmycampus.com",
        ]
    )
    def test_dashboard_200_platform_operator(self):
        u = User.objects.create_user(
            username="plc_super",
            password="x" * 8,
            is_superuser=True,
        )
        c = Client()
        c.force_login(u)
        url = reverse("platform_runtime:tenant_lifecycle_dashboard")
        r = c.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-tenant-lifecycle-dashboard", body)

    def test_dashboard_403_unauthorized_tenant_user(self):
        school = self.school_a
        u = User.objects.create_user(
            username="plc_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        req = RequestFactory().get("/platform-runtime/lifecycle/")
        req.user = u
        req.school = school
        resp = tenant_lifecycle_dashboard(req)
        self.assertEqual(resp.status_code, 403)


class TenantLifecycleSignupStateTests(TestCase):
    databases = {"default"}

    def test_signup_started_state_without_completed(self):
        s = School.objects.create(
            name="Su only",
            slug="life-su",
            subdomain="life-su",
            is_active=True,
            last_activity=timezone.now(),
        )
        _funnel_row(s, "signup_started")
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_SIGNUP_STARTED)
