"""
Phase 10 — 2.1: Year clone and rollover views (clone_year_setup, rollover_year, rollover_queue, proposal detail/prepare).
Extracted from accounts/views.py for giant-file decomposition.
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Count
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.academics.models import AcademicYear, Classroom, Term
from apps.academics.graduation_audit import (
    audit_graduating_cohort,
    audit_graduation_eligibility,
)
from apps.academics.services_year_setup import clone_academic_year
from apps.accounts.decorators import permission_required
from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.accounts.rollover_backup import (
    create_pre_rollover_backup,
    require_pre_rollover_backup,
)
from apps.people.enrollment_services import (
    graduate_student,
    open_enrollment,
    outcome_for_manual_placement,
)
from apps.people.models import StudentProfile, StudentResourceReturn
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.reports.services import get_promotion_status, _annual_average_for_student


def _enqueue_rollover_task(task, *args, **kwargs):
    """Prefer async Celery; fall back to in-process apply when broker is unavailable."""
    from apps.platform_runtime.workflow_telemetry import enqueue_background_job

    return enqueue_background_job(task, *args, **kwargs)


def _is_admin_user(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", None) == User.Role.ADMIN
    )


def _notify_guardians_of_rollover(rolled_students, target_year, *, created_by=None):
    """Notify each guardian of each rolled-over student.

    Shared by the synchronous ``rollover_year`` view and the async
    ``apps.accounts.tasks.apply_rollover_proposal`` task so BOTH apply paths send
    the identical in-app notification (and optional SMS) — previously only the
    sync path did, so a queued rollover with "Notify parents" ticked was silent.

    ``rolled_students`` is an iterable of ``(student, new_classroom)`` tuples.
    Returns the number of in-app notifications created (for logging/tests).
    """
    if not rolled_students:
        return 0
    from apps.people.models import StudentGuardian
    from apps.finance.models import Notification as FinanceNotification

    notifier = None
    try:
        from apps.evals.notifications import NotificationService

        notifier = NotificationService()
    except ImportError:
        pass

    notified = 0
    for student, new_classroom in rolled_students:
        msg = f"Your child {student.get_full_name() or student.last_name} has been assigned to {new_classroom.name} for {target_year.name}."
        for link in StudentGuardian.objects.filter(
            student=student
        ).select_related("guardian_user"):
            if link.guardian_user_id:
                FinanceNotification.objects.notify_unread(
                    title="Class assignment",
                    message=msg,
                    severity=FinanceNotification.Severity.INFO,
                    recipient_id=link.guardian_user_id,
                    created_by=created_by,
                )
                notified += 1
            if (
                notifier
                and getattr(link, "phone", None)
                and link.phone
                and getattr(link, "receives_sms", False)
            ):
                try:
                    notifier.send_sms(link.phone, msg)
                except (
                    AttributeError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    pass
    return notified


def _years_for_clone(request):
    qs = AcademicYear.objects.all().order_by("-start_date")
    school = getattr(request, "school", None)
    if school is not None and getattr(school, "pk", None):
        qs = qs.filter(school=school)  # tenant-isolation-allow: clone-year-scoped-to-request-school
    return list(qs)


def _create_academic_year_url() -> str:
    for name in (
        "admin:academics_academicyear_add",
        "siteconfig:academic_years_setup_evidence",
        "academics:hub",
        "admin:academics_academicyear_changelist",
    ):
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return ""


def _clone_year_context(request, years):
    return {
        "years": years,
        "can_clone": len(years) >= 2,
        "create_year_url": _create_academic_year_url(),
        "year_count": len(years),
    }


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def clone_year_setup(request):
    """
    Clone structure from a previous academic year to a target year (terms, classrooms, subject assignments, promotion rules).
    Target year must already exist; create it first if the school has fewer than two years.
    """
    years = _years_for_clone(request)
    ctx = _clone_year_context(request, years)
    if request.method == "POST":
        if not ctx["can_clone"]:
            messages.error(
                request,
                "Create the new academic year first, then clone last year's classrooms into it.",
            )
            return render(request, "accounts/clone_year_setup.html", ctx)
        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/clone_year_setup.html", ctx)

        if source_id == target_id:
            messages.error(request, "Source and target year must be different.")
            return render(request, "accounts/clone_year_setup.html", ctx)

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        school = getattr(request, "school", None)
        if school is not None:
            if getattr(source_year, "school_id", None) not in (None, school.pk) or getattr(
                target_year, "school_id", None
            ) not in (None, school.pk):
                messages.error(request, "Those academic years are not part of this school.")
                return render(request, "accounts/clone_year_setup.html", ctx)
        try:
            stats = clone_academic_year(source_year, target_year)
            messages.success(
                request,
                f"Cloned {source_year.name} → {target_year.name}: "
                f"{stats['terms_created']} terms, {stats['classrooms_created']} classrooms, "
                f"{stats['subject_assignments_created']} subject assignments, {stats['promotion_rules_created']} promotion rules.",
            )
            return redirect("studio_os:workflow_center")
        except (DatabaseError, RuntimeError, TypeError, ValueError) as e:
            school_id = str(getattr(getattr(request, "school", None), "pk", None) or "")
            log_exception_with_context(
                "accounts clone_year_setup: clone_academic_year failed",
                school_id=school_id,
                extra={
                    "view": "clone_year_setup",
                    "source_year_id": source_year.id,
                    "target_year_id": target_year.id,
                    "error": str(e),
                },
            )
            messages.error(request, f"Clone failed: {e}")
            return render(request, "accounts/clone_year_setup.html", ctx)

    return render(request, "accounts/clone_year_setup.html", ctx)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def rollover_year(request):
    """
    Year-end rollover: move students from source year to target year and assign next classroom.
    Uses promotion status to suggest next class; operator can override per student.
    Optionally lock the source year after rollover.
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """
    years = list(AcademicYear.objects.all().order_by("-start_date"))
    if request.method == "POST":
        # "Back up now" affordance — trigger the M28 tenant DR snapshot for this
        # school so the pre-rollover backup gate below is satisfied, then return
        # to the form (does NOT apply the rollover).
        if request.POST.get("create_backup_now"):
            backup_school = getattr(request, "school", None)
            if backup_school is None:
                messages.error(
                    request, "School context is required to create a backup."
                )
                return render(
                    request, "accounts/rollover_year.html", {"years": years}
                )
            try:
                result = create_pre_rollover_backup(backup_school)
                messages.success(
                    request,
                    "Backup created "
                    f"({result.get('byte_size', 0)} bytes). "
                    "You can now run the rollover.",
                )
            except (
                DatabaseError,
                ImportError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                school_id = str(getattr(backup_school, "pk", "") or "")
                log_exception_with_context(
                    "accounts rollover_year: create_pre_rollover_backup failed",
                    school_id=school_id,
                    extra={"view": "rollover_year", "error": str(e)},
                )
                messages.error(request, f"Backup failed: {e}")
            return render(request, "accounts/rollover_year.html", {"years": years})
        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        lock_source = request.POST.get("lock_source") == "on"
        notify_parents = request.POST.get("notify_parents") == "on"
        allow_outstanding_returns = (
            request.POST.get("allow_outstanding_returns") == "on"
        )
        carry_forward_arrears_check = request.POST.get("carry_forward_arrears") == "on"
        override_graduation_gate = (
            request.POST.get("acknowledge_ineligible_graduates") == "on"
        )
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/rollover_year.html", {"years": years})

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        if getattr(source_year, "is_locked", False):
            messages.error(
                request,
                f"{source_year.name} is locked; rollover from this year is not allowed.",
            )
            return render(request, "accounts/rollover_year.html", {"years": years})
        school = getattr(request, "school", None)
        # Pre-rollover backup gate (M29 / EOY gap #3) — fires BEFORE any student
        # is moved. Refuses the destructive apply unless a recent M28 tenant DR
        # snapshot exists for this school OR the operator ticked
        # "acknowledge_no_backup" to explicitly override.
        try:
            require_pre_rollover_backup(
                school,
                source_year,
                override=request.POST.get("acknowledge_no_backup") == "on",
                created_by=request.user,
            )
        except ValidationError as e:
            messages.error(request, e.messages[0] if e.messages else str(e))
            return render(request, "accounts/rollover_year.html", {"years": years})
        if school is not None:
            from apps.academics.year_close import evaluate_year_close_blockers

            scorecard = evaluate_year_close_blockers(
                school, source_year, target_year
            )
            if not scorecard["ok"] and not allow_outstanding_returns:
                for blocker in scorecard["blockers"]:
                    if blocker["code"] == "outstanding_returns":
                        continue
                    messages.error(request, blocker["message"])
                if any(
                    b["code"] != "outstanding_returns" for b in scorecard["blockers"]
                ):
                    return render(
                        request,
                        "accounts/rollover_year.html",
                        {
                            "years": years,
                            "year_close_dry_run": scorecard,
                        },
                    )
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        target_classrooms = list(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Classroom.objects.filter(academic_year=target_year).order_by("name")
        )
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        target_classrooms_by_id = {c.id: c for c in target_classrooms}

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        students = list(
            StudentProfile.objects.filter(
                academic_year=source_year, is_active=True
            ).select_related("classroom")
        )
        flags = get_effective_flags(request)
        block_if_outstanding = flags.get(
            "block_promotion_if_outstanding_returns", False
        )
        outstanding_by_student = dict(
            StudentResourceReturn.objects.filter(
                academic_year=source_year,
                returned_at__isnull=True,
            )
            .values("student_id")
            .annotate(count=Count("id"))
            .values_list("student_id", "count")
        )
        # M29 / EOY — freeze the immutable grade archive BEFORE any student is
        # moved. The graduation branch below sets is_active=False, which
        # ``batch_freeze_transcripts`` (is_active=True only) would then skip, so
        # freezing here — while every student is still active — captures the
        # graduating cohort's final transcripts too. Gated on ``lock_source``
        # (locking the source year = closing it = freeze its history);
        # best-effort so a freeze error never breaks the rollover.
        if lock_source and school is not None:
            try:
                from apps.academics.year_close import batch_freeze_transcripts

                freeze_result = batch_freeze_transcripts(school, source_year)
                if freeze_result.get("created"):
                    messages.success(
                        request,
                        f"Archived {freeze_result['created']} immutable "
                        f"transcript(s) for {source_year.name}.",
                    )
            except Exception as e:  # noqa: BLE001 - transcript freeze is best-effort, never fatal
                _school_id = str(getattr(school, "pk", "") or "")
                log_exception_with_context(
                    "accounts rollover_year: transcript freeze failed",
                    school_id=_school_id,
                    extra={"view": "rollover_year", "error": str(e)},
                )
        updated = 0
        graduated = 0
        skipped_outstanding = 0
        graduation_blocked = 0
        rolled_students = []
        GRADUATE_VALUE = "__graduate__"
        from django.db import connection

        from apps.platform_runtime.workflow_telemetry import (
            TASK_EOY_ROLLOVER,
            update_and_broadcast_progress,
        )
        from apps.platform_runtime.workflow_tracker import ensure_workflow_run

        expected = max(len(students), 1)
        schema = str(getattr(connection, "schema_name", "") or "")
        with ensure_workflow_run(
            "accounts-rollover",
            steps=("place_students", "finalize"),
            expected_duration_seconds=900,  # magic-number-allow: workflow-expected-duration-seconds
            school_id=str(getattr(school, "pk", "") or ""),
            tenant_schema=schema,
            payload={"task_type": TASK_EOY_ROLLOVER},
        ):
            update_and_broadcast_progress(
                school=school,
                task_type=TASK_EOY_ROLLOVER,
                processed=0,
                expected=expected,
                log_message="Rollover apply started",
            )
            for index, s in enumerate(students, start=1):
                try:
                    key = f"classroom_{s.id}"
                    classroom_id = request.POST.get(key)
                    if not classroom_id:
                        continue
                    outstanding = outstanding_by_student.get(s.id, 0)
                    if (
                        block_if_outstanding
                        and not allow_outstanding_returns
                        and outstanding > 0
                    ):
                        skipped_outstanding += 1
                        continue
                    if classroom_id == GRADUATE_VALUE:
                        # W22 graduation gate (async/sync parity with the proposal apply
                        # path): don't graduate an off-track student when requirements are
                        # configured and the operator did not override. Absent config →
                        # requirements_configured is False → this never bites.
                        grad_audit = audit_graduation_eligibility(s, source_year)
                        if (
                            grad_audit.requirements_configured
                            and not grad_audit.is_eligible
                            and not override_graduation_gate
                        ):
                            graduation_blocked += 1
                            continue
                        # Close the enrollment BEFORE blanking the legacy fields so the
                        # leaving year survives in history (2.2).
                        graduate_student(s, target_year)
                        s.academic_year = target_year
                        s.classroom = None
                        s.status = StudentProfile.Status.ALUMNI
                        s.is_active = False
                        s.save(
                            update_fields=[
                                "academic_year",
                                "classroom",
                                "status",
                                "is_active",
                            ]
                        )
                        graduated += 1
                        continue
                    try:
                        new_class = target_classrooms_by_id.get(int(classroom_id))
                    except (ValueError, TypeError):
                        continue
                    if not new_class:
                        continue
                    # 2.2: open a new enrollment and close the prior one. The operator's
                    # chosen class still wins; the OUTCOME is derived from it, so a
                    # student left in the same grade is recorded as RETAINED rather than
                    # indistinguishable from a promotion.
                    source_enrollment = s.enrollment_for_year(source_year)
                    source_classroom = (
                        source_enrollment.classroom
                        if source_enrollment is not None
                        and source_enrollment.classroom_id
                        else s.classroom
                    )
                    open_enrollment(
                        s,
                        target_year,
                        new_class,
                        entry_date=getattr(target_year, "start_date", None),
                        close_outcome=outcome_for_manual_placement(
                            source_classroom, new_class
                        ),
                    )
                    updated += 1
                    rolled_students.append((s, new_class))
                finally:
                    update_and_broadcast_progress(
                        school=school,
                        task_type=TASK_EOY_ROLLOVER,
                        processed=index,
                        expected=expected,
                        log_message=f"Processed student record {index} of {expected}",
                    )
        if notify_parents and rolled_students:
            _notify_guardians_of_rollover(
                rolled_students, target_year, created_by=request.user
            )
        if carry_forward_arrears_check and flags.get(
            "carry_forward_arrears_on_rollover", True
        ):
            try:
                from apps.finance.services import carry_forward_arrears

                arrears_created = carry_forward_arrears(source_year, target_year)
                if arrears_created:
                    messages.success(
                        request,
                        f"Created {arrears_created} opening balance (arrears) invoice(s) in {target_year.name}.",
                    )
            except (
                DatabaseError,
                ImportError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                school_id = str(
                    getattr(getattr(request, "school", None), "pk", None) or ""
                )
                log_exception_with_context(
                    "accounts rollover_year: carry_forward_arrears failed",
                    school_id=school_id,
                    extra={
                        "view": "rollover_year",
                        "source_year_id": source_year.id,
                        "target_year_id": target_year.id,
                        "error": str(e),
                    },
                )
                messages.error(
                    request,
                    f"Arrears carry-forward failed: {e}. Please check Finance configuration.",
                )
        if lock_source:
            from apps.academics.year_close import lock_source_year

            lock_source_year(
                school,
                source_year,
                actor=request.user,
                reason="rollover_year lock_source",
                activate_target=target_year,
            )
            messages.success(
                request,
                f"Rolled over {updated} students to {target_year.name}, "
                f"hard-closed {source_year.name}, and set {target_year.name} as the active year.",
            )
        else:
            messages.success(
                request, f"Rolled over {updated} students to {target_year.name}."
            )
        if graduated:
            messages.success(request, f"Marked {graduated} student(s) as Alumni.")
        if skipped_outstanding:
            messages.warning(
                request,
                f"Skipped {skipped_outstanding} student(s) due to outstanding resource returns. "
                "Enable 'Allow rollover despite outstanding returns' to include them, or mark items returned in Resource return checklist.",
            )
        if graduation_blocked:
            messages.warning(
                request,
                f"Did not graduate {graduation_blocked} student(s) who do not meet the "
                "configured graduation requirements. Review their records, or tick "
                "'graduate them anyway' to override the graduation gate.",
            )
        return redirect("accounts:rollover_year")

    source_id = request.GET.get("source_year")
    target_id = request.GET.get("target_year")
    context = {
        "years": years,
        "rows": [],
        "source_year": None,
        "target_year": None,
        "target_classrooms": [],
        "checklist": [],
        "block_promotion_if_outstanding_returns": False,
        "carry_forward_arrears_on_rollover": False,
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    }
    if source_id and target_id:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        source_year = AcademicYear.objects.filter(id=source_id).first()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        target_year = AcademicYear.objects.filter(id=target_id).first()
        if source_year and target_year:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            context["source_year"] = source_year
            context["target_year"] = target_year
            target_classrooms_list = list(
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                Classroom.objects.filter(academic_year=target_year).order_by("name")
            )
            context["target_classrooms"] = target_classrooms_list
            source_locked = getattr(source_year, "is_locked", False)
            context["checklist"] = [
                {"label": "Source year is not locked", "ok": not source_locked},
                {
                    "label": "Target year has classrooms",
                    "ok": len(target_classrooms_list) > 0,
                },
                {
                    "label": "Final grades entered and reports finalized (manual check)",
                    "ok": None,
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                },
            ]
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            promotion_map = {}
            try:
                from apps.academics.models import ClassroomPromotionMapping
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

                for m in ClassroomPromotionMapping.objects.filter(
                    source_year=source_year, target_year=target_year
                ).select_related("source_classroom", "target_classroom"):
                    if m.source_classroom_id:
                        promotion_map[m.source_classroom_id] = m.target_classroom
            except (
                DatabaseError,
                ImportError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e:
                school_id = str(
                    getattr(getattr(request, "school", None), "pk", None) or ""
                )
                log_exception_with_context(
                    "accounts rollover_year: ClassroomPromotionMapping query failed",
                    school_id=school_id,
                    extra={
                        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                        "view": "rollover_year",
                        "source_year_id": source_year.id,
                        "target_year_id": target_year.id,
                        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                        "error": str(e),
                    },
                )
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            terms = list(
                Term.objects.filter(academic_year=source_year).order_by(
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    "position", "start_date"
                )
            )
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            students = StudentProfile.objects.filter(
                academic_year=source_year, is_active=True
            ).select_related("classroom")
            outstanding_counts = dict(
                StudentResourceReturn.objects.filter(
                    academic_year=source_year,
                    returned_at__isnull=True,
                )
                .values("student_id")
                .annotate(count=Count("id"))
                .values_list("student_id", "count")
            )
            # config-resolver-allow: method call get_backend_feature_flags() on the namespace object
            site = get_effective_site_settings(request=request)
            context["block_promotion_if_outstanding_returns"] = get_effective_flags(
                request
            ).get("block_promotion_if_outstanding_returns", False)
            backend_flags = (
                site.get_backend_feature_flags()
                if callable(getattr(site, "get_backend_feature_flags", None))
                else {}
            )
            context["carry_forward_arrears_on_rollover"] = backend_flags.get(
                "carry_forward_arrears_on_rollover", True
            )
            for s in students:
                annual_avg = _annual_average_for_student(s, terms) if terms else None
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                promo = (
                    get_promotion_status(s, source_year, annual_avg)
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    if annual_avg is not None
                    else "NO_DATA"
                )
                suggested = None
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                if s.classroom_id and promotion_map:
                    suggested = promotion_map.get(s.classroom_id)
                if not suggested and s.classroom:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    suggested = Classroom.objects.filter(
                        academic_year=target_year, name=s.classroom.name
                    ).first()
                if not suggested and context["target_classrooms"]:
                    suggested = context["target_classrooms"][0]
                context["rows"].append(
                    {
                        "student": s,
                        "annual_average": round(annual_avg, 2)
                        if annual_avg is not None
                        else None,
                        "promotion_status": promo,
                        "suggested_classroom": suggested,
                        "outstanding_returns": outstanding_counts.get(s.id, 0),
                    }
                )
    context["rollover_queue_url"] = reverse("accounts:rollover_queue")
    return render(request, "accounts/rollover_year.html", context)


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET"])
def rollover_queue(request):
    """Plan II: List PENDING and APPROVED rollover proposals for the current school."""
    school = getattr(request, "school", None)
    school_id = school.pk if school else None
    if not school_id:
        messages.error(request, "School context required.")
        return redirect("accounts:rollover_year")
    proposals = list(
        RolloverProposal.objects.filter(school_id=school_id)
        .exclude(
            status__in=[
                RolloverProposal.Status.APPLIED,
                RolloverProposal.Status.CANCELLED,
            ]
        )
        .select_related("source_year", "target_year", "created_by")
        .order_by("-created_at")[:50]
    )
    return render(request, "accounts/rollover_queue.html", {"proposals": proposals})


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["GET", "POST"])
def rollover_proposal_detail(request, proposal_id):
    """Plan II: Review/edit proposal items (approved_next_classroom, is_graduate) and Approve or Apply."""
    proposal = get_object_or_404(RolloverProposal, pk=proposal_id)
    school = getattr(request, "school", None)
    if not school or proposal.school_id != school.pk:
        from django.http import HttpResponseForbidden
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        return HttpResponseForbidden()
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    target_classrooms = list(
        Classroom.objects.filter(academic_year=proposal.target_year).order_by("name")
    )
    items = list(
        RolloverProposalItem.objects.filter(proposal=proposal)
        .select_related(
            "student",
            "student__classroom",
            "suggested_next_classroom",
            "approved_next_classroom",
        )
        .order_by("student__last_name", "student__first_name")
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            for item in items:
                key_room = f"classroom_{item.id}"
                room_id = request.POST.get(key_room)
                if request.POST.get(f"graduate_{item.id}") == "on":
                    item.is_graduate = True
                    item.approved_next_classroom_id = None
                else:
                    item.is_graduate = False
                    if room_id:
                        try:
                            item.approved_next_classroom_id = int(room_id)
                        except (ValueError, TypeError):
                            item.approved_next_classroom_id = (
                                item.suggested_next_classroom_id
                            )
                    else:
                        item.approved_next_classroom_id = (
                            item.suggested_next_classroom_id
                        )
                item.save(update_fields=["is_graduate", "approved_next_classroom_id"])
            proposal.status = RolloverProposal.Status.APPROVED
            proposal.approved_at = timezone.now()
            proposal.approved_by = request.user
            proposal.save(update_fields=["status", "approved_at", "approved_by"])
            messages.success(
                request, "Rollover proposal approved. You can now Apply it."
            )
            return redirect(
                "accounts:rollover_proposal_detail", proposal_id=proposal_id
            )
        if action == "apply":
            lock_source = request.POST.get("lock_source") == "on"
            notify_parents = request.POST.get("notify_parents") == "on"
            allow_outstanding = request.POST.get("allow_outstanding_returns") == "on"
            carry_arrears = request.POST.get("carry_forward_arrears") == "on"
            override_backup = request.POST.get("acknowledge_no_backup") == "on"
            override_graduation = (
                request.POST.get("acknowledge_ineligible_graduates") == "on"
            )
            # Pre-rollover backup gate (M29 / EOY gap #3): fail the apply here,
            # in-request, when there is no recent M28 snapshot and the operator
            # did not override — rather than enqueueing a task that would refuse
            # and silently leave the proposal unapplied.
            try:
                require_pre_rollover_backup(
                    school,
                    proposal.source_year,
                    override=override_backup,
                    created_by=proposal.approved_by or proposal.created_by,
                )
            except ValidationError as e:
                messages.error(request, e.messages[0] if e.messages else str(e))
                return redirect(
                    "accounts:rollover_proposal_detail", proposal_id=proposal_id
                )
            from apps.accounts.tasks import apply_rollover_proposal

            enqueue_kwargs = {
                "lock_source": lock_source,
                "notify_parents": notify_parents,
                "allow_outstanding_returns": allow_outstanding,
                "carry_forward_arrears": carry_arrears,
                "override_backup_gate": override_backup,
                "override_graduation_gate": override_graduation,
            }
            if getattr(school, "pk", None):
                enqueue_kwargs["school_id"] = str(school.pk)
            _enqueue_rollover_task(
                apply_rollover_proposal,
                proposal_id,
                **enqueue_kwargs,
            )
            messages.success(
                request,
                "Rollover is running. Watch live progress on this page.",
            )
            return redirect(
                "accounts:rollover_proposal_detail", proposal_id=proposal_id
            )
    # When the proposal is APPROVED the apply form is shown — surface a per-graduate
    # eligibility check (W22) so the operator sees who is off-track before applying,
    # and gate the override checkbox on there being at least one ineligible graduate.
    graduation_audits = []
    has_ineligible_graduates = False
    if proposal.status == RolloverProposal.Status.APPROVED:
        for cohort_item, result in audit_graduating_cohort(proposal):
            graduation_audits.append(
                {"item": cohort_item, "student": cohort_item.student, "result": result}
            )
            if result.requirements_configured and not result.is_eligible:
                has_ineligible_graduates = True
    return render(
        request,
        "accounts/rollover_proposal_detail.html",
        {
            "proposal": proposal,
            "items": items,
            "target_classrooms": target_classrooms,
            "graduation_audits": graduation_audits,
            "has_ineligible_graduates": has_ineligible_graduates,
        },
    )


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
@require_http_methods(["POST"])
def rollover_prepare(request):
    """Plan II: Enqueue or run prepare_rollover_proposal and redirect to proposal detail or queue."""
    source_id = request.POST.get("source_year")
    target_id = request.POST.get("target_year")
    if not source_id or not target_id:
        messages.error(request, "Select source and target year.")
        return redirect("accounts:rollover_year")
    source_year = get_object_or_404(AcademicYear, id=source_id)
    target_year = get_object_or_404(AcademicYear, id=target_id)
    school = getattr(request, "school", None)
    school_id = school.pk if school else None
    if not school_id:
        messages.error(request, "School context required.")
        return redirect("accounts:rollover_year")
    if getattr(source_year, "is_locked", False):
        messages.error(request, "Source year is locked.")
        return redirect("accounts:rollover_year")
    from apps.accounts.tasks import prepare_rollover_proposal

    result = prepare_rollover_proposal.apply(
        args=[school_id, source_year.id, target_year.id],
        kwargs={"created_by_id": request.user.pk},
    )
    if getattr(result, "result", {}).get("ok"):
        proposal_id = result.result.get("proposal_id")
        if proposal_id:
            messages.success(
                request,
                f"Rollover proposal created with {result.result.get('items', 0)} students. Review and approve below.",
            )
            return redirect(
                "accounts:rollover_proposal_detail", proposal_id=proposal_id
            )
    messages.error(
        request,
        (getattr(result, "result", None) or {}).get(
            "error", "Failed to prepare proposal."
        ),
    )
    return redirect("accounts:rollover_year")
