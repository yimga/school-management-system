"""
Phase 10 — 2.1: Year clone and rollover views (clone_year_setup, rollover_year, rollover_queue, proposal detail/prepare).
Extracted from accounts/views.py for giant-file decomposition.
"""
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.academics.models import AcademicYear, Classroom, Term
from apps.academics.services_year_setup import clone_academic_year
from apps.accounts.decorators import permission_required
from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.people.models import StudentProfile, StudentResourceReturn
from apps.platform_runtime.helpers import get_effective_flags, get_effective_site_settings
from apps.reports.services import get_promotion_status, _annual_average_for_student


def _is_admin_user(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or getattr(user, "role", None) == User.Role.ADMIN
    )


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def clone_year_setup(request):
    """
    Clone structure from a previous academic year to a target year (terms, classrooms, subject assignments, promotion rules).
    Target year must already exist; create it in admin first if needed.
    """
    years = list(AcademicYear.objects.all().order_by("-start_date"))
    if request.method == "POST":
        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

        if source_id == target_id:
            messages.error(request, "Source and target year must be different.")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        try:
            stats = clone_academic_year(source_year, target_year)
            messages.success(
                request,
                f"Cloned {source_year.name} → {target_year.name}: "
                f"{stats['terms_created']} terms, {stats['classrooms_created']} classrooms, "
                f"{stats['subject_assignments_created']} subject assignments, {stats['promotion_rules_created']} promotion rules.",
            )
            return redirect("accounts:workflow_center")
        except Exception as e:
            messages.error(request, f"Clone failed: {e}")
            return render(request, "accounts/clone_year_setup.html", {"years": years})

    return render(request, "accounts/clone_year_setup.html", {"years": years})


