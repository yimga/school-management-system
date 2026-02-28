"""
Syllabus Builder: teacher hub (course cards), builder, upload, preview, approval queue.
Uses get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL) and log_delegation_action for delegate approvals.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import CourseSyllabus, SubjectAssignment, CurriculumNode
from apps.academics.services import get_active_year_and_term
from apps.people.models import TeacherProfile
from apps.evals.models import TeacherAssignment


def _get_teacher_assignments(user):
    """Return TeacherAssignment queryset for current user and active year, or None if not a teacher with assignments."""
    try:
        teacher = TeacherProfile.objects.get(user=user)
    except TeacherProfile.DoesNotExist:
        return None
    year, _ = get_active_year_and_term()
    if not year:
        return TeacherAssignment.objects.none()
    return TeacherAssignment.objects.filter(
        teacher=teacher,
        academic_year=year,
        is_active=True,
    ).select_related(
        "subject_assignment",
        "subject_assignment__classroom",
        "subject_assignment__subject",
        "subject_assignment__term",
        "subject_assignment__academic_year",
    ).order_by("subject_assignment__classroom__name", "subject_assignment__subject__name")


def _assignment_syllabus_status(assignment):
    """Return (syllabus_or_none, status_label) for a TeacherAssignment."""
    try:
        syllabus = CourseSyllabus.objects.get(subject_assignment=assignment.subject_assignment)
        return syllabus, syllabus.get_status_display()
    except CourseSyllabus.DoesNotExist:
        return None, "Missing"


@login_required
def teacher_syllabus_hub(request):
    """Grid of course cards: Subject, Class, Syllabus Status, actions (Builder | Upload | Preview | Clone)."""
    assignments_qs = _get_teacher_assignments(request.user)
    if assignments_qs is None:
        return HttpResponseForbidden("Teacher profile not found.")
    assignments = list(assignments_qs)
    cards = []
    for ta in assignments:
        syllabus, status_label = _assignment_syllabus_status(ta)
        cards.append({
            "assignment": ta,
            "subject_assignment": ta.subject_assignment,
            "syllabus": syllabus,
            "status_label": status_label,
        })
    approved_count = sum(1 for c in cards if c["status_label"] == "Approved")
    return render(request, "academics/teacher_syllabus_hub.html", {
        "cards": cards,
        "year_term": get_active_year_and_term(),
        "approved_count": approved_count,
    })


@login_required
def syllabus_builder(request, subject_assignment_id: int):
    """Edit syllabus via builder (builder_data JSON). Create CourseSyllabus if missing."""
    sa = get_object_or_404(
        SubjectAssignment.objects.select_related("classroom", "subject", "term", "academic_year"),
        pk=subject_assignment_id,
    )
    assignments_qs = _get_teacher_assignments(request.user)
    if not assignments_qs or not assignments_qs.filter(subject_assignment=sa).exists():
        return HttpResponseForbidden("You are not assigned to this class/subject.")
    syllabus, _ = CourseSyllabus.objects.get_or_create(
        subject_assignment=sa,
        defaults={"status": CourseSyllabus.Status.DRAFT, "created_by": request.user},
    )
    if syllabus.status not in (CourseSyllabus.Status.DRAFT, CourseSyllabus.Status.NEEDS_REVISION):
        messages.info(request, "This syllabus is not in draft state; you can still edit builder data.")
    if request.method == "POST":
        import json
        raw = request.POST.get("builder_data") or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        syllabus.builder_data = data
        syllabus.status = CourseSyllabus.Status.DRAFT
        syllabus.save()
        # W6-2: Tag with standards — update curriculum_nodes from curriculum_node_ids
        node_ids = request.POST.getlist("curriculum_node_ids")
        if node_ids is not None:
            try:
                valid_ids = [int(x) for x in node_ids if str(x).isdigit()]
                school_id = getattr(sa.academic_year, "school_id", None)
                if school_id is not None:
                    qs = CurriculumNode.objects.filter(
                        pk__in=valid_ids,
                        standard__school_id__in=(school_id, None),
                    )
                    syllabus.curriculum_nodes.set(qs)
                else:
                    syllabus.curriculum_nodes.set(CurriculumNode.objects.filter(pk__in=valid_ids))
            except (ValueError, TypeError):
                pass
        messages.success(request, "Syllabus draft saved.")
        return redirect("academics:teacher_syllabus_hub")
    import json
    builder_json = json.dumps(syllabus.builder_data, indent=2) if syllabus.builder_data else "{}"
    # W6-2: Load curriculum nodes for "Tag with standards" (school-scoped or global)
    school_id = getattr(sa.academic_year, "school_id", None)
    if school_id is not None:
        available_nodes = CurriculumNode.objects.filter(
            standard__school_id__in=(school_id, None),
        ).select_related("standard").order_by("standard__name", "code")[:200]
    else:
        available_nodes = CurriculumNode.objects.select_related("standard").order_by("code")[:200]
    selected_node_ids = list(syllabus.curriculum_nodes.values_list("pk", flat=True))
    return render(request, "academics/syllabus_builder.html", {
        "syllabus": syllabus,
        "subject_assignment": sa,
        "builder_data_json": builder_json,
        "available_curriculum_nodes": available_nodes,
        "selected_curriculum_node_ids": selected_node_ids,
    })


@login_required
def syllabus_upload(request, subject_assignment_id: int):
    """Upload PDF/Word for a syllabus. Create CourseSyllabus if missing."""
    sa = get_object_or_404(SubjectAssignment, pk=subject_assignment_id)
    assignments_qs = _get_teacher_assignments(request.user)
    if not assignments_qs or not assignments_qs.filter(subject_assignment=sa).exists():
        return HttpResponseForbidden("You are not assigned to this class/subject.")
    syllabus, _ = CourseSyllabus.objects.get_or_create(
        subject_assignment=sa,
        defaults={"status": CourseSyllabus.Status.DRAFT, "created_by": request.user},
    )
    if request.method == "POST" and request.FILES.get("file"):
        from apps.accounts.validators import FileTypeValidator, FileSizeValidator
        from django.core.exceptions import ValidationError
        up = request.FILES["file"]
        try:
            FileTypeValidator(
                allowed_extensions=[".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods"],
                allowed_types=[
                    "application/pdf",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.ms-excel",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/vnd.oasis.opendocument.text",
                    "application/vnd.oasis.opendocument.spreadsheet",
                ],
                message="Only document files (PDF, Word, Excel, or ODT/ODS) are allowed.",
            )(up)
            FileSizeValidator(max_size_mb=10)(up)
        except ValidationError as e:
            messages.error(request, e.messages[0] if getattr(e, "messages", None) else str(e))
            return redirect("academics:syllabus_upload", subject_assignment_id=sa.id)
        syllabus.uploaded_file = up
        syllabus.status = CourseSyllabus.Status.DRAFT
        syllabus.save()
        messages.success(request, "File uploaded. You can submit for approval when ready.")
        return redirect("academics:teacher_syllabus_hub")
    return render(request, "academics/syllabus_upload.html", {
        "syllabus": syllabus,
        "subject_assignment": sa,
    })


@login_required
def syllabus_submit(request, subject_assignment_id: int):
    """Set status to PENDING (submit for approval)."""
    sa = get_object_or_404(SubjectAssignment, pk=subject_assignment_id)
    assignments_qs = _get_teacher_assignments(request.user)
    if not assignments_qs or not assignments_qs.filter(subject_assignment=sa).exists():
        return HttpResponseForbidden("You are not assigned to this class/subject.")
    syllabus = get_object_or_404(CourseSyllabus, subject_assignment=sa)
    if syllabus.status not in (CourseSyllabus.Status.DRAFT, CourseSyllabus.Status.NEEDS_REVISION):
        messages.warning(request, "Syllabus is already submitted or approved.")
        return redirect("academics:teacher_syllabus_hub")
    if request.method == "POST":
        syllabus.status = CourseSyllabus.Status.PENDING
        syllabus.submitted_at = timezone.now()
        syllabus.save()
        messages.success(request, "Syllabus submitted for approval.")
        return redirect("academics:teacher_syllabus_hub")
    return redirect("academics:teacher_syllabus_hub")


@login_required
def syllabus_preview(request, subject_assignment_id: int):
    """Preview syllabus as student/dean (read-only, optional watermark)."""
    sa = get_object_or_404(
        SubjectAssignment.objects.select_related("classroom", "subject", "term", "academic_year"),
        pk=subject_assignment_id,
    )
    syllabus = get_object_or_404(CourseSyllabus, subject_assignment=sa)
    # Allow: owner teacher, or any effective approver (for dean view)
    assignments_qs = _get_teacher_assignments(request.user)
    from apps.accounts.delegation import can_user_approve_for_workflow, WORKFLOW_SYLLABUS_APPROVAL
    is_owner = assignments_qs and assignments_qs.filter(subject_assignment=sa).exists()
    is_approver = can_user_approve_for_workflow(request.user, WORKFLOW_SYLLABUS_APPROVAL)
    if not (is_owner or is_approver):
        return HttpResponseForbidden("You cannot view this syllabus.")
    return render(request, "academics/syllabus_preview.html", {
        "syllabus": syllabus,
        "subject_assignment": sa,
    })


@login_required
def syllabus_approval_queue(request):
    """List syllabi pending approval for current user (effective approver: role or delegate)."""
    from apps.accounts.delegation import get_effective_approvers, WORKFLOW_SYLLABUS_APPROVAL
    approver_ids = [u.pk for u in get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL)]
    if request.user.pk not in approver_ids:
        return HttpResponseForbidden("You are not an approver for syllabi.")
    pending = (
        CourseSyllabus.objects.filter(status=CourseSyllabus.Status.PENDING)
        .select_related(
            "subject_assignment",
            "subject_assignment__classroom",
            "subject_assignment__subject",
            "subject_assignment__term",
            "subject_assignment__academic_year",
        )
        .order_by("submitted_at")
    )
    return render(request, "academics/syllabus_approval_queue.html", {"pending": pending})


@login_required
def syllabus_approve(request, subject_assignment_id: int):
    """Approve a syllabus (effective approver). Log delegation action if acting as delegate."""
    from apps.accounts.delegation import (
        get_effective_approvers,
        get_active_delegation_for_delegate,
        log_delegation_action,
        WORKFLOW_SYLLABUS_APPROVAL,
    )
    sa = get_object_or_404(SubjectAssignment, pk=subject_assignment_id)
    syllabus = get_object_or_404(CourseSyllabus, subject_assignment=sa)
    if syllabus.status != CourseSyllabus.Status.PENDING:
        messages.warning(request, "Syllabus is not pending.")
        return redirect("academics:syllabus_approval_queue")
    approver_ids = [u.pk for u in get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL)]
    if request.user.pk not in approver_ids:
        return HttpResponseForbidden("You are not an approver for syllabi.")
    if request.method == "POST":
        syllabus.status = CourseSyllabus.Status.APPROVED
        syllabus.reviewed_at = timezone.now()
        syllabus.reviewed_by = request.user
        syllabus.reviewer_notes = request.POST.get("notes", "").strip()
        syllabus.save()
        delegation = get_active_delegation_for_delegate(request.user)
        if delegation:
            log_delegation_action(
                delegation,
                request.user,
                "syllabus_approved",
                object_repr=str(syllabus),
                object_id=syllabus.pk,
                metadata={"subject_assignment_id": sa.pk},
            )
        # Award badge to teacher (e.g. Syllabus Master)
        try:
            from apps.people.badge_services import create_teacher_badge_for_syllabus_approval
            create_teacher_badge_for_syllabus_approval(syllabus)
        except Exception:
            pass
        # Sync to Document Library (portal syllabus feature)
        try:
            from apps.portal.models import PortalFeatureItem
            preview_url = request.build_absolute_uri(
                reverse("academics:syllabus_preview", args=[sa.pk])
            )
            title = f"{sa.subject.name} – {sa.classroom.name} ({sa.term.label})"
            if syllabus.portal_item_id:
                item = syllabus.portal_item
                item.title = title
                item.link = preview_url
                item.is_active = True
                item.save()
            else:
                item = PortalFeatureItem.objects.create(
                    feature=PortalFeatureItem.Feature.SYLLABUS,
                    title=title,
                    description="Approved course syllabus.",
                    link=preview_url,
                    is_active=True,
                    created_by=request.user,
                )
                syllabus.portal_item = item
                syllabus.save(update_fields=["portal_item"])
        except Exception:
            pass  # Don't fail approval if sync fails
        messages.success(request, "Syllabus approved.")
        return redirect("academics:syllabus_approval_queue")
    return redirect("academics:syllabus_approval_queue")


@login_required
def syllabus_reject(request, subject_assignment_id: int):
    """Send syllabus back to teacher (Needs revision). Log delegation action if delegate."""
    from apps.accounts.delegation import (
        get_effective_approvers,
        get_active_delegation_for_delegate,
        log_delegation_action,
        WORKFLOW_SYLLABUS_APPROVAL,
    )
    sa = get_object_or_404(SubjectAssignment, pk=subject_assignment_id)
    syllabus = get_object_or_404(CourseSyllabus, subject_assignment=sa)
    if syllabus.status != CourseSyllabus.Status.PENDING:
        messages.warning(request, "Syllabus is not pending.")
        return redirect("academics:syllabus_approval_queue")
    approver_ids = [u.pk for u in get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL)]
    if request.user.pk not in approver_ids:
        return HttpResponseForbidden("You are not an approver for syllabi.")
    if request.method == "POST":
        syllabus.status = CourseSyllabus.Status.NEEDS_REVISION
        syllabus.reviewed_at = timezone.now()
        syllabus.reviewed_by = request.user
        syllabus.reviewer_notes = request.POST.get("notes", "").strip()
        syllabus.save()
        delegation = get_active_delegation_for_delegate(request.user)
        if delegation:
            log_delegation_action(
                delegation,
                request.user,
                "syllabus_rejected",
                object_repr=str(syllabus),
                object_id=syllabus.pk,
                metadata={"subject_assignment_id": sa.pk},
            )
        messages.success(request, "Syllabus returned for revision.")
        return redirect("academics:syllabus_approval_queue")
    return redirect("academics:syllabus_approval_queue")


@login_required
def syllabus_clone(request, subject_assignment_id: int):
    """Clone syllabus from one SubjectAssignment to another (e.g. Form 3A → 3B). Target selection via GET/POST."""
    source_sa = get_object_or_404(SubjectAssignment, pk=subject_assignment_id)
    assignments_qs = _get_teacher_assignments(request.user)
    if not assignments_qs or not assignments_qs.filter(subject_assignment=source_sa).exists():
        return HttpResponseForbidden("You are not assigned to this class/subject.")
    source_syllabus = get_object_or_404(CourseSyllabus, subject_assignment=source_sa)
    # Targets: same year/term/subject, teacher assigned, no syllabus yet
    my_sa_ids = set(assignments_qs.values_list("subject_assignment_id", flat=True))
    existing_sa_ids = set(
        CourseSyllabus.objects.filter(subject_assignment__in=my_sa_ids).values_list("subject_assignment_id", flat=True)
    )
    candidate_ids = my_sa_ids - existing_sa_ids - {source_sa.pk}
    target_assignments = list(
        SubjectAssignment.objects.filter(pk__in=candidate_ids)
        .filter(academic_year=source_sa.academic_year, term=source_sa.term, subject=source_sa.subject)
        .select_related("classroom", "subject", "term")
    )
    target_sa_ids = {t.pk for t in target_assignments}
    if request.method == "POST":
        target_id = request.POST.get("target_assignment")
        if target_id:
            target_sa = get_object_or_404(SubjectAssignment, pk=int(target_id))
            if target_sa.pk not in target_sa_ids:
                return HttpResponseForbidden("Invalid target.")
            CourseSyllabus.objects.create(
                subject_assignment=target_sa,
                status=CourseSyllabus.Status.DRAFT,
                builder_data=dict(source_syllabus.builder_data),
                created_by=request.user,
            )
            if source_syllabus.uploaded_file:
                # Copy file reference not file content for simplicity; optional: copy file
                pass
            messages.success(request, f"Syllabus cloned to {target_sa.classroom}.")
            return redirect("academics:teacher_syllabus_hub")
    return render(request, "academics/syllabus_clone.html", {
        "source_syllabus": source_syllabus,
        "source_assignment": source_sa,
        "target_assignments": target_assignments,
    })
