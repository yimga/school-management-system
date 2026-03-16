"""
Celery tasks for accounts (e.g. delegation auto-revoke).
Runs in tenant context where applicable.
"""
from __future__ import annotations

import logging
from django.utils import timezone
from celery import shared_task
from apps.platform_runtime.helpers import get_effective_site_settings
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.celery_tasks import _run_with_tenant_context, get_active_school_ids

logger = logging.getLogger(__name__)


def _school_for_user(user):
    if not user:
        return None
    teacher_profile = getattr(user, "teacher_profile", None)
    if teacher_profile and getattr(teacher_profile, "school", None):
        return teacher_profile.school
    guardian_links = getattr(user, "guardian_links", None)
    if guardian_links is not None:
        link = guardian_links.select_related("student__school").first()
        if link and getattr(link.student, "school", None):
            return link.student.school
    return None


def _expire_past_delegations_body() -> dict:
    """Inner body: run inside tenant context."""
    from apps.accounts.models import Delegation

    now = timezone.now()
    qs = Delegation.objects.filter(is_active=True).select_related("delegator")
    to_expire = []
    for d in qs:
        site = get_effective_site_settings(school=_school_for_user(d.delegator))
        if not getattr(site, "delegation_auto_revoke", True):
            continue
        end = d.extended_end_date or d.end_date
        if end and end < now:
            to_expire.append((d.pk, site))

    if to_expire:
        for pk, site in to_expire:
            try:
                from apps.people.badge_services import revoke_acting_badges_for_delegation
                d = Delegation.objects.get(pk=pk)
                revoke_acting_badges_for_delegation(d)
                if getattr(site, "delegation_summary_report_on_return", True):
                    try:
                        from apps.accounts.models import DelegationActionLog
                        count = DelegationActionLog.objects.filter(delegation=d).count()
                        if count > 0 and d.delegator.email:
                            from django.core.mail import send_mail
                            from django.conf import settings as django_settings
                            send_mail(
                                subject="While you were away: %d action(s) on your behalf" % count,
                                message="Your delegation has ended. %d action(s) were taken on your behalf. Review them in the portal: Delegation catch-up." % count,
                                from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@school.local"),
                                recipient_list=[d.delegator.email],
                                fail_silently=True,
                            )
                    except (OSError, ConnectionError, AttributeError, TypeError) as e:
                        _school = _school_for_user(d.delegator)
                        log_exception_with_context(
                            "expire_past_delegations: summary email failed",
                            school_id=str(_school.id) if _school else None,
                            extra={"task": "expire_past_delegations", "delegation_id": pk, "error": str(e)},
                        )
                        logger.warning("expire_past_delegations: summary email for %s: %s", pk, e)
            except (ImportError, AttributeError, TypeError, ValueError) as e:
                _school = _school_for_user(d.delegator)
                log_exception_with_context(
                    "expire_past_delegations: revoke badge failed",
                    school_id=str(_school.id) if _school else None,
                    extra={"task": "expire_past_delegations", "delegation_id": pk, "error": str(e)},
                )
                logger.warning("expire_past_delegations: revoke badge for delegation %s: %s", pk, e)
        Delegation.objects.filter(pk__in=[pk for pk, _site in to_expire]).update(is_active=False)
        logger.info("expire_past_delegations: deactivated %d delegation(s)", len(to_expire))

    return {"expired": len(to_expire)}


@shared_task(name="accounts.expire_past_delegations")
def expire_past_delegations(school_id: str | None = None):
    """Set is_active=False on past delegations. Runs in tenant context (per school_id or all active schools)."""
    if school_id:
        return _run_with_tenant_context(school_id=school_id, runnable=_expire_past_delegations_body)
    totals = {"expired": 0}
    for sid in get_active_school_ids():
        result = _run_with_tenant_context(school_id=sid, runnable=_expire_past_delegations_body)
        totals["expired"] += result.get("expired", 0)
    return totals


def _prepare_rollover_proposal_impl(school_id, source_year_id, target_year_id, created_by_id=None):
    """Inner implementation: run inside tenant context."""
    import logging
    from apps.accounts.models import RolloverProposal, RolloverProposalItem
    from apps.schools.models import School
    from apps.academics.models import AcademicYear, Classroom
    from apps.people.models import StudentProfile
    from apps.reports.services import get_promotion_status, _annual_average_for_student

    logger = logging.getLogger(__name__)
    try:
        school = School.objects.get(pk=school_id)
        source_year = AcademicYear.objects.get(pk=source_year_id)
        target_year = AcademicYear.objects.get(pk=target_year_id)
    except (School.DoesNotExist, AcademicYear.DoesNotExist) as e:
        logger.warning("prepare_rollover_proposal: %s", e)
        return {"ok": False, "error": str(e)}

    if getattr(source_year, "is_locked", False):
        return {"ok": False, "error": "Source year is locked"}

    target_classrooms = list(Classroom.objects.filter(academic_year=target_year).order_by("name"))
    promotion_map = {}
    try:
        from apps.academics.models import ClassroomPromotionMapping
        for m in ClassroomPromotionMapping.objects.filter(
            source_year=source_year, target_year=target_year
        ).select_related("source_classroom", "target_classroom"):
            if m.source_classroom_id:
                promotion_map[m.source_classroom_id] = m.target_classroom
    except (ImportError, AttributeError, TypeError):
        pass

    from django.db.models import Count
    from apps.people.models import StudentResourceReturn
    outstanding = dict(
        StudentResourceReturn.objects.filter(academic_year=source_year, returned_at__isnull=True)
        .values("student_id")
        .annotate(count=Count("id"))
        .values_list("student_id", "count")
    )

    from apps.academics.models import Term
    terms = list(Term.objects.filter(academic_year=source_year).order_by("position", "start_date"))
    students = list(
        StudentProfile.objects.filter(academic_year=source_year, is_active=True).select_related("classroom")
    )

    proposal = RolloverProposal.objects.create(
        school=school,
        source_year=source_year,
        target_year=target_year,
        status=RolloverProposal.Status.PENDING,
        created_by_id=created_by_id,
    )
    created = 0
    for s in students:
        annual_avg = _annual_average_for_student(s, terms) if terms else None
        promo = get_promotion_status(s, source_year, annual_avg) if annual_avg is not None else "NO_DATA"
        suggested = None
        if s.classroom_id and promotion_map:
            suggested = promotion_map.get(s.classroom_id)
        if not suggested and s.classroom:
            suggested = Classroom.objects.filter(academic_year=target_year, name=s.classroom.name).first()
        if not suggested and target_classrooms:
            suggested = target_classrooms[0]
        RolloverProposalItem.objects.create(
            proposal=proposal,
            student=s,
            current_classroom_id=s.classroom_id,
            suggested_next_classroom=suggested,
            promotion_status=promo,
            annual_average=round(annual_avg, 2) if annual_avg is not None else None,
            outstanding_returns=outstanding.get(s.id, 0),
        )
        created += 1
    logger.info("prepare_rollover_proposal: created proposal %s with %d items", proposal.pk, created)
    return {"ok": True, "proposal_id": proposal.pk, "items": created}


