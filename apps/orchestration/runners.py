"""
Phase 10 — 4.1: Orchestration runners. Create/update OrchestrationRun; retries, compensation, SLA.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.utils import timezone

from .models import OrchestrationRun, ProcessDefinition


class BaseOrchestrationRunner:
    """Base for long-running process runners. Subclass and implement run_step()."""
    code: str = ""

    def __init__(self, run: OrchestrationRun, max_retries: int = 3):
        self.run = run
        self.max_retries = max_retries

    def run_step(self) -> dict:
        """Execute one step. Return output_payload fragment; raise on failure."""
        raise NotImplementedError

    def execute(self) -> bool:
        """Run one step; update run state; return True if completed (or compensated)."""
        if self.run.status not in (OrchestrationRun.Status.PENDING, OrchestrationRun.Status.RUNNING):
            return True
        try:
            self.run.status = OrchestrationRun.Status.RUNNING
            if not self.run.started_at:
                self.run.started_at = timezone.now()
            self.run.save(update_fields=["status", "started_at", "updated_at"])
            out = self.run_step()
            self.run.output_payload = {**(self.run.output_payload or {}), **out}
            self.run.status = OrchestrationRun.Status.COMPLETED
            self.run.completed_at = timezone.now()
            self.run.save(update_fields=["output_payload", "status", "completed_at", "updated_at"])
            return True
        except Exception as e:
            self.run.retry_count = (self.run.retry_count or 0) + 1
            self.run.error_message = str(e)[:2000]
            if self.run.retry_count >= self.max_retries:
                self.run.status = OrchestrationRun.Status.FAILED
                self.run.completed_at = timezone.now()
                self.run.save(
                    update_fields=["retry_count", "error_message", "status", "completed_at", "updated_at"]
                )
                try:
                    self.compensate()
                except Exception:
                    pass
                return False
            self.run.save(
                update_fields=["retry_count", "error_message", "status", "updated_at"]
            )
        return False

    def compensate(self) -> None:
        """Optional compensation (rollback) when run failed or cancelled."""
        pass


class FeeFollowUpRunner(BaseOrchestrationRunner):
    """Runner for fee_follow_up: enqueue reminder work per school; records run in OrchestrationRun."""
    code = "fee_follow_up"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(getattr(self.run.school_id, "", ""))
        count = 0
        try:
            from apps.finance.models import InvoiceReminder

            if self.run.school_id:
                count = InvoiceReminder.objects.filter(
                    invoice__school_id=self.run.school_id,
                    is_active=True,
                    next_send_at__lte=timezone.now(),
                ).count()
        except Exception:
            pass
        return {"school_id": school_id, "reminders_due": count, "step": "fee_follow_up"}


class AdmissionsRunner(BaseOrchestrationRunner):
    """Runner for admissions: batch application processing / offer letters (4.1)."""
    code = "admissions"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(getattr(self.run.school_id, "", ""))
        count = 0
        try:
            from apps.requests.models import AdmissionApplication
            if self.run.school_id:
                count = AdmissionApplication.objects.filter(
                    school_id=self.run.school_id,
                    status="PENDING",
                ).count()
        except Exception:
            pass
        return {"school_id": school_id, "pending_applications": count, "step": "admissions"}


class ReEnrollmentRunner(BaseOrchestrationRunner):
    """Runner for re_enrollment: next-year re-enrollment invitations / confirmations (4.1)."""
    code = "re_enrollment"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(getattr(self.run.school_id, "", ""))
        count = 0
        try:
            from apps.accounts.models import StudentProfile
            if self.run.school_id:
                count = StudentProfile.objects.filter(school_id=self.run.school_id, is_active=True).count()
        except Exception:
            pass
        return {"school_id": school_id, "eligible_students": count, "step": "re_enrollment"}


class ApprovalChainRunner(BaseOrchestrationRunner):
    """Runner for approval_chain: multi-step approval workflows (e.g. fee waiver, leave) (4.1)."""
    code = "approval_chain"

    def run_step(self) -> dict:
        payload = self.run.input_payload or {}
        chain_id = payload.get("chain_id") or ""
        return {"chain_id": chain_id, "step": "approval_chain"}


def start_run(definition_code: str, school=None, triggered_by=None, input_payload: Optional[dict] = None) -> Optional[OrchestrationRun]:
    """Create a PENDING OrchestrationRun for the given definition. Returns the run or None."""
    try:
        definition = ProcessDefinition.objects.get(code=definition_code)
    except ProcessDefinition.DoesNotExist:
        return None
    run = OrchestrationRun.objects.create(
        definition=definition,
        school=school,
        triggered_by=triggered_by,
        input_payload=input_payload or {},
        status=OrchestrationRun.Status.PENDING,
        sla_deadline=timezone.now() + timedelta(hours=24) if definition_code == "fee_follow_up" else None,
    )
    return run


def get_runner(run: OrchestrationRun) -> Optional[BaseOrchestrationRunner]:
    """Return runner instance for this run's definition code."""
    code = getattr(run.definition, "code", "") if run.definition_id else ""
    if code == "fee_follow_up":
        return FeeFollowUpRunner(run=run)
    if code == "admissions":
        return AdmissionsRunner(run=run)
    if code == "re_enrollment":
        return ReEnrollmentRunner(run=run)
    if code == "approval_chain":
        return ApprovalChainRunner(run=run)
    return None


def run_workflow_simulation(definition_code: str, payload: dict, school=None) -> dict:
    """
    Phase 10 — 10.7: Workflow simulation with impact counts (no side effects).
    Returns {"impact_count": N, "steps": [...], "dry_run": True} for marketplace/UI.
    Runs the runner's run_step() in memory (no DB write) to compute impact.
    """
    try:
        definition = ProcessDefinition.objects.get(code=definition_code)
    except ProcessDefinition.DoesNotExist:
        return {"impact_count": 0, "steps": [], "dry_run": True, "error": "unknown_definition"}
    from .models import OrchestrationRun
    run = OrchestrationRun(
        definition=definition,
        school=school,
        input_payload=payload or {},
        status=OrchestrationRun.Status.PENDING,
    )
    runner = get_runner(run)
    if runner is None:
        return {"impact_count": 0, "steps": [], "dry_run": True}
    try:
        step_out = runner.run_step()
    except Exception as e:
        return {"impact_count": 0, "steps": [{"error": str(e)[:200]}], "dry_run": True}
    steps = [step_out]
    impact = 0
    for key in ("reminders_due", "pending_applications", "eligible_students"):
        impact += step_out.get(key) or 0
    if impact == 0 and step_out:
        impact = 1
    return {"impact_count": impact, "steps": steps, "dry_run": True}
