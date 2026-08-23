"""The analytics nightly commands must run inside each school's tenant context.

``apps.analytics`` and ``apps.people`` are TENANT_APPS only (config/settings.py),
so under ``USE_DJANGO_TENANTS`` their tables live exclusively inside tenant
schemas. These commands are driven from cron and from ``call_command`` inside a
Celery task -- neither has tenant middleware, so the connection sits on
``public`` where the relations do not exist. The write raises, the wrapper's
``except`` swallows it, and beat records a clean nightly run that wrote nothing.

Like ``apps/schoolops/tests/test_sweeps_run_in_tenant_context_2026_08_22.py``,
these tests do not need Postgres: under SQLite there is one schema, so a missing
wrapper never raises. What they assert is the STRUCTURE that makes the wrapper
real -- that every school is visited inside ``_run_with_tenant_context``.
"""

from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.analytics.models import RiskDigestRecipient, RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School


def _school(tag):
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}", slug=slug, subdomain=slug, is_active=True
    )


class NightlyBatchTenantContextTests(TestCase):
    def setUp(self):
        self.a = _school("nb-a")
        self.b = _school("nb-b")
        self.student_a = StudentProfile.objects.create(
            school=self.a,
            first_name="Nb",
            last_name="Student",
            student_code=f"sc-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad-{uuid.uuid4().hex[:12]}",
        )
        RiskFactor.objects.create(
            school=self.a,
            student=self.student_a,
            score=85.0,
            reason_summary="heuristic",
        )

    def _run_recording(self, *args, **kwargs):
        """Run a command with the tenant wrapper recorded, not replaced."""
        seen: list[str] = []

        def _record(*, school_id, runnable, **kw):
            seen.append(str(school_id))
            return runnable()

        out = StringIO()
        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_record
        ):
            call_command(*args, stdout=out, stderr=out, **kwargs)
        return seen, out.getvalue()

    def test_compute_nightly_risk_enters_context_for_every_school(self):
        # Guard against the vacuous pass: there must be more than one active
        # school for "every school" to mean anything.
        self.assertGreaterEqual(School.objects.filter(is_active=True).count(), 2)

        seen, _out = self._run_recording("compute_nightly_risk")

        self.assertIn(str(self.a.pk), seen)
        self.assertIn(str(self.b.pk), seen)

    def test_compute_nightly_grade_predictions_enters_context_for_every_school(self):
        seen, _out = self._run_recording("compute_nightly_grade_predictions")

        self.assertIn(str(self.a.pk), seen)
        self.assertIn(str(self.b.pk), seen)

    def test_ai_narrate_risk_digest_enters_context_for_its_school(self):
        seen, out = self._run_recording(
            "ai_narrate_risk_digest", "--school", self.a.slug, "--top-n", "1"
        )

        self.assertEqual(seen, [str(self.a.pk)])
        # The digest body proves the RiskFactor read happened INSIDE the context,
        # not before it.
        self.assertIn("Nb Student", out)

    def test_send_risk_digest_enters_context_once_per_school(self):
        RiskDigestRecipient.objects.create(
            school=self.a,
            channel=RiskDigestRecipient.Channel.EMAIL,
            target="ops@example.test",
            enabled=True,
        )
        seen, _out = self._run_recording("send_risk_digest", "--dry-run")

        self.assertIn(str(self.a.pk), seen)
        self.assertIn(str(self.b.pk), seen)
        # send_risk_digest drives ai_narrate_risk_digest in-process for a school
        # it has already entered; re-entering would let the inner exit reset the
        # session for the rest of the outer body.
        self.assertEqual(
            len(seen), len(set(seen)), f"tenant context entered twice: {seen}"
        )

    def test_one_unresolvable_tenant_does_not_end_the_batch(self):
        def _boom(*, school_id, runnable, **kw):
            if str(school_id) == str(self.a.pk):
                raise ValueError("Tenant client could not be resolved")
            return runnable()

        out = StringIO()
        with patch(
            "apps.schools.celery_tasks._run_with_tenant_context", side_effect=_boom
        ):
            call_command("compute_nightly_risk", stdout=out, stderr=out)

        self.assertIn("risk factor", out.getvalue().lower())

    def test_inference_run_failure_is_recorded_not_fatal(self):
        """A DB failure on the first school must not abort the whole batch."""
        from apps.analytics.models import AtRiskInferenceRun

        real_create = AtRiskInferenceRun.objects.create
        calls = {"n": 0}

        def _flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                from django.db import DatabaseError

                raise DatabaseError("relation does not exist")
            return real_create(*args, **kwargs)

        out = StringIO()
        with patch.object(AtRiskInferenceRun.objects, "create", side_effect=_flaky):
            call_command("compute_nightly_risk", stdout=out, stderr=out)

        self.assertIn(
            "risk factor",
            out.getvalue().lower(),
            "the batch aborted on the first school's DB failure",
        )
        self.assertGreaterEqual(calls["n"], 2, "the second school was never reached")
