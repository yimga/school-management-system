"""The weekly friction digest must actually leave the process.

``_dispatch`` used to call ``CommunicationTemplate.queue_render()`` — a method
that has never existed on that model. The resulting AttributeError was caught
and logged at INFO as a "fallback", so a tenant that HAD configured the digest
got exactly the same outcome as one that had not: nothing sent, and a log line
that reads benign.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.communication.models import CommunicationTemplate
from apps.observability.models_friction import FrictionEvent
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class FrictionDigestDispatchTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Friction Dispatch {uid}",
            slug=f"fdx-{uid}",
            subdomain=f"fdx-{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"fadm-{uid}",
            email=f"fadm-{uid}@example.test",
            password="pw",
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_primary=True
        )
        FrictionEvent.objects.create(
            school=self.school,
            user=self.admin,
            view_name="academics:gradebook",
            kind="validation_retry",
            utc_day=timezone.now().date(),
            count=9,
        )
        self.template = CommunicationTemplate.objects.create(
            school=self.school,
            key="friction_digest",
            subject_template="Weekly friction digest",
            body_template="{{ body }}",
            is_active=True,
        )

    def _run(self, send_email_side_effect=None):
        calls: list[tuple] = []

        def _recorder(to_addresses, subject, body, **kwargs):
            calls.append((list(to_addresses), subject, body, kwargs))
            if send_email_side_effect is not None:
                raise send_email_side_effect
            return True

        # Patched on the module that owns it — an import error here would mean
        # the dispatch path names a function the Communication app does not have,
        # which is the class of bug this test exists for.
        with mock.patch(
            "apps.communication.notification_service.send_email",
            side_effect=_recorder,
        ):
            call_command(
                "digest_friction",
                "--threshold", "1",
                "--hours", "24",
                "--school", self.school.slug,
                "--no-ai",
            )
        return calls

    def test_configured_tenant_actually_receives_the_digest(self):
        calls = self._run()
        # Guard against the vacuous pass: if the command had aggregated nothing
        # it would also make zero send calls, so first pin that the row is in
        # the window the command scans.
        self.assertEqual(FrictionEvent.objects.filter(school=self.school).count(), 1)
        self.assertEqual(
            len(calls), 1,
            "the friction digest was never dispatched to any send path",
        )
        recipients, subject, body, kwargs = calls[0]
        self.assertIn(self.admin.email, recipients)
        self.assertEqual(subject, "Weekly friction digest")
        self.assertIn("academics:gradebook", body)
        self.assertEqual(getattr(kwargs.get("school"), "pk", None), self.school.pk)

    def test_broken_dispatch_is_logged_as_an_error_not_a_benign_fallback(self):
        with self.assertLogs(
            "apps.observability.management.commands.digest_friction", level="ERROR"
        ) as captured:
            self._run(send_email_side_effect=RuntimeError("smtp down"))
        self.assertTrue(
            any("friction_digest" in line for line in captured.output),
            captured.output,
        )

    def test_tenant_without_recipients_is_not_an_error(self):
        SchoolMembership.objects.filter(school=self.school).delete()
        calls = self._run()
        self.assertEqual(calls, [])
