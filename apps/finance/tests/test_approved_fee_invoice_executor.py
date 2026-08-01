"""The fee-invoice approval queue must actually EXECUTE once approved.

When a tenant enables auto-generate AND require-approval, the scheduled generator
parks a PENDING ``AutomationApprovalQueue`` row. Before this fix there was no
executor: an operator could approve the row but the invoices never generated —
the row sat at APPROVED forever. These tests cover the three moving parts:

  1. ``force_execute`` on ``_auto_generate_fee_invoices_body`` bypasses ONLY the
     schedule/approval gates (so an approved row generates), and the scheduled
     path still parks an ENRICHED row (school + schema_name + a real preview).
  2. ``execute_approved_fee_invoice_generations`` selects APPROVED
     fee_invoice_generation rows, runs the body with force_execute=True in the
     row's tenant context, and marks the row EXECUTED (must-FIRE, effect-probing);
     other statuses / types are ignored; a failure leaves the row APPROVED.
  3. The executor is registered in the broker-less periodic registry.

Money-safety note: the executor is idempotent because ``create_fee_invoices``
get_or_creates each invoice by (academic_year, student) reference, so re-execution
never double-invoices — asserted at the services layer elsewhere; here we mock
``create_fee_invoices`` to keep these tests off the tuition-pricing gauntlet.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.automation.models import AutomationApprovalQueue
from apps.finance.tasks import execute_approved_fee_invoice_generations


class _FeeFixtureMixin:
    def setUp(self):
        super().setUp()
        from apps.academics.models import AcademicYear, Classroom, Department, Specialty
        from apps.finance.models import ComplianceProfile
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from decimal import Decimal

        self.school = School.objects.create(
            name="Approve School", slug="approve-school", subdomain="approve-school"
        )
        self.profile = ComplianceProfile.objects.create(
            name="CM Profile",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
            timezone="Africa/Douala",
            chart_template=ComplianceProfile.ChartTemplate.OHADA,
            min_wage=Decimal("60000"),
            default_hours_per_week=Decimal("40"),
            overtime_multiplier=Decimal("1.5"),
            annual_leave_days=21,
            maternity_leave_days=84,
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026", start_date="2025-09-01", end_date="2026-06-30", is_active=True
        )
        self.dept = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=self.dept, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year, department=self.dept, name="Form 1", code="F1"
        )
        self.student = StudentProfile.objects.create(
            first_name="Jane",
            last_name="Doe",
            student_code="STU-APPROVE-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        from apps.finance.models import FeePlan

        self.plan = FeePlan.objects.create(
            school=self.school,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            name="Tuition",
            is_active=True,
        )

    def _finance_cfg(self, *, require_approval: bool):
        return {
            "auto_generate_invoices_enabled": True,
            "auto_generate_schedule": {"mode": "academic_year_start"},
            "auto_generate_due_date_offset_days": 7,
            "auto_generate_require_approval": require_approval,
        }


class ForceExecuteGateTests(_FeeFixtureMixin, TestCase):
    def _run_body(self, *, require_approval, force_execute, create_ret=None):
        from apps.finance import tasks as finance_tasks

        with mock.patch.object(
            finance_tasks, "get_cached_site_settings",
            return_value=SimpleNamespace(compliance_profile=self.profile),
        ), mock.patch.object(
            finance_tasks, "_get_finance_runtime_config",
            return_value=self._finance_cfg(require_approval=require_approval),
        ), mock.patch.object(
            finance_tasks, "pulse_workflow_step", return_value=None
        ), mock.patch(
            "apps.finance.scheduled_invoicing.is_invoice_generation_due_for_school",
            return_value=True,
        ), mock.patch.object(
            finance_tasks, "create_fee_invoices",
            return_value=list(create_ret or []),
        ) as m_create:
            result = finance_tasks._auto_generate_fee_invoices_body(
                dry_run=False, school_id=self.school.id, force_execute=force_execute
            )
        return result, m_create

    def test_scheduled_path_parks_enriched_row_and_does_not_generate(self):
        result, m_create = self._run_body(require_approval=True, force_execute=False)
        self.assertEqual(result["status"], "pending_approval")
        m_create.assert_not_called()  # parked, not generated
        row = AutomationApprovalQueue.objects.get(automation_type="fee_invoice_generation")
        self.assertEqual(row.status, AutomationApprovalQueue.Status.PENDING)
        # Enriched: the executor needs these to re-enter the tenant context...
        self.assertEqual(row.school_id, self.school.id)
        # ...and the approver needs a REAL preview, not the empty one it used to park.
        self.assertEqual(row.execution_summary["total_students"], 1)
        self.assertEqual(row.execution_summary["plans"][0]["would_create_invoices"], 1)

    def test_force_execute_generates_and_does_not_queue(self):
        result, m_create = self._run_body(
            require_approval=True, force_execute=True, create_ret=[object(), object()]
        )
        # force_execute overrode the approval gate → generated instead of parking.
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["invoices_created"], 2)
        m_create.assert_called_once()
        self.assertEqual(
            AutomationApprovalQueue.objects.count(), 0, "must NOT park a new row"
        )

    def test_force_execute_overrides_not_due_gate(self):
        # should_generate False + force_execute True must still generate (operator override).
        from apps.finance import tasks as finance_tasks

        with mock.patch.object(
            finance_tasks, "get_cached_site_settings",
            return_value=SimpleNamespace(compliance_profile=self.profile),
        ), mock.patch.object(
            finance_tasks, "_get_finance_runtime_config",
            return_value=self._finance_cfg(require_approval=True),
        ), mock.patch.object(
            finance_tasks, "pulse_workflow_step", return_value=None
        ), mock.patch(
            "apps.finance.scheduled_invoicing.is_invoice_generation_due_for_school",
            return_value=False,  # NOT due
        ), mock.patch.object(
            finance_tasks, "create_fee_invoices", return_value=[object()]
        ) as m_create:
            result = finance_tasks._auto_generate_fee_invoices_body(
                dry_run=False, school_id=self.school.id, force_execute=True
            )
        self.assertEqual(result["status"], "success")
        m_create.assert_called_once()


class ExecutorTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Exec School", slug="exec-school", subdomain="exec-school"
        )

    def _row(self, *, status, automation_type="fee_invoice_generation"):
        return AutomationApprovalQueue.objects.create(
            automation_type=automation_type,
            school=self.school,
            schema_name="exec-school",
            status=status,
            execution_summary={"billing_period": "ay-2025-09-01"},
        )

    def test_executes_approved_row_with_force_and_marks_executed(self):
        row = self._row(status=AutomationApprovalQueue.Status.APPROVED)
        with mock.patch(
            "apps.finance.tasks._run_with_tenant_context",
            side_effect=lambda runnable=None, **kw: runnable(),
        ), mock.patch(
            "apps.finance.tasks._auto_generate_fee_invoices_body",
            return_value={"status": "success", "invoices_created": 3},
        ) as m_body:
            result = execute_approved_fee_invoice_generations()

        self.assertEqual(result["executed"], 1)
        self.assertEqual(result["failed"], 0)
        m_body.assert_called_once()
        _, kwargs = m_body.call_args
        self.assertTrue(kwargs.get("force_execute"), "must run with force_execute=True")
        self.assertEqual(kwargs.get("school_id"), self.school.id)
        row.refresh_from_db()
        self.assertEqual(row.status, AutomationApprovalQueue.Status.EXECUTED)
        self.assertEqual(
            row.execution_summary["execution_result"]["invoices_created"], 3
        )

    def test_ignores_pending_rejected_and_other_types(self):
        self._row(status=AutomationApprovalQueue.Status.PENDING)
        self._row(status=AutomationApprovalQueue.Status.REJECTED)
        self._row(
            status=AutomationApprovalQueue.Status.APPROVED,
            automation_type="some_other_automation",
        )
        with mock.patch(
            "apps.finance.tasks._run_with_tenant_context",
            side_effect=lambda runnable=None, **kw: runnable(),
        ), mock.patch(
            "apps.finance.tasks._auto_generate_fee_invoices_body",
        ) as m_body:
            result = execute_approved_fee_invoice_generations()
        self.assertEqual(result["executed"], 0)
        m_body.assert_not_called()

    def test_failure_leaves_row_approved_for_retry(self):
        row = self._row(status=AutomationApprovalQueue.Status.APPROVED)
        with mock.patch(
            "apps.finance.tasks._run_with_tenant_context",
            side_effect=ValueError("simulated generation failure"),
        ):
            result = execute_approved_fee_invoice_generations()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["executed"], 0)
        row.refresh_from_db()
        self.assertEqual(row.status, AutomationApprovalQueue.Status.APPROVED)


class ExecutorRegistryTests(TestCase):
    _JOB = "finance.execute_approved_fee_invoice_generations"

    def setUp(self):
        from apps.platform_runtime import periodic

        self.periodic = periodic
        self._saved_registry = dict(periodic._REGISTRY)
        self._saved_installed = periodic._DEFAULTS_INSTALLED
        periodic._REGISTRY.clear()
        periodic._DEFAULTS_INSTALLED = False
        cache.clear()
        periodic.ensure_default_jobs()

    def tearDown(self):
        self.periodic._REGISTRY.clear()
        self.periodic._REGISTRY.update(self._saved_registry)
        self.periodic._DEFAULTS_INSTALLED = self._saved_installed
        cache.clear()

    def test_registered_cron_only_frequent(self):
        job = self.periodic._REGISTRY.get(self._JOB)
        self.assertIsNotNone(job)
        self.assertFalse(job.auto_eligible)  # financial → off the /health/ thread
        self.assertEqual(job.interval_seconds, self.periodic.FREQUENT_DRAIN_SECONDS)
        self.assertIn("executor", job.tags)

    def test_run_job_invokes_executor(self):
        with mock.patch(
            "apps.finance.tasks.execute_approved_fee_invoice_generations",
            return_value={"executed": 0, "failed": 0},
        ) as m_exec:
            result = self.periodic.run_job(self._JOB, force=True)
        self.assertEqual(result["status"], "ran", result)
        self.assertEqual(m_exec.call_count, 1)
