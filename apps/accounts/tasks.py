"""
Celery tasks for accounts (e.g. delegation auto-revoke).
Runs in tenant context where applicable.
"""

from __future__ import annotations

import logging
from django.utils import timezone
from celery import shared_task
from apps.siteconfig.config_service import get_effective_site_settings
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
    qs = Delegation.objects.filter(is_active=True).select_related("delegator")  # tenant-isolation-allow: celery-delegation-lifecycle-cross-user-graph-reviewed
    to_expire = []
    for d in qs:
        # config-resolver-allow: namespace stored in to_expire and re-read after the loop
        site = get_effective_site_settings(school=_school_for_user(d.delegator))
        if not getattr(site, "delegation_auto_revoke", True):
            continue
        end = d.extended_end_date or d.end_date
        if end and end < now:
            to_expire.append((d.pk, site))

    if to_expire:
        for pk, site in to_expire:
            try:
                from apps.people.badge_services import (
                    revoke_acting_badges_for_delegation,
                )

                d = Delegation.objects.get(pk=pk)  # tenant-isolation-allow: celery-delegation-lifecycle-cross-user-graph-reviewed
                revoke_acting_badges_for_delegation(d)
                if getattr(site, "delegation_summary_report_on_return", True):
                    try:
                        from apps.accounts.models import DelegationActionLog

                        count = DelegationActionLog.objects.filter(delegation=d).count()  # tenant-isolation-allow: celery-delegation-lifecycle-cross-user-graph-reviewed
                        if count > 0 and d.delegator.email:
                            from apps.schoolops.email_compat import send_mail
                            from django.conf import settings as django_settings

                            send_mail(
                                subject="While you were away: %d action(s) on your behalf"
                                % count,
                                message="Your delegation has ended. %d action(s) were taken on your behalf. Review them in the portal: Delegation catch-up."
                                % count,
                                from_email=getattr(
                                    django_settings,
                                    "DEFAULT_FROM_EMAIL",
                                    "noreply@school.local",
                                ),
                                recipient_list=[d.delegator.email],
                                fail_silently=True,
                            )
                    except (OSError, ConnectionError, AttributeError, TypeError) as e:
                        _school = _school_for_user(d.delegator)
                        log_exception_with_context(
                            "expire_past_delegations: summary email failed",
                            school_id=str(_school.id) if _school else None,
                            extra={
                                "task": "expire_past_delegations",
                                "delegation_id": pk,
                                "error": str(e),
                            },
                        )
                        logger.warning(
                            "expire_past_delegations: summary email for %s: %s", pk, e
                        )
            except (ImportError, AttributeError, TypeError, ValueError) as e:
                _school = _school_for_user(d.delegator)
                log_exception_with_context(
                    "expire_past_delegations: revoke badge failed",
                    school_id=str(_school.id) if _school else None,
                    extra={
                        "task": "expire_past_delegations",
                        "delegation_id": pk,
                        "error": str(e),
                    },
                )
                logger.warning(
                    "expire_past_delegations: revoke badge for delegation %s: %s", pk, e
                )
        Delegation.objects.filter(pk__in=[pk for pk, _site in to_expire]).update(  # tenant-isolation-allow: celery-delegation-lifecycle-cross-user-graph-reviewed
            is_active=False
        )
        logger.info(
            "expire_past_delegations: deactivated %d delegation(s)", len(to_expire)
        )

    return {"expired": len(to_expire)}


@shared_task(name="accounts.expire_past_delegations")
def expire_past_delegations(school_id: str | None = None):
    """Set is_active=False on past delegations. Runs in tenant context (per school_id or all active schools)."""
    if school_id:
        return _run_with_tenant_context(
            school_id=school_id, runnable=_expire_past_delegations_body
        )
    totals = {"expired": 0}
    for sid in get_active_school_ids():
        result = _run_with_tenant_context(
            school_id=sid, runnable=_expire_past_delegations_body
        )
        totals["expired"] += result.get("expired", 0)
    return totals


