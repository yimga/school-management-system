"""A provisioning step that FAILED must not report SUCCESS to the owner.

Found by an A-Z lifecycle audit (2026-07-16). Two seed sub-steps recorded their
"READY" event OUTSIDE their own try/except, so the event fired unconditionally:

    except (...):
        phase_b_failed_steps.append("terms")     # step FAILED
    _record_school_event(..., status="SUCCESS",  # ...and we say SUCCESS anyway
                         payload={"term_count": term_count})  # the INTENDED count

That matters beyond cosmetics: the owner's progress strip keys its per-step tick
off exactly these event types (``provisioning_progress.EXTENDED_PROVISION_STEP_SPECS``)
and event-presence outranks the parent run state. So the owner watched
"Creating your academic year ✓" / "Setting up subjects ✓" on a tenant that has
neither — a green tick on a step that failed.

A third case was worse. ``ensure_local_grading_scale`` contractually NEVER raises
(it logs and returns ``{"ok": False, "error": ...}``), so its caller's
``except -> phase_b_failed_steps.append("grading_scale")`` was DEAD CODE reachable
only via ImportError. A real grading-scale failure therefore recorded SUCCESS,
never blocked ``phase_b_complete=True``, and the tenant became "settled" — so no
watchdog or reconcile would ever re-seed it. A school with no grading scale
cannot publish a grade.

These tests pin the contract: the event reports the OUTCOME, the payload reports
GROUND TRUTH (what is in the database, not what was attempted), and a failure is
tracked so Phase B stays resumable.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.schools.models import School, SchoolProvisioningEvent


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class GradingScaleFailureIsTrackedTests(TestCase):
    """The dead-guard case: a not-ok return must fail the step, not pass it."""

    def setUp(self):
        self.school = School.objects.create(
            name="Truthful Seed Academy",
            slug="truthful-seed",
            subdomain="truthful-seed",
            is_active=False,
        )

    def _event(self, kind):
        return (
            SchoolProvisioningEvent.objects.filter(school=self.school, event_type=kind)
            .order_by("-id")
            .first()
        )

    @patch("apps.evals.grading_provisioning.ensure_local_grading_scale")
    def test_not_ok_grading_scale_records_failed_and_blocks_phase_b(self, mock_scale):
        # The real function swallows everything and returns ok=False -- reproduce
        # that contract exactly (NOT an exception, which is what the old guard
        # wrongly assumed).
        mock_scale.return_value = {"ok": False, "error": "no scale for country"}
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="owner@truthful.test")

        ev = self._event("GRADING_SCALE_READY")
        self.assertIsNotNone(ev, "the grading-scale step must record an event")
        self.assertEqual(
            (ev.status or "").upper(),
            "FAILED",
            "a not-ok grading scale must report FAILED, not SUCCESS",
        )

        self.school.refresh_from_db()
        prov = (self.school.settings or {}).get("provisioning") or {}
        self.assertIn(
            "grading_scale",
            prov.get("phase_b_failed_steps") or [],
            "a not-ok grading scale must be tracked so Phase B stays resumable",
        )
        self.assertNotEqual(
            prov.get("phase_b_complete"),
            True,
            "Phase B must NOT complete while the grading scale failed -- otherwise "
            "the school reads as settled and no healer ever re-seeds it",
        )

    @patch("apps.evals.grading_provisioning.ensure_local_grading_scale")
    def test_ok_grading_scale_still_reports_success(self, mock_scale):
        # The guard must not turn a healthy provision red.
        mock_scale.return_value = {"ok": True, "scale_type": "letter"}
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="owner@truthful.test")

        ev = self._event("GRADING_SCALE_READY")
        self.assertIsNotNone(ev)
        self.assertEqual((ev.status or "").upper(), "SUCCESS")
        self.school.refresh_from_db()
        prov = (self.school.settings or {}).get("provisioning") or {}
        self.assertNotIn("grading_scale", prov.get("phase_b_failed_steps") or [])


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class FailedSeedStepReportsFailedTests(TestCase):
    """The core regression: a FAILED step must not emit a SUCCESS event.

    This is the test that actually pins the "green tick on a failed step" bug --
    the happy-path tests below cannot see it.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Failing Seed Academy",
            slug="failing-seed",
            subdomain="failing-seed",
            is_active=False,
        )

    def _event(self, kind):
        return (
            SchoolProvisioningEvent.objects.filter(school=self.school, event_type=kind)
            .order_by("-id")
            .first()
        )

    def test_failed_term_seeding_reports_FAILED_not_success(self):
        from django.db import DatabaseError

        from apps.schools.tasks import provision_school_sync

        with patch(
            "apps.academics.models.Term.objects.get_or_create",
            side_effect=DatabaseError("simulated term seed failure"),
        ):
            provision_school_sync(str(self.school.id), contact_email="owner@fail.test")

        ev = self._event("ACADEMIC_YEAR_READY")
        self.assertIsNotNone(ev, "the step must still record an event")
        self.assertEqual(
            (ev.status or "").upper(),
            "FAILED",
            "term seeding failed -- the owner's progress strip must NOT show a "
            "green tick for it",
        )
        self.assertTrue((ev.payload or {}).get("failed"))
        self.assertEqual(
            int((ev.payload or {}).get("term_count") or 0),
            0,
            "payload must report the REAL term count (0), not the intended count",
        )

        self.school.refresh_from_db()
        prov = (self.school.settings or {}).get("provisioning") or {}
        self.assertIn("terms", prov.get("phase_b_failed_steps") or [])

    def test_failed_subject_seeding_reports_FAILED_not_success(self):
        from django.db import DatabaseError

        from apps.schools.tasks import provision_school_sync

        with patch(
            "apps.academics.models.Subject.objects.get_or_create",
            side_effect=DatabaseError("simulated subject seed failure"),
        ):
            provision_school_sync(str(self.school.id), contact_email="owner@fail.test")

        ev = self._event("SUBJECTS_READY")
        self.assertIsNotNone(ev)
        self.assertEqual(
            (ev.status or "").upper(),
            "FAILED",
            "subject seeding failed -- the event must say so",
        )
        self.assertTrue((ev.payload or {}).get("failed"))


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class SeedEventPayloadIsGroundTruthTests(TestCase):
    """A healthy provision's payload must describe the DB, not the intent."""

    def setUp(self):
        self.school = School.objects.create(
            name="Ground Truth Academy",
            slug="ground-truth",
            subdomain="ground-truth",
            is_active=False,
        )

    def test_academic_year_event_reports_real_term_count(self):
        from apps.academics.models import Term
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="owner@ground.test")

        ev = (
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="ACADEMIC_YEAR_READY"
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(ev)
        self.assertEqual((ev.status or "").upper(), "SUCCESS")
        real = Term.objects.filter(school=self.school).count()
        self.assertEqual(
            int((ev.payload or {}).get("term_count") or 0),
            real,
            "term_count must be what the tenant actually has, not what was intended",
        )

    def test_subjects_event_reports_real_total(self):
        from apps.academics.models import Subject
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="owner@ground.test")

        ev = (
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="SUBJECTS_READY"
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(ev)
        self.assertEqual((ev.status or "").upper(), "SUCCESS")
        self.assertEqual(
            int((ev.payload or {}).get("subjects_total") or 0),
            Subject.objects.filter(school=self.school).count(),
        )
