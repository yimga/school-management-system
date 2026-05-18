"""v3.32.0 — Low-balance notification signal + Celery task tests.

Three layers:

  * Pure structural (:class:`SimpleTestCase`) — module imports + signal
    handler attachment + task callable + email template renderability.
  * DB-level :class:`TestCase` — signal transition matrix, task email
    delivery + cooldown + sweep + tenant isolation, NoSecretsLogged
    invariant.

The DB-layer tests degrade gracefully when the project test DB is
infra-blocked (`OperationalError: no such index ...`); the structural
tests always run.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings


# ---------------------------------------------------------------------------
# Layer 1 — pure structural (no DB)
# ---------------------------------------------------------------------------


class StructuralLowBalanceWiringTests(SimpleTestCase):
    """Signal handlers attached + task exists + template renderable."""

    def test_signal_handlers_register_on_meal_plan_balance(self) -> None:
        from django.db.models.signals import post_save, pre_save

        from apps.schoolops import signals  # noqa: F401  side-effect
        from apps.schoolops.models import MealPlanBalance

        pre_recv = [r for r in pre_save._live_receivers(
            sender=MealPlanBalance)]
        post_recv = [r for r in post_save._live_receivers(
            sender=MealPlanBalance)]
        # At minimum: our two handlers should be attached.
        self.assertGreaterEqual(len(pre_recv), 1)
        self.assertGreaterEqual(len(post_recv), 1)

    def test_notify_task_callable(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        self.assertTrue(callable(notify_low_meal_plan_balance))

    def test_sweep_task_callable(self) -> None:
        from apps.schoolops.tasks import sweep_low_meal_plan_balances
        self.assertTrue(callable(sweep_low_meal_plan_balances))

    def test_email_templates_render(self) -> None:
        from django.template.loader import render_to_string
        ctx = {
            "student_first_name": "Sam",
            "student_last_name": "Doe",
            "balance_display": "1.50 USD",
            "threshold_display": "5.00 USD",
            "plan_label": "Standard plan",
        }
        txt = render_to_string("schoolops/email/low_meal_balance.txt", ctx)
        html = render_to_string("schoolops/email/low_meal_balance.html", ctx)
        self.assertIn("Sam", txt)
        self.assertIn("Sam", html)
        self.assertIn("1.50 USD", txt)


# ---------------------------------------------------------------------------
# Layer 2 — DB-backed tests
# ---------------------------------------------------------------------------


def _build_school():
    from apps.schools.models import School
    slug = f"low-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        features={"cafeteria": True},
    )


def _build_student(school, *, first_name="Sam", last_name="Doe"):
    from apps.people.models import StudentProfile
    return StudentProfile.objects.create(
        school=school,
        first_name=first_name,
        last_name=last_name,
        student_code=f"STU-{uuid.uuid4().hex[:8]}",
    )


def _build_guardian(student, *, email="guardian@test.example"):
    from django.contrib.auth import get_user_model
    from apps.people.models import StudentGuardian
    User = get_user_model()
    user = User.objects.create_user(
        username=f"g-{uuid.uuid4().hex[:8]}",
        email=email, password="x", role=User.Role.PARENT,
    )
    return StudentGuardian.objects.create(
        guardian_user=user, student=student,
        email=email, receives_email=True,
    )


def _build_meal_plan_balance(
    school, student, *,
    balance="10.00", threshold="5.00", currency="USD",
):
    from apps.schoolops.models import MealPlanBalance
    return MealPlanBalance.objects.create(
        school=school, student=student,
        balance=Decimal(balance),
        low_balance_threshold=Decimal(threshold),
        currency=currency,
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LowBalanceSignalTransitionTests(TestCase):
    """Signal fires only on False -> True is_low transition."""

    def setUp(self) -> None:
        self.school = _build_school()
        self.student = _build_student(self.school)
        _build_guardian(self.student)

    def test_signal_fires_on_false_to_true(self) -> None:
        row = _build_meal_plan_balance(
            self.school, self.student, balance="20.00",
        )
        mail.outbox = []
        row.balance = Decimal("1.00")  # below 5.00 threshold
        row.save()
        # Eager Celery — outbox should now have one mail.
        self.assertEqual(len(mail.outbox), 1)

    def test_signal_does_not_fire_on_true_to_true(self) -> None:
        row = _build_meal_plan_balance(
            self.school, self.student, balance="2.00",
        )
        # row was created already low — first save fires once.
        mail.outbox = []
        row.balance = Decimal("1.00")  # still low; no transition
        row.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_signal_does_not_fire_on_false_to_false(self) -> None:
        row = _build_meal_plan_balance(
            self.school, self.student, balance="20.00",
        )
        mail.outbox = []
        row.balance = Decimal("15.00")
        row.save()
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LowBalanceTaskTests(TestCase):
    """Direct invocation of :func:`notify_low_meal_plan_balance`."""

    def setUp(self) -> None:
        self.school = _build_school()
        self.student = _build_student(self.school)

    def test_task_sends_email_when_guardian_present(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        _build_guardian(self.student, email="parent@example.test")
        row = _build_meal_plan_balance(
            self.school, self.student, balance="1.00",
        )
        mail.outbox = []
        result = notify_low_meal_plan_balance(meal_plan_balance_id=row.pk)
        self.assertTrue(result["delivered_email"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("parent@example.test", mail.outbox[0].to)

    def test_task_no_ops_when_no_guardian(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        row = _build_meal_plan_balance(
            self.school, self.student, balance="1.00",
        )
        mail.outbox = []
        result = notify_low_meal_plan_balance(meal_plan_balance_id=row.pk)
        self.assertFalse(result["delivered_email"])
        self.assertTrue(result["skipped_no_guardian_email"])

    def test_task_enforces_seven_day_cooldown(self) -> None:
        from django.utils import timezone
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        _build_guardian(self.student)
        row = _build_meal_plan_balance(
            self.school, self.student, balance="1.00",
        )
        row.last_low_balance_notification_sent_at = timezone.now()
        row.save(update_fields=["last_low_balance_notification_sent_at"])
        mail.outbox = []
        result = notify_low_meal_plan_balance(meal_plan_balance_id=row.pk)
        self.assertTrue(result["skipped_cooldown"])
        self.assertEqual(len(mail.outbox), 0)

    def test_task_increments_notification_count(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        _build_guardian(self.student)
        row = _build_meal_plan_balance(
            self.school, self.student, balance="1.00",
        )
        notify_low_meal_plan_balance(meal_plan_balance_id=row.pk)
        row.refresh_from_db()
        self.assertEqual(row.low_balance_notification_count, 1)
        self.assertIsNotNone(row.last_low_balance_notification_sent_at)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LowBalanceSweepTests(TestCase):
    """Sweep task picks up rows the signal missed."""

    def test_sweep_enqueues_low_rows(self) -> None:
        from apps.schoolops.tasks import sweep_low_meal_plan_balances
        school = _build_school()
        student = _build_student(school)
        _build_guardian(student)
        # Create a row already low — signal will fire ONCE on create,
        # but to model the "missed" case, clear the timestamp + outbox.
        row = _build_meal_plan_balance(school, student, balance="1.00")
        row.last_low_balance_notification_sent_at = None
        row.save(update_fields=["last_low_balance_notification_sent_at"])
        mail.outbox = []
        summary = sweep_low_meal_plan_balances()
        self.assertGreaterEqual(summary["enqueued"], 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TenantIsolationTests(TestCase):
    """Tenant A's low row never notifies tenant B's guardians."""

    def test_tenant_isolation_in_email_delivery(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        school_a = _build_school()
        school_b = _build_school()
        student_a = _build_student(school_a)
        student_b = _build_student(school_b)
        _build_guardian(student_a, email="a-guardian@example.test")
        _build_guardian(student_b, email="b-guardian@example.test")
        row_a = _build_meal_plan_balance(
            school_a, student_a, balance="1.00",
        )
        mail.outbox = []
        notify_low_meal_plan_balance(meal_plan_balance_id=row_a.pk)
        self.assertEqual(len(mail.outbox), 1)
        recipients = mail.outbox[0].to
        self.assertIn("a-guardian@example.test", recipients)
        self.assertNotIn("b-guardian@example.test", recipients)


class NoSecretsLoggedTests(TestCase):
    """Task logs row PK + student/plan IDs only; never email/balance."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_logger_never_emits_email_address(self) -> None:
        from apps.schoolops.tasks import notify_low_meal_plan_balance
        school = _build_school()
        student = _build_student(school)
        _build_guardian(student, email="secret-parent@example.test")
        row = _build_meal_plan_balance(school, student, balance="1.00")
        with self.assertLogs(
            "apps.schoolops.tasks", level=logging.INFO,
        ) as cm:
            notify_low_meal_plan_balance(meal_plan_balance_id=row.pk)
        joined = "\n".join(cm.output).lower()
        self.assertNotIn("secret-parent@example.test", joined)
        # Balance numeric should never appear in logs either.
        self.assertNotIn("1.00 usd", joined)