def _prepare_rollover_proposal_impl(
    school_id, source_year_id, target_year_id, created_by_id=None
):
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
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        source_year = AcademicYear.objects.get(pk=source_year_id)
        target_year = AcademicYear.objects.get(pk=target_year_id)
    except (School.DoesNotExist, AcademicYear.DoesNotExist) as e:
        logger.warning("prepare_rollover_proposal: %s", e)
        return {"ok": False, "error": str(e)}

    if getattr(source_year, "is_locked", False):
        return {"ok": False, "error": "Source year is locked"}

    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    target_classrooms = list(
        Classroom.objects.filter(academic_year=target_year).order_by("name")
    )
    promotion_map = {}
    try:
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        from apps.academics.models import ClassroomPromotionMapping

        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
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
        StudentResourceReturn.objects.filter(  # tenant-isolation-allow: celery-delegation-lifecycle-cross-user-graph-reviewed
            academic_year=source_year, returned_at__isnull=True
        )
        .values("student_id")
        .annotate(count=Count("id"))
        .values_list("student_id", "count")
    )

    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    from apps.academics.models import Term

    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    terms = list(
        Term.objects.filter(academic_year=source_year).order_by(
            # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
            "position", "start_date"
        )
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    )
    students = list(
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        StudentProfile.objects.filter(
            academic_year=source_year, is_active=True
        ).select_related("classroom")
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
        promo = (
            get_promotion_status(s, source_year, annual_avg)
            if annual_avg is not None
            else "NO_DATA"
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        )
        suggested = None
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        if s.classroom_id and promotion_map:
            suggested = promotion_map.get(s.classroom_id)
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        if not suggested and s.classroom:
            suggested = Classroom.objects.filter(
                academic_year=target_year, name=s.classroom.name
            ).first()
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
    logger.info(
        "prepare_rollover_proposal: created proposal %s with %d items",
        proposal.pk,
        created,
    )
    return {"ok": True, "proposal_id": proposal.pk, "items": created}


@shared_task(name="accounts.prepare_rollover_proposal")
def prepare_rollover_proposal(
    school_id, source_year_id, target_year_id, created_by_id=None
):
    """Build rollover proposal. Runs in tenant context for school_id."""
    return _run_with_tenant_context(
        school_id=str(school_id),
        runnable=lambda: _prepare_rollover_proposal_impl(
            school_id, source_year_id, target_year_id, created_by_id
        ),
    )


def _apply_rollover_proposal_impl(
    proposal_id,
    lock_source=False,
    notify_parents=False,
    allow_outstanding_returns=False,
    carry_forward_arrears=False,
):
    """Inner implementation: run inside tenant context."""
    import logging
    from django.utils import timezone
    from apps.accounts.models import RolloverProposal
    from apps.people.enrollment_services import (
        graduate_student,
        open_enrollment,
        outcome_for_manual_placement,
    )
    from apps.people.models import StudentProfile

    logger = logging.getLogger(__name__)
    # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
    try:
        proposal = RolloverProposal.objects.get(pk=proposal_id)
    except RolloverProposal.DoesNotExist:
        return {"ok": False, "error": "Proposal not found"}
    if proposal.status != RolloverProposal.Status.APPROVED:
        return {
            "ok": False,
            "error": f"Proposal status is {proposal.status}, must be APPROVED",
        }

    source_year = proposal.source_year
    target_year = proposal.target_year
    # config-resolver-allow: method call get_backend_feature_flags() on the namespace object
    site = get_effective_site_settings(school=getattr(proposal, "school", None))
    if callable(getattr(site, "get_backend_feature_flags", None)):
        flags = site.get_backend_feature_flags()
    else:
        flags = getattr(site, "backend_feature_flags", None) or {}
    block_outstanding = flags.get("block_promotion_if_outstanding_returns", False)

    updated = 0
    graduated = 0
    skipped = 0
    rolled_students = []
    for item in proposal.items.select_related(
        "student", "suggested_next_classroom", "approved_next_classroom"
    ).all():
        student = item.student
        if (
            block_outstanding
            and not allow_outstanding_returns
            and (item.outstanding_returns or 0) > 0
        ):
            skipped += 1
            continue
        if getattr(item, "is_graduate", False):
            # Close the enrollment BEFORE the legacy fields are cleared, so the
            # leaving year is preserved in history rather than blanked (2.2).
            graduate_student(student, target_year)
            student.academic_year = target_year
            student.classroom = None
            student.status = StudentProfile.Status.ALUMNI
            student.is_active = False
            student.save(
                update_fields=["academic_year", "classroom", "status", "is_active"]
            )
            graduated += 1
            continue
        next_class = item.approved_next_classroom or item.suggested_next_classroom
        if next_class is None:
            skipped += 1
            continue
        # 2.2: open a NEW enrollment and close the prior one instead of
        # overwriting the student row. The operator's approved classroom still
        # wins; only the recorded OUTCOME is derived (same grade => RETAINED).
        source_enrollment = student.enrollment_for_year(source_year)
        source_classroom = (
            source_enrollment.classroom
            if source_enrollment is not None and source_enrollment.classroom_id
            else student.classroom
        )
        open_enrollment(
            student,
            target_year,
            next_class,
            entry_date=getattr(target_year, "start_date", None),
            close_outcome=outcome_for_manual_placement(
                source_classroom, next_class, item.promotion_status or ""
            ),
        )
        updated += 1
        rolled_students.append((student, next_class))

    # Notify-parity with the synchronous rollover view: when the operator asked
    # to notify parents, send the SAME per-guardian in-app notification (and
    # optional SMS) that ``rollover_year`` sends. Previously this task accepted
    # ``notify_parents`` and silently ignored it.
    if notify_parents and rolled_students:
        try:
            from apps.accounts.views_rollover import _notify_guardians_of_rollover

            _notify_guardians_of_rollover(
                rolled_students,
                target_year,
                created_by=getattr(proposal, "approved_by", None)
                or getattr(proposal, "created_by", None),
            )
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            logger.warning(
                "apply_rollover_proposal: guardian notify failed: %s", e
            )

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
            _school_id = (
                str(proposal.school_id)
                if getattr(proposal, "school_id", None)
                else None
            )
            log_exception_with_context(
                "apply_rollover_proposal: carry_forward_arrears failed",
                school_id=_school_id,
                extra={
                    "task": "apply_rollover_proposal",
                    "proposal_id": proposal_id,
                    "error": str(e),
                },
            )
            logger.warning("apply_rollover_proposal: carry_forward_arrears: %s", e)

    logger.info(
        "apply_rollover_proposal: proposal %s applied; updated=%d graduated=%d skipped=%d",
        proposal_id,
        updated,
        graduated,
        skipped,
    )
    return {"ok": True, "updated": updated, "graduated": graduated, "skipped": skipped}


@shared_task(name="accounts.apply_rollover_proposal")
def apply_rollover_proposal(
    proposal_id,
    lock_source=False,
    notify_parents=False,
    allow_outstanding_returns=False,
    carry_forward_arrears=False,
    school_id: str | None = None,
):
    """Apply APPROVED rollover proposal. Runs in tenant context when school_id is provided."""

    def _run():
        return _apply_rollover_proposal_impl(
            proposal_id,
            lock_source,
            notify_parents,
            allow_outstanding_returns,
            carry_forward_arrears,
        )

    if school_id:
        return _run_with_tenant_context(school_id=str(school_id), runnable=_run)
    return _apply_rollover_proposal_impl(
        proposal_id,
        lock_source,
        notify_parents,
        allow_outstanding_returns,
        carry_forward_arrears,
    )


# v3.33.0 Agent 4 — import the legacy-hashes Celery task modules so
# Celery's autodiscover_tasks() registers their @shared_task decorators.
# The modules themselves lazy-guard the Celery import so a CI lane
# without Celery can still import this module cleanly.
try:  # pragma: no cover - import side effects only
    from apps.accounts.legacy_hashes import sunset_task as _sunset_task  # noqa: F401
    from apps.accounts.legacy_hashes import key_rotation_task as _key_rotation_task  # noqa: F401
except Exception:  # noqa: BLE001 - autodiscover must not fail on a downstream import error
    logger.warning("legacy_hash_task_autodiscover_skipped", exc_info=True)


# v3.34.0 Agent 5 — upstream django-cryptography compatibility watch.
# The watch script polls PyPI weekly for new releases that may finally
# work with Django 5 (removing the django.utils.baseconv dependency).
# When a candidate appears, this task emails the operator distribution
# list — it NEVER auto-upgrades; the operator must verify in a test
# environment and PR the requirements.txt bump manually.
@shared_task(name="accounts.watch_django_cryptography_upstream")
def watch_django_cryptography_upstream() -> dict:
    """Run scripts/check_django_cryptography_compat.py and notify on COMPAT lines.

    Returns a small structured summary for logging/observability. The
    detailed audit trail lives at ``var/upstream-watch/django-cryptography-*.json``.
    """
    import importlib.util
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_django_cryptography_compat.py"
    if not script_path.exists():
        logger.warning(
            "watch_django_cryptography_upstream: script_missing path=%s",
            script_path,
        )
        return {"ok": False, "reason": "script_missing"}

    # Import the script as a module to invoke main() directly — avoids
    # spawning a subprocess (Celery worker context, shell=True forbidden).
    spec = importlib.util.spec_from_file_location(
        "_dcrypto_watch", script_path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return {"ok": False, "reason": "import_failed"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exit_code = module.main(["--repo-root", str(repo_root)])

    # Locate the most-recent audit JSON to surface a COMPAT signal.
    watch_dir = repo_root / "var" / "upstream-watch"
    latest = None
    if watch_dir.exists():
        candidates = sorted(watch_dir.glob("django-cryptography-*.json"))
        latest = candidates[-1] if candidates else None

    compat_lines: list[str] = []
    if latest is not None:
        try:
            import json as _json
            payload = _json.loads(latest.read_text(encoding="utf-8"))
            compat_lines = [
                line for line in (payload.get("summary_lines") or [])
                if isinstance(line, str) and line.startswith("COMPAT:")
            ]
        except (OSError, ValueError) as exc:  # pragma: no cover - audit json malformed
            logger.warning(
                "watch_django_cryptography_upstream: audit_parse_failed err=%s",
                type(exc).__name__,
            )

    if compat_lines:
        # Operator notification — uses Django's email scaffolding when
        # available, otherwise just logs at WARNING so ops can grep.
        try:
            from django.core.mail import mail_admins
            mail_admins(
                subject="[RunMyCampus] django-cryptography Django-5 compat candidate",
                message=(
                    "The weekly upstream watch flagged a candidate release:\n\n"
                    + "\n".join(compat_lines)
                    + f"\n\nAudit trail: {latest}\n"
                    + "Follow docs/SECURITY_KEYS.md § 'Internal Fernet Shim Migration Plan' "
                    + "before bumping requirements.txt.\n"
                ),
                fail_silently=True,
            )
        except Exception:  # noqa: BLE001 - email backend is operator-configured
            logger.warning(
                "watch_django_cryptography_upstream: mail_admins_failed",
                exc_info=True,
            )
        logger.info(
            "watch_django_cryptography_upstream: compat_candidates_found "
            "count=%s audit=%s",
            len(compat_lines), latest,
        )

    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "compat_candidate_count": len(compat_lines),
        "audit_path": str(latest) if latest else None,
    }