@shared_task(name="accounts.prepare_rollover_proposal")
def prepare_rollover_proposal(school_id, source_year_id, target_year_id, created_by_id=None):
    """Build rollover proposal. Runs in tenant context for school_id."""
    return _run_with_tenant_context(
        school_id=str(school_id),
        runnable=lambda: _prepare_rollover_proposal_impl(school_id, source_year_id, target_year_id, created_by_id),
    )


def _apply_rollover_proposal_impl(proposal_id, lock_source=False, notify_parents=False, allow_outstanding_returns=False, carry_forward_arrears=False):
    """Inner implementation: run inside tenant context."""
    import logging
    from django.utils import timezone
    from apps.accounts.models import RolloverProposal
    from apps.people.models import StudentProfile

    logger = logging.getLogger(__name__)
    try:
        proposal = RolloverProposal.objects.get(pk=proposal_id)
    except RolloverProposal.DoesNotExist:
        return {"ok": False, "error": "Proposal not found"}
    if proposal.status != RolloverProposal.Status.APPROVED:
        return {"ok": False, "error": f"Proposal status is {proposal.status}, must be APPROVED"}

    source_year = proposal.source_year
    target_year = proposal.target_year
    site = get_effective_site_settings(school=getattr(proposal, "school", None))
    if callable(getattr(site, "get_backend_feature_flags", None)):
        flags = site.get_backend_feature_flags()
    else:
        flags = getattr(site, "backend_feature_flags", None) or {}
    block_outstanding = flags.get("block_promotion_if_outstanding_returns", False)

    updated = 0
    graduated = 0
    skipped = 0
    for item in proposal.items.select_related("student", "suggested_next_classroom", "approved_next_classroom").all():
        student = item.student
        if block_outstanding and not allow_outstanding_returns and (item.outstanding_returns or 0) > 0:
            skipped += 1
            continue
        if getattr(item, "is_graduate", False):
            student.academic_year = target_year
            student.classroom = None
            student.status = StudentProfile.Status.ALUMNI
            student.is_active = False
            student.save(update_fields=["academic_year", "classroom", "status", "is_active"])
            graduated += 1
            continue
        next_class = item.approved_next_classroom or item.suggested_next_classroom
        if next_class is None:
            skipped += 1
            continue
        student.academic_year = target_year
        student.classroom = next_class
        student.save(update_fields=["academic_year", "classroom"])
        updated += 1

    proposal.status = RolloverProposal.Status.APPLIED
    proposal.applied_at = timezone.now()
    proposal.save(update_fields=["status", "applied_at"])

    if lock_source:
        source_year.is_locked = True
        source_year.save(update_fields=["is_locked"])

    if carry_forward_arrears and flags.get("carry_forward_arrears_on_rollover", True):
        try:
            from apps.finance.services import carry_forward_arrears
            carry_forward_arrears(source_year, target_year)
        except (ValueError, TypeError, ImportError, AttributeError) as e:
            _school_id = str(proposal.school_id) if getattr(proposal, "school_id", None) else None
            log_exception_with_context(
                "apply_rollover_proposal: carry_forward_arrears failed",
                school_id=_school_id,
                extra={"task": "apply_rollover_proposal", "proposal_id": proposal_id, "error": str(e)},
            )
            logger.warning("apply_rollover_proposal: carry_forward_arrears: %s", e)

    logger.info("apply_rollover_proposal: proposal %s applied; updated=%d graduated=%d skipped=%d", proposal_id, updated, graduated, skipped)
    return {"ok": True, "updated": updated, "graduated": graduated, "skipped": skipped}


@shared_task(name="accounts.apply_rollover_proposal")
def apply_rollover_proposal(proposal_id, lock_source=False, notify_parents=False, allow_outstanding_returns=False, carry_forward_arrears=False, school_id: str | None = None):
    """Apply APPROVED rollover proposal. Runs in tenant context when school_id is provided."""
    def _run():
        return _apply_rollover_proposal_impl(proposal_id, lock_source, notify_parents, allow_outstanding_returns, carry_forward_arrears)
    if school_id:
        return _run_with_tenant_context(school_id=str(school_id), runnable=_run)
    return _apply_rollover_proposal_impl(proposal_id, lock_source, notify_parents, allow_outstanding_returns, carry_forward_arrears)
