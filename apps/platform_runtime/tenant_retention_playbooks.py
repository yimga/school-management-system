"""
Named tenant retention playbooks (triggers, conditions, operator actions).

Schedulers call :func:`evaluate_playbooks_for_school` and persist deduplicated rows via
:class:`~apps.platform_runtime.models.TenantRetentionPlaybookAction` plus audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from django.conf import settings
from django.utils import timezone

from apps.platform_runtime.customer_health import calculate_school_health
from apps.platform_runtime.models import (
    TenantLifecycleSchedulerRun,
    TenantRetentionPlaybookAction,
    TenantRetentionPlaybookAuditLog,
)
from apps.platform_runtime.tenant_lifecycle_state_machine import (
    STATE_ACTIVATED,
    STATE_AT_RISK,
    STATE_CHURNED,
    STATE_EXPANSION_READY,
    STATE_ONBOARDING,
    STATE_PAYING,
    STATE_RECOVERED,
    resolve_tenant_lifecycle_state,
)
from apps.schools.models import MarketingFunnelEvent

PLAYBOOK_ONBOARDING_STALLED = "onboarding_stalled"
PLAYBOOK_FIRST_ACTION_NOT_COMPLETED = "first_action_not_completed"
PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP = "payment_failed_follow_up"
PLAYBOOK_LOW_USAGE_RESCUE = "low_usage_rescue"
PLAYBOOK_AT_RISK_ESCALATION = "at_risk_escalation"
PLAYBOOK_EXPANSION_READY_OUTREACH = "expansion_ready_outreach"
PLAYBOOK_CHURNED_RECOVERY = "churned_recovery"


def _stall_onboarding_days() -> int:
    return int(getattr(settings, "TENANT_LIFECYCLE_ONBOARDING_STALL_DAYS", 7))


def _stall_first_action_days() -> int:
    return int(getattr(settings, "TENANT_LIFECYCLE_FIRST_ACTION_STALL_DAYS", 14))


def _first_event_ts(school_id: int | None, event_type: str):
    if not school_id:
        return None
    return (
        MarketingFunnelEvent.objects.filter(school_id=school_id, event_type=event_type)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )


def _has_event(school_id: int | None, event_type: str) -> bool:
    if not school_id:
        return False
    return MarketingFunnelEvent.objects.filter(
        school_id=school_id, event_type=event_type
    ).exists()


Matcher = Callable[..., Optional[str]]
"""
Return optional phase suffix for idempotency (e.g. winback vs followthrough).
None means playbook does not apply.
"""


def _match_onboarding_stalled(school, raw: dict[str, Any]) -> Optional[str]:
    if raw.get("state") != STATE_ONBOARDING:
        return None
    sid = school.pk
    o0 = _first_event_ts(sid, "onboarding_start")
    if not o0:
        return None
    if (timezone.now() - o0).days < _stall_onboarding_days():
        return None
    return "default"


def _match_first_action_not_completed(school, raw: dict[str, Any]) -> Optional[str]:
    sid = school.pk
    if _has_event(sid, "first_action"):
        return None
    su = _first_event_ts(sid, "signup_completed")
    if not su:
        return None
    if (timezone.now() - su).days < _stall_first_action_days():
        return None
    return "default"


def _match_payment_failed_follow_up(_school, raw: dict[str, Any]) -> Optional[str]:
    if raw.get("state") != STATE_AT_RISK:
        return None
    if "latest_payment_event_failed" not in (raw.get("reasons") or []):
        return None
    return "default"


def _match_low_usage_rescue(school, raw: dict[str, Any]) -> Optional[str]:
    if raw.get("state") not in (STATE_PAYING, STATE_ACTIVATED):
        return None
    health = calculate_school_health(school)
    score = int(health.get("score") or 0)
    students = int(health.get("student_count") or 0)
    if students < 2 or score >= 45:
        return None
    return "default"


def _match_at_risk_escalation(_school, raw: dict[str, Any]) -> Optional[str]:
    if raw.get("state") != STATE_AT_RISK:
        return None
    if "latest_payment_event_failed" in (raw.get("reasons") or []):
        return None
    return "default"


def _match_expansion_ready_outreach(_school, raw: dict[str, Any]) -> Optional[str]:
    if raw.get("state") != STATE_EXPANSION_READY:
        return None
    return "default"


def _match_churned_recovery(_school, raw: dict[str, Any]) -> Optional[str]:
    st = raw.get("state")
    if st == STATE_CHURNED:
        return "winback"
    if st == STATE_RECOVERED:
        reasons = raw.get("reasons") or []
        if "billing_recovered_after_prolonged_failure" in reasons:
            return "followthrough"
        if "tenant_recovered_event" in reasons:
            return "followthrough"
    return None


@dataclass(frozen=True)
class RetentionPlaybookSpec:
    code: str
    trigger: str
    condition_summary: str
    action_kind: str
    owner: str
    severity: str
    schedule: str
    matcher: Matcher


RETENTION_PLAYBOOKS: tuple[RetentionPlaybookSpec, ...] = (
    RetentionPlaybookSpec(
        code=PLAYBOOK_ONBOARDING_STALLED,
        trigger="lifecycle_state_onboarding_and_onboarding_start_stale",
        condition_summary=f"STATE_ONBOARDING and onboarding_start age >= {_stall_onboarding_days()}d",
        action_kind="operator_task",
        owner="platform_ops",
        severity="warning",
        schedule="daily",
        matcher=_match_onboarding_stalled,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_FIRST_ACTION_NOT_COMPLETED,
        trigger="signup_completed_without_first_action_stale",
        condition_summary=f"no first_action and signup_completed age >= {_stall_first_action_days()}d",
        action_kind="operator_task",
        owner="customer_success",
        severity="warning",
        schedule="daily",
        matcher=_match_first_action_not_completed,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_PAYMENT_FAILED_FOLLOW_UP,
        trigger="lifecycle_at_risk_latest_payment_failed",
        condition_summary="STATE_AT_RISK with latest_payment_event_failed",
        action_kind="billing_follow_up",
        owner="finance_ops",
        severity="critical",
        schedule="daily",
        matcher=_match_payment_failed_follow_up,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_LOW_USAGE_RESCUE,
        trigger="paying_or_activated_low_health_score",
        condition_summary="PAYING or ACTIVATED with health score <45 and students>=2",
        action_kind="operator_task",
        owner="customer_success",
        severity="warning",
        schedule="weekly",
        matcher=_match_low_usage_rescue,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_AT_RISK_ESCALATION,
        trigger="lifecycle_at_risk_non_payment_reason",
        condition_summary="STATE_AT_RISK without latest_payment_event_failed",
        action_kind="escalation_queue",
        owner="platform_ops",
        severity="critical",
        schedule="daily",
        matcher=_match_at_risk_escalation,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_EXPANSION_READY_OUTREACH,
        trigger="lifecycle_expansion_ready",
        condition_summary="STATE_EXPANSION_READY",
        action_kind="expansion_outreach",
        owner="growth",
        severity="info",
        schedule="weekly",
        matcher=_match_expansion_ready_outreach,
    ),
    RetentionPlaybookSpec(
        code=PLAYBOOK_CHURNED_RECOVERY,
        trigger="lifecycle_churned_or_recovered_followthrough",
        condition_summary="STATE_CHURNED winback or STATE_RECOVERED followthrough",
        action_kind="recovery_playbook",
        owner="customer_success",
        severity="critical",
        schedule="daily",
        matcher=_match_churned_recovery,
    ),
)


def _idempotency_key(
    playbook_code: str, school_id: int, *, phase: str, day_iso: str
) -> str:
    return f"{playbook_code}:{school_id}:{day_iso}:{phase}"


def _write_audit(
    school_id: int,
    spec: RetentionPlaybookSpec,
    *,
    outcome: str,
    detail: str,
    payload: dict[str, Any],
    scheduler_run: TenantLifecycleSchedulerRun | None,
) -> None:
    TenantRetentionPlaybookAuditLog.objects.create(
        school_id=school_id,
        playbook_code=spec.code,
        trigger=spec.trigger,
        outcome=outcome,
        detail=detail[:2000],
        payload=payload,
        scheduler_run=scheduler_run,
    )


def ensure_playbook_action(
    school,
    spec: RetentionPlaybookSpec,
    *,
    phase: str,
    scheduler_run: TenantLifecycleSchedulerRun | None,
    day_iso: str,
    extra_payload: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Create OPEN playbook action when idempotency allows. Writes audit (created | duplicate).

    Returns True when a new action row was created.
    """
    sid = school.pk
    key = _idempotency_key(spec.code, sid, phase=phase, day_iso=day_iso)
    payload = dict(extra_payload or {})
    payload.setdefault("phase", phase)
    _obj, created = TenantRetentionPlaybookAction.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "school": school,
            "playbook_code": spec.code,
            "trigger": spec.trigger,
            "condition_summary": spec.condition_summary,
            "action_kind": spec.action_kind,
            "owner": spec.owner,
            "severity": spec.severity,
            "schedule": spec.schedule,
            "payload": payload,
            "scheduler_run": scheduler_run,
        },
    )
    if not created:
        _write_audit(
            sid,
            spec,
            outcome="skipped_duplicate",
            detail=key,
            payload=payload,
            scheduler_run=scheduler_run,
        )
        return False

    _write_audit(
        sid,
        spec,
        outcome="action_created",
        detail=key,
        payload=payload,
        scheduler_run=scheduler_run,
    )
    return True


def evaluate_playbooks_for_school(
    school,
    *,
    scheduler_run: TenantLifecycleSchedulerRun | None = None,
    now=None,
) -> int:
    """
    Evaluate all retention playbooks for one school.

    Returns count of new OPEN actions created (0..len(RETENTION_PLAYBOOKS)).
    """
    now = now or timezone.now()
    day_iso = now.date().isoformat()
    raw = resolve_tenant_lifecycle_state(school)
    actions = 0

    for spec in RETENTION_PLAYBOOKS:
        phase = spec.matcher(school, raw)
        if phase is None:
            _write_audit(
                school.pk,
                spec,
                outcome="skipped_no_match",
                detail="",
                payload={"lifecycle_state": raw.get("state")},
                scheduler_run=scheduler_run,
            )
            continue

        created = ensure_playbook_action(
            school,
            spec,
            phase=phase,
            scheduler_run=scheduler_run,
            day_iso=day_iso,
            extra_payload={"lifecycle_state": raw.get("state")},
        )
        if created:
            actions += 1

    return actions
