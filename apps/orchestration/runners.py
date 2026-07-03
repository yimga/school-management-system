"""
Phase 10 — 4.1: Orchestration runners. Create/update OrchestrationRun; retries, compensation, SLA.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import DatabaseError, IntegrityError, OperationalError, ProgrammingError
from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

from .models import OrchestrationRun, ProcessDefinition

# Typed exceptions for orchestration execute/compensate and run_step query paths.
_ORCHESTRATION_RUN_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValueError,
    TypeError,
    AttributeError,
    ImportError,
    RuntimeError,
)
_ORCHESTRATION_STEP_QUERY_ERRORS = (
    ImportError,
    DatabaseError,
    OperationalError,
    ProgrammingError,
    AttributeError,
    TypeError,
)


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
        """Run one step; update run state; return True if completed (or compensated).

        Move 2 instrumentation: bind the run to the current ProcessDefinitionVersion
        on first execution and emit OrchestrationStepEvent rows around each step.
        """

        # Move 2: import lazily so legacy callers / migrations don't import a model
        # before the app is ready.
        try:
            from apps.orchestration import event_log, versioning
            from apps.orchestration.models import OrchestrationStepEvent

            event_emit = event_log.emit
            event_types = OrchestrationStepEvent.EventType
            versioning.bind_run_to_current_version(self.run)
        except Exception:
            event_emit = None
            event_types = None

        if self.run.status not in (
            OrchestrationRun.Status.PENDING,
            OrchestrationRun.Status.RUNNING,
        ):
            return True
        step_started_at = timezone.now()
        try:
            self.run.status = OrchestrationRun.Status.RUNNING
            first_start = False
            if not self.run.started_at:
                self.run.started_at = step_started_at
                first_start = True
            self.run.save(update_fields=["status", "started_at", "updated_at"])
            if event_emit and event_types:
                if first_start:
                    event_emit(self.run, event_type=event_types.RUN_STARTED)
                event_emit(
                    self.run,
                    event_type=event_types.STEP_STARTED,
                    step_name=type(self).__name__,
                )
            out = self.run_step()
            self.run.output_payload = {**(self.run.output_payload or {}), **out}
            self.run.status = OrchestrationRun.Status.COMPLETED
            self.run.completed_at = timezone.now()
            self.run.save(
                update_fields=["output_payload", "status", "completed_at", "updated_at"]
            )
            if event_emit and event_types:
                step_ms = int((self.run.completed_at - step_started_at).total_seconds() * 1000)
                event_emit(
                    self.run,
                    event_type=event_types.STEP_SUCCEEDED,
                    step_name=type(self).__name__,
                    payload={k: v for k, v in (out or {}).items() if isinstance(v, (str, int, float, bool, list, dict))},
                    duration_ms=step_ms,
                )
                event_emit(self.run, event_type=event_types.RUN_COMPLETED)
            return True
        except _ORCHESTRATION_RUN_ERRORS as e:
            school_id = getattr(self.run, "school_id", None)
            log_exception_with_context(
                "Orchestration run step failed",
                school_id=school_id,
                extra={
                    "run_id": getattr(self.run, "pk", None),
                    "retry_count": (self.run.retry_count or 0) + 1,
                    "definition_code": getattr(
                        getattr(self.run, "definition", None), "code", None
                    ),
                },
            )
            self.run.retry_count = (self.run.retry_count or 0) + 1
            self.run.error_message = str(e)[:2000]
            step_ms = int((timezone.now() - step_started_at).total_seconds() * 1000)
            if event_emit and event_types:
                event_emit(
                    self.run,
                    event_type=event_types.STEP_FAILED,
                    step_name=type(self).__name__,
                    error_message=str(e)[:2000],
                    duration_ms=step_ms,
                )
            if self.run.retry_count >= self.max_retries:
                self.run.status = OrchestrationRun.Status.FAILED
                self.run.completed_at = timezone.now()
                self.run.save(
                    update_fields=[
                        "retry_count",
                        "error_message",
                        "status",
                        "completed_at",
                        "updated_at",
                    ]
                )
                if event_emit and event_types:
                    event_emit(self.run, event_type=event_types.RUN_FAILED, error_message=str(e)[:2000])
                try:
                    if event_emit and event_types:
                        event_emit(self.run, event_type=event_types.COMPENSATION_STARTED)
                    self.compensate()
                    if event_emit and event_types:
                        event_emit(self.run, event_type=event_types.COMPENSATION_COMPLETED)
                except _ORCHESTRATION_RUN_ERRORS:
                    log_exception_with_context(
                        "Orchestration compensate failed",
                        school_id=school_id,
                        extra={
                            "run_id": getattr(self.run, "pk", None),
                            "definition_code": getattr(
                                getattr(self.run, "definition", None), "code", None
                            ),
                        },
                    )
                return False
            self.run.save(
                update_fields=["retry_count", "error_message", "status", "updated_at"]
            )
            if event_emit and event_types:
                event_emit(
                    self.run,
                    event_type=event_types.RETRY_SCHEDULED,
                    step_name=type(self).__name__,
                    payload={"attempt": self.run.retry_count},
                )
        return False

    def compensate(self) -> None:
        """Optional compensation (rollback) when run failed or cancelled."""
        pass


class FeeFollowUpRunner(BaseOrchestrationRunner):
    """Runner for fee_follow_up: enqueue reminder work per school; records run in OrchestrationRun."""

    code = "fee_follow_up"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(
            getattr(self.run.school_id, "", "")
        )
        count = 0
        try:
            from apps.finance.models import PaymentReminder

            if self.run.school_id:
                count = PaymentReminder.objects.filter(
                    invoice__school_id=self.run.school_id,
                    is_active=True,
                    next_send_at__lte=timezone.now(),
                ).count()
        except _ORCHESTRATION_STEP_QUERY_ERRORS:
            log_exception_with_context(
                "FeeFollowUpRunner run_step query failed",
                school_id=school_id,
                extra={"step": "fee_follow_up"},
            )
        return {"school_id": school_id, "reminders_due": count, "step": "fee_follow_up"}


class AdmissionsRunner(BaseOrchestrationRunner):
    """Runner for admissions: batch application processing / offer letters (4.1)."""

    code = "admissions"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(
            getattr(self.run.school_id, "", "")
        )
        count = 0
        try:
            from apps.people.models import Applicant

            if self.run.school_id:
                # "Pending" = submitted but not yet decided (excludes raw LEAD
                # and the terminal ACCEPTED/REJECTED/ENROLLED stages).
                count = Applicant.objects.filter(
                    school_id=self.run.school_id,
                    stage__in=[Applicant.Stage.APPLIED, Applicant.Stage.UNDER_REVIEW],
                ).count()
        except _ORCHESTRATION_STEP_QUERY_ERRORS:
            log_exception_with_context(
                "AdmissionsRunner run_step query failed",
                school_id=school_id,
                extra={"step": "admissions"},
            )
        return {
            "school_id": school_id,
            "pending_applications": count,
            "step": "admissions",
        }


class ReEnrollmentRunner(BaseOrchestrationRunner):
    """Runner for re_enrollment: next-year re-enrollment invitations / confirmations (4.1)."""

    code = "re_enrollment"

    def run_step(self) -> dict:
        school_id = getattr(self.run.school_id, "hex", None) or str(
            getattr(self.run.school_id, "", "")
        )
        count = 0
        try:
            from apps.people.models import StudentProfile

            if self.run.school_id:
                count = StudentProfile.objects.filter(
                    school_id=self.run.school_id, is_active=True
                ).count()
        except _ORCHESTRATION_STEP_QUERY_ERRORS:
            log_exception_with_context(
                "ReEnrollmentRunner run_step query failed",
                school_id=school_id,
                extra={"step": "re_enrollment"},
            )
        return {
            "school_id": school_id,
            "eligible_students": count,
            "step": "re_enrollment",
        }


class ApprovalChainRunner(BaseOrchestrationRunner):
    """Runner for approval_chain: multi-step approval workflows (e.g. fee waiver, leave) (4.1)."""

    code = "approval_chain"

    def run_step(self) -> dict:
        payload = self.run.input_payload or {}
        chain_id = payload.get("chain_id") or ""
        return {"chain_id": chain_id, "step": "approval_chain"}


class StudentTransferRunner(BaseOrchestrationRunner):
    """Runner for student_transfer: executes one APPROVED TransferCase end-to-end.

    The case model owns the fine-grained FSM (export → seal → apply → link →
    reconcile, with its own compensation); this runner contributes the
    orchestration rails — append-only step events, retry, SLA — around one
    ``run_transfer_case`` execution. ``input_payload`` carries ``case_id``.
    """

    code = "student_transfer"

    def run_step(self) -> dict:
        payload = self.run.input_payload or {}
        case_id = payload.get("case_id") or ""
        from django.core.exceptions import ValidationError

        from apps.people.models_transfer import TransferCase

        try:
            case = TransferCase.objects.filter(pk=case_id).first()  # tenant-isolation-allow: operator-plane-case-by-pk-from-run-payload
        except (ValidationError, ValueError):
            # A malformed UUID in the payload is a missing case, not a 500.
            case = None
        if case is None:
            return {
                "error": "case_not_found",
                "case_id": str(case_id),
                "step": "student_transfer",
            }
        from apps.people.transfer_service import run_transfer_case

        summary = run_transfer_case(case, actor=self.run.triggered_by)
        summary["step"] = "student_transfer"
        return summary


def start_run(
    definition_code: str,
    school=None,
    triggered_by=None,
    input_payload: Optional[dict] = None,
) -> Optional[OrchestrationRun]:
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
        sla_deadline=timezone.now() + timedelta(hours=24)
        if definition_code == "fee_follow_up"
        else None,
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
    if code == "student_transfer":
        return StudentTransferRunner(run=run)
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
        return {
            "impact_count": 0,
            "steps": [],
            "dry_run": True,
            "error": "unknown_definition",
        }
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
    except _ORCHESTRATION_RUN_ERRORS as e:
        school_id = getattr(school, "pk", None) if school is not None else None
        log_exception_with_context(
            "run_workflow_simulation run_step failed",
            school_id=school_id,
            extra={"definition_code": definition_code, "dry_run": True},
        )
        return {"impact_count": 0, "steps": [{"error": str(e)[:200]}], "dry_run": True}
    steps = [step_out]
    impact = 0
    for key in ("reminders_due", "pending_applications", "eligible_students"):
        impact += step_out.get(key) or 0
    if impact == 0 and step_out:
        impact = 1
    return {"impact_count": impact, "steps": steps, "dry_run": True}