@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def rollover_year(request):
    """
    Year-end rollover: move students from source year to target year and assign next classroom.
    Uses promotion status to suggest next class; operator can override per student.
    Optionally lock the source year after rollover.
    """
    years = list(AcademicYear.objects.all().order_by("-start_date"))
    if request.method == "POST":
        source_id = request.POST.get("source_year")
        target_id = request.POST.get("target_year")
        lock_source = request.POST.get("lock_source") == "on"
        notify_parents = request.POST.get("notify_parents") == "on"
        allow_outstanding_returns = request.POST.get("allow_outstanding_returns") == "on"
        carry_forward_arrears_check = request.POST.get("carry_forward_arrears") == "on"
        if not source_id or not target_id:
            messages.error(request, "Please select both source and target year.")
            return render(request, "accounts/rollover_year.html", {"years": years})

        source_year = get_object_or_404(AcademicYear, id=source_id)
        target_year = get_object_or_404(AcademicYear, id=target_id)
        if getattr(source_year, "is_locked", False):
            messages.error(request, f"{source_year.name} is locked; rollover from this year is not allowed.")
            return render(request, "accounts/rollover_year.html", {"years": years})

        target_classrooms = list(Classroom.objects.filter(academic_year=target_year).order_by("name"))
        target_classrooms_by_id = {c.id: c for c in target_classrooms}

        students = list(StudentProfile.objects.filter(
            academic_year=source_year, is_active=True
        ).select_related("classroom"))
        flags = get_effective_flags(request)
        block_if_outstanding = flags.get("block_promotion_if_outstanding_returns", False)
        outstanding_by_student = dict(
            StudentResourceReturn.objects.filter(
                academic_year=source_year,
                returned_at__isnull=True,
            )
            .values("student_id")
            .annotate(count=Count("id"))
            .values_list("student_id", "count")
        )
        updated = 0
        graduated = 0
        skipped_outstanding = 0
        rolled_students = []
        GRADUATE_VALUE = "__graduate__"
        for s in students:
            key = f"classroom_{s.id}"
            classroom_id = request.POST.get(key)
            if not classroom_id:
                continue
            outstanding = outstanding_by_student.get(s.id, 0)
            if block_if_outstanding and not allow_outstanding_returns and outstanding > 0:
                skipped_outstanding += 1
                continue
            if classroom_id == GRADUATE_VALUE:
                s.academic_year = target_year
                s.classroom = None
                s.status = StudentProfile.Status.ALUMNI
                s.is_active = False
                s.save(update_fields=["academic_year", "classroom", "status", "is_active"])
                graduated += 1
                continue
            try:
                new_class = target_classrooms_by_id.get(int(classroom_id))
            except (ValueError, TypeError):
                continue
            if not new_class:
                continue
            s.academic_year = target_year
            s.classroom = new_class
            s.save(update_fields=["academic_year", "classroom"])
            updated += 1
            rolled_students.append((s, new_class))
        if notify_parents and rolled_students:
            from apps.people.models import StudentGuardian
            from apps.finance.models import Notification as FinanceNotification
            notifier = None
            try:
                from apps.evals.notifications import NotificationService
                notifier = NotificationService()
            except Exception:
                pass
            for student, new_classroom in rolled_students:
                msg = f"Your child {student.get_full_name() or student.last_name} has been assigned to {new_classroom.name} for {target_year.name}."
                for link in StudentGuardian.objects.filter(student=student).select_related("guardian_user"):
                    if link.guardian_user_id:
                        FinanceNotification.objects.create(
                            title="Class assignment",
                            message=msg,
                            severity=FinanceNotification.Severity.INFO,
                            recipient_id=link.guardian_user_id,
                            created_by=request.user,
                        )
                    if notifier and getattr(link, "phone", None) and link.phone and getattr(link, "receives_sms", False):
                        try:
                            notifier.send_sms(link.phone, msg)
                        except Exception:
                            pass
        if carry_forward_arrears_check and flags.get("carry_forward_arrears_on_rollover", True):
            try:
                from apps.finance.services import carry_forward_arrears
                arrears_created = carry_forward_arrears(source_year, target_year)
                if arrears_created:
                    messages.success(
                        request,
                        f"Created {arrears_created} opening balance (arrears) invoice(s) in {target_year.name}.",
                    )
            except Exception as e:
                messages.error(
                    request,
                    f"Arrears carry-forward failed: {e}. Please check Finance configuration.",
                )
        if lock_source:
            source_year.is_locked = True
            source_year.save(update_fields=["is_locked"])
            messages.success(request, f"Rolled over {updated} students to {target_year.name} and locked {source_year.name}.")
        else:
            messages.success(request, f"Rolled over {updated} students to {target_year.name}.")
        if graduated:
            messages.success(request, f"Marked {graduated} student(s) as Alumni.")
        if skipped_outstanding:
            messages.warning(
                request,
                f"Skipped {skipped_outstanding} student(s) due to outstanding resource returns. "
                "Enable 'Allow rollover despite outstanding returns' to include them, or mark items returned in Resource return checklist.",
            )
        return redirect("accounts:rollover_year")

    source_id = request.GET.get("source_year")
    target_id = request.GET.get("target_year")
    context = {"years": years, "rows": [], "source_year": None, "target_year": None, "target_classrooms": [], "checklist": [], "block_promotion_if_outstanding_returns": False, "carry_forward_arrears_on_rollover": False}
    if source_id and target_id:
        source_year = AcademicYear.objects.filter(id=source_id).first()
        target_year = AcademicYear.objects.filter(id=target_id).first()
        if source_year and target_year:
            context["source_year"] = source_year
            context["target_year"] = target_year
            target_classrooms_list = list(
                Classroom.objects.filter(academic_year=target_year).order_by("name")
            )
            context["target_classrooms"] = target_classrooms_list
            source_locked = getattr(source_year, "is_locked", False)
            context["checklist"] = [
                {"label": "Source year is not locked", "ok": not source_locked},
                {"label": "Target year has classrooms", "ok": len(target_classrooms_list) > 0},
                {"label": "Final grades entered and reports finalized (manual check)", "ok": None},
            ]
            promotion_map = {}
            try:
                from apps.academics.models import ClassroomPromotionMapping
                for m in ClassroomPromotionMapping.objects.filter(
                    source_year=source_year, target_year=target_year
                ).select_related("source_classroom", "target_classroom"):
                    if m.source_classroom_id:
                        promotion_map[m.source_classroom_id] = m.target_classroom
            except Exception:
                pass
            terms = list(Term.objects.filter(academic_year=source_year).order_by("position", "start_date"))
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
            site = get_effective_site_settings(request=request)
            context["block_promotion_if_outstanding_returns"] = (
                get_effective_flags(request).get("block_promotion_if_outstanding_returns", False)
            )
            context["carry_forward_arrears_on_rollover"] = (
                (getattr(site, "backend_feature_flags", None) or {}).get("carry_forward_arrears_on_rollover", True)
            )
            for s in students:
                annual_avg = _annual_average_for_student(s, terms) if terms else None
                promo = get_promotion_status(s, source_year, annual_avg) if annual_avg is not None else "NO_DATA"
                suggested = None
                if s.classroom_id and promotion_map:
                    suggested = promotion_map.get(s.classroom_id)
                if not suggested and s.classroom:
                    suggested = Classroom.objects.filter(
                        academic_year=target_year, name=s.classroom.name
                    ).first()
                if not suggested and context["target_classrooms"]:
                    suggested = context["target_classrooms"][0]
                context["rows"].append({
                    "student": s,
                    "annual_average": round(annual_avg, 2) if annual_avg is not None else None,
                    "promotion_status": promo,
                    "suggested_classroom": suggested,
                    "outstanding_returns": outstanding_counts.get(s.id, 0),
                })
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
        .exclude(status__in=[RolloverProposal.Status.APPLIED, RolloverProposal.Status.CANCELLED])
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
        return HttpResponseForbidden()
    target_classrooms = list(
        Classroom.objects.filter(academic_year=proposal.target_year).order_by("name")
    )
    items = list(
        RolloverProposalItem.objects.filter(proposal=proposal)
        .select_related("student", "student__classroom", "suggested_next_classroom", "approved_next_classroom")
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
                            item.approved_next_classroom_id = item.suggested_next_classroom_id
                    else:
                        item.approved_next_classroom_id = item.suggested_next_classroom_id
                item.save(update_fields=["is_graduate", "approved_next_classroom_id"])
            proposal.status = RolloverProposal.Status.APPROVED
            proposal.approved_at = timezone.now()
            proposal.approved_by = request.user
            proposal.save(update_fields=["status", "approved_at", "approved_by"])
            messages.success(request, "Rollover proposal approved. You can now Apply it.")
            return redirect("accounts:rollover_proposal_detail", proposal_id=proposal_id)
        if action == "apply":
            lock_source = request.POST.get("lock_source") == "on"
            notify_parents = request.POST.get("notify_parents") == "on"
            allow_outstanding = request.POST.get("allow_outstanding_returns") == "on"
            carry_arrears = request.POST.get("carry_forward_arrears") == "on"
            from apps.accounts.tasks import apply_rollover_proposal
            apply_rollover_proposal.apply(
                args=[proposal_id],
                kwargs=dict(lock_source=lock_source, notify_parents=notify_parents, allow_outstanding_returns=allow_outstanding, carry_forward_arrears=carry_arrears),
            )
            messages.success(request, "Rollover applied. Students have been moved to the target year.")
            return redirect("accounts:rollover_queue")
    return render(
        request,
        "accounts/rollover_proposal_detail.html",
        {"proposal": proposal, "items": items, "target_classrooms": target_classrooms},
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
            messages.success(request, f"Rollover proposal created with {result.result.get('items', 0)} students. Review and approve below.")
            return redirect("accounts:rollover_proposal_detail", proposal_id=proposal_id)
    messages.error(request, (getattr(result, "result", None) or {}).get("error", "Failed to prepare proposal."))
    return redirect("accounts:rollover_year")
