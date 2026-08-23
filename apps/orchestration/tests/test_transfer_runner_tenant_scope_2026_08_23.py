"""StudentTransferRunner must not execute another tenant's TransferCase.

``run.input_payload["case_id"]`` is attacker-controlled on any path that lets a
caller create a run (``api.py`` stamps the run with the CALLER's school and
copies the posted payload verbatim). Before this fix the runner looked the case
up by pk alone, so naming another school's case uuid handed that case to
``run_transfer_case`` — an operation that moves student records and remaps FKs.

Both tests use ``dry_run`` so the assertion is about the LOOKUP, never about a
real transfer executing. The positive test is the vacuity guard: it proves the
same call shape does reach and find a case when the run's tenant owns it, so the
negative test's ``case_not_found`` is the scope check firing and not a lookup
that was broken for some unrelated reason.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.orchestration.models import OrchestrationRun, ProcessDefinition
from apps.orchestration.runners import StudentTransferRunner
from apps.people.models_transfer import TransferCase
from apps.schools.models import School


class StudentTransferRunnerTenantScopeTests(TestCase):
    databases = {"default"}

    def _school(self, tag: str) -> School:
        uid = uuid.uuid4().hex[:8]
        return School.objects.create(
            name=f"{tag} {uid}",
            slug=f"{tag}-{uid}",
            subdomain=f"{tag}{uid}",
            is_active=True,
        )

    def setUp(self):
        self.definition = ProcessDefinition.objects.create(
            code=f"student_transfer_{uuid.uuid4().hex[:6]}",
            name="Student transfer",
        )
        self.victim_source = self._school("vsrc")
        self.victim_target = self._school("vtgt")
        self.attacker = self._school("atk")
        self.case = TransferCase.objects.create(
            source_school=self.victim_source,
            target_school=self.victim_target,
            source_profile_pk="1",
            status=TransferCase.Status.APPROVED,
        )

    def _runner(self, school):
        run = OrchestrationRun.objects.create(
            definition=self.definition,
            school=school,
            input_payload={"case_id": str(self.case.pk)},
        )
        runner = StudentTransferRunner(run=run)
        runner.dry_run = True
        return runner

    def test_run_scoped_to_another_school_cannot_reach_the_case(self):
        out = self._runner(self.attacker).run_step()
        self.assertEqual(out.get("error"), "case_not_found")
        self.assertNotIn("would_run", out)

    def test_run_scoped_to_the_case_source_school_finds_it(self):
        # Vacuity guard: same payload, same runner, tenant that owns the case.
        out = self._runner(self.victim_source).run_step()
        self.assertTrue(out.get("would_run"))
        self.assertEqual(out.get("case_id"), str(self.case.pk))

    def test_run_scoped_to_the_case_target_school_finds_it(self):
        out = self._runner(self.victim_target).run_step()
        self.assertTrue(out.get("would_run"))

    def test_run_with_no_school_does_not_search_platform_wide(self):
        out = self._runner(None).run_step()
        self.assertEqual(out.get("error"), "case_not_found")
