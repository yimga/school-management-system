"""End-to-end: real provisioning pipeline + onboarding 'done' page.

Runs the actual provisioning to completion (sync fallback, shared-DB), asserts
every seed artifact, verifies re-provision idempotency, and renders the
onboarding 'done' page that previously 500'd (undefined `pending_school_name`
filter-arg in tenant_minimal_shell.html). The django-tenants Postgres schema
build is skipped locally (USE_DJANGO_TENANTS False) — that part is staging-only.

Validated via a direct django.setup() run (12/12) because the custom sqlite test
runner is flaky on Windows; this TestCase form runs in CI.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Subject,
    Term,
)
from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.tasks import dispatch_provision_school

User = get_user_model()


class SchoolProvisionOnboardingE2ETests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="E2E Test High School",
            slug="e2e-test-high",
            subdomain="e2e-test-high",
            is_active=False,
        )
        self.owner = User.objects.create_user(
            username="e2e-owner@example.com",
            email="e2e-owner@example.com",
            password="x",
        )
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, is_primary=True
        )

    def _provision(self):
        """Run the real pipeline via the sync fallback (broker offline)."""
        with mock.patch(
            "apps.schools.tasks.provision_school_task.delay",
            side_effect=RuntimeError("broker offline"),
        ):
            return dispatch_provision_school(
                str(self.school.id), contact_email="e2e-owner@example.com"
            )

    def test_full_provision_seeds_everything_and_done_page_renders(self):
        result = self._provision()
        self.school.refresh_from_db()

        # Pipeline completed.
        self.assertTrue(self.school.is_active, "school should be active")
        self.assertTrue(result.get("fallback"), "dispatch should fall back to sync")

        # Every seed artifact the seed_data step is responsible for.
        self.assertTrue(AcademicYear.objects.filter(school=self.school).exists())
        term_count = Term.objects.filter(school=self.school).count()
        self.assertGreaterEqual(term_count, 1, "terms must be seeded")
        subject_count = Subject.objects.filter(school=self.school).count()
        self.assertGreaterEqual(subject_count, 1, "subjects must be seeded")
        self.assertGreaterEqual(
            Classroom.objects.filter(school=self.school).count(), 1
        )
        self.assertGreaterEqual(
            Department.objects.filter(school=self.school).count(), 1
        )
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="COMPLETED"
            ).exists()
        )
        self.assertFalse(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="FAILED"
            ).exists(),
            "a clean provision must record no FAILED event",
        )

        # Idempotency: a second run must not duplicate seed rows.
        self._provision()
        self.assertEqual(
            Term.objects.filter(school=self.school).count(),
            term_count,
            "re-provision must not duplicate terms",
        )
        self.assertEqual(
            Subject.objects.filter(school=self.school).count(),
            subject_count,
            "re-provision must not duplicate subjects",
        )

        # The onboarding 'done' page that previously 500'd must render 200.
        from apps.accounts.views_owner_onboarding import owner_onboarding_done

        req = RequestFactory().get(
            "/authentication/onboarding/done/",
            HTTP_HOST="e2e-test-high.runmycampus.com",
        )
        req.user = self.owner
        req.urlconf = "config.tenant_urls"
        req.session = SessionStore()
        req.school = self.school
        req.public_host_kind = "tenant"
        req.tenant = type("T", (), {"schema_name": "public"})()
        resp = owner_onboarding_done(req)
        self.assertEqual(resp.status_code, 200, "onboarding/done must not 500")

    def test_resume_phase_b_on_active_school_with_incomplete_seed(self):
        """A school left LIVE but with Phase B incomplete must RESUME, not no-op.

        Regression for the production half-provisioned tenant: Phase A activated
        the school (is_active=True) but seed_data failed, so the owner had a live
        portal with no academic year / terms / subjects / classrooms and no way to
        finish. The flight-deck Retry card calls dispatch_provision_school, which
        used to hit the blanket ``if school.is_active: return`` guard and bail —
        leaving the tenant broken forever. The guard now falls through to resume
        whenever ``phase_b_complete`` is not set.
        """
        # Simulate the broken state: active (Phase A done) but Phase B never
        # completed and no seed artifacts created.
        self.school.is_active = True
        self.school.settings = {"provisioning": {"phase_a_complete": True}}
        self.school.save(update_fields=["is_active", "settings", "updated_at"])
        self.assertFalse(AcademicYear.objects.filter(school=self.school).exists())

        # Retry provisioning (the same entry point the flight-deck Retry card uses).
        self._provision()
        self.school.refresh_from_db()

        # Phase B must have RESUMED and completed: seed artifacts now exist and the
        # phase_b_complete flag is set.
        self.assertTrue(
            AcademicYear.objects.filter(school=self.school).exists(),
            "resume must seed the academic year that the failed run never created",
        )
        self.assertGreaterEqual(
            Term.objects.filter(school=self.school).count(), 1
        )
        self.assertGreaterEqual(
            Subject.objects.filter(school=self.school).count(), 1
        )
        prov = (self.school.settings or {}).get("provisioning") or {}
        self.assertTrue(
            prov.get("phase_b_complete"),
            "resume must mark phase_b_complete so a later retry no-ops",
        )

        # And a SUBSEQUENT retry must now no-op (phase_b_complete short-circuit),
        # never duplicating seed rows.
        term_count = Term.objects.filter(school=self.school).count()
        self._provision()
        self.assertEqual(
            Term.objects.filter(school=self.school).count(),
            term_count,
            "a fully-provisioned school must not re-seed on retry",
        )

    def test_operator_can_requeue_half_provisioned_active_school(self):
        """Tenant-360 / flight-deck requeue must be ALLOWED on a live-but-Phase-B-
        incomplete school, and REFUSED on a fully-provisioned one."""
        from apps.schools.operator_school_lens import (
            can_operator_requeue_provisioning,
        )
        from apps.schools.provisioning_progress import provisioning_needs_resume

        # Fully provisioned (Phase A + B) → no requeue needed.
        self.school.is_active = True
        self.school.settings = {
            "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
        }
        self.school.save(update_fields=["is_active", "settings", "updated_at"])
        self.assertFalse(provisioning_needs_resume(self.school))
        self.assertFalse(can_operator_requeue_provisioning(self.school))

        # Active but Phase B incomplete (the broken-tenant case) → requeue allowed.
        self.school.settings = {"provisioning": {"phase_a_complete": True}}
        self.school.save(update_fields=["settings", "updated_at"])
        self.assertTrue(provisioning_needs_resume(self.school))
        self.assertTrue(can_operator_requeue_provisioning(self.school))

    def test_reconciler_selects_only_half_provisioned_active_tenants(self):
        """The durable seal must requeue half-provisioned tenants and ONLY those.

        Critically, a legacy school (active, no provisioning flags at all — the
        state of every tenant provisioned before phase tracking existed) must NOT
        be flagged, or the reconciler would re-provision the entire fleet.
        """
        from django.utils import timezone

        from apps.schools.tasks import reconcile_half_provisioned_tenants
        from apps.schools.provisioning_progress import provisioning_needs_resume

        # This school: active, Phase A done, Phase B NOT done → eligible.
        self.school.is_active = True
        self.school.settings = {"provisioning": {"phase_a_complete": True}}
        self.school.save(update_fields=["is_active", "settings", "updated_at"])
        self.assertTrue(provisioning_needs_resume(self.school))

        # Legacy school: active, NO provisioning flags → must be immune.
        legacy = School.objects.create(
            name="Legacy High", slug="legacy-high",
            subdomain="legacy-high", is_active=True,
        )
        self.assertFalse(provisioning_needs_resume(legacy))

        # Fully provisioned school: both flags → must be skipped.
        done = School.objects.create(
            name="Done High", slug="done-high", subdomain="done-high",
            is_active=True,
            settings={"provisioning": {"phase_a_complete": True, "phase_b_complete": True}},
        )
        self.assertFalse(provisioning_needs_resume(done))

        # Dry run isolates SELECTION from the actual re-drive.
        result = reconcile_half_provisioned_tenants(dry_run=True)
        self.assertEqual(
            result["requeued"], 1, "exactly the one half-provisioned tenant"
        )

        # Cooldown: stamp last_reconcile_at = now → the candidate is skipped.
        self.school.refresh_from_db()
        blob = dict(self.school.settings or {})
        prov = dict(blob.get("provisioning") or {})
        prov["last_reconcile_at"] = timezone.now().isoformat()
        blob["provisioning"] = prov
        self.school.settings = blob
        self.school.save(update_fields=["settings", "updated_at"])
        result2 = reconcile_half_provisioned_tenants(dry_run=True, cooldown_minutes=30)
        self.assertEqual(result2["requeued"], 0)
        self.assertEqual(result2["skipped_cooldown"], 1)

    def test_done_page_renders_even_when_provisioning_incomplete(self):
        """The 500 was independent of provisioning state — guard that path too."""
        from apps.accounts.views_owner_onboarding import owner_onboarding_done

        # School left INACTIVE (provisioning never ran). Stub the in-request kick
        # so the test stays fast and deterministic.
        with mock.patch(
            "apps.accounts.views_owner_onboarding._kick_provisioning_on_done_page",
            return_value=None,
        ):
            req = RequestFactory().get(
                "/authentication/onboarding/done/",
                HTTP_HOST="e2e-test-high.runmycampus.com",
            )
            req.user = self.owner
            req.urlconf = "config.tenant_urls"
            req.session = SessionStore()
            req.school = self.school
            req.public_host_kind = "tenant"
            req.tenant = type("T", (), {"schema_name": "public"})()
            resp = owner_onboarding_done(req)
        self.assertEqual(resp.status_code, 200)
