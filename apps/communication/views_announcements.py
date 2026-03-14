"""
Views for announcement management with tiered permissions:

- School-wide announcements: admins/leadership only (or submit-for-approval when enabled).
- Class announcements: teachers can create for their classes only.
- Department announcements: HOD/leadership only (existing).
- Optional: approval workflow and audit logging.
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from apps.communication.models import (
    Announcement,
    AnnouncementAuditLog,
    ClassAnnouncement,
    log_announcement_audit,
)
from apps.communication.forms_announcements import (
    AnnouncementCreateForm,
    ClassAnnouncementForm,
    SUBMIT_ACTION_PUBLISH,
    SUBMIT_ACTION_DRAFT,
    SUBMIT_ACTION_SUBMIT_FOR_APPROVAL,
)
from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.people.models import TeacherProfile
from apps.platform_runtime.helpers import get_effective_flags
from apps.siteconfig.models_support import default_announcement_submit_for_approval_roles

ANNOUNCEMENT_FLAG_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    ObjectDoesNotExist,
    TypeError,
    ValueError,
)


def _announcement_school(request: HttpRequest):
    return getattr(request, "school", None)


def _announcement_queryset(request: HttpRequest):
    school = _announcement_school(request)
    if school is None:
        return Announcement.objects.none()
    return Announcement.objects.filter(school=school)


def _class_announcement_queryset(request: HttpRequest):
    school = _announcement_school(request)
    if school is None:
        return ClassAnnouncement.objects.none()
    return ClassAnnouncement.objects.filter(school=school)


def _get_announcement_feature_flags(request=None):
    """Get announcement-related flags from site settings (backend_feature_flags)."""
    try:
        flags = get_effective_flags(request)
        policy_roles = []
        school = getattr(request, "school", None) if request is not None else None
        if school is not None:
            try:
                from apps.policies.policy_registry import get_effective_policy

                approval_policy = ((get_effective_policy(school).get("communication") or {}).get("message_approval") or {})
                policy_roles = (
                    approval_policy.get("announcement_submit_for_approval_roles")
                    or approval_policy.get("submit_for_approval_roles")
                    or []
                )
            except ANNOUNCEMENT_FLAG_FAILURES:
                policy_roles = []
        return {
            "allow_submit_for_approval": flags.get("announcement_allow_submit_for_approval", False),
            "submit_for_approval_roles": (
                flags.get("announcement_submit_for_approval_roles")
                or policy_roles
                or default_announcement_submit_for_approval_roles()
            ),
        }
    except ANNOUNCEMENT_FLAG_FAILURES:
        return {
            "allow_submit_for_approval": False,
            "submit_for_approval_roles": default_announcement_submit_for_approval_roles(),
        }


def _can_create_school_wide_announcement(user) -> bool:
    """
    Principals, admins, and designated leadership can publish school-wide announcements directly.
    """
    if not user or not getattr(user, "is_authenticated", True):
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = getattr(user, "role", None)
    return role in (
        User.Role.ADMIN,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.PROPRIETOR,
        User.Role.DEAN,
        User.Role.CENSOR,
        User.Role.COMMS_STAFF,
    )


def _can_submit_for_approval(user, request=None) -> bool:
    """When site flag is on, teachers/comms can submit school-wide announcements for approval."""
    if not user or not getattr(user, "is_authenticated", True):
        return False
    flags = _get_announcement_feature_flags(request)
    if not flags.get("allow_submit_for_approval"):
        return False
    roles = [r.upper() for r in (flags.get("submit_for_approval_roles") or [])]
    role = (getattr(user, "role", "") or "").upper()
    return role in roles


def _can_access_school_wide_announcement_create(user, request=None) -> bool:
    """Can open the create form: either publish directly or submit for approval."""
    return _can_create_school_wide_announcement(user) or _can_submit_for_approval(user, request)


def _can_approve_announcements(user) -> bool:
    """Can approve pending announcements (same as can publish)."""
    return _can_create_school_wide_announcement(user)


@login_required
def announcement_create(request: HttpRequest):
    """
    Create a school-wide announcement. Allowed for admins/leadership (publish or draft)
    or, when optional workflow is enabled, teachers/comms can submit for approval or save as draft.
    """
    if not (_can_create_school_wide_announcement(request.user) or _can_submit_for_approval(request.user, request)):
        return HttpResponseForbidden(
            "You cannot create school-wide announcements. "
            "Use Class announcement or Department announcement (if HOD) from your dashboard."
        )
    school = _announcement_school(request)
    if school is None:
        return HttpResponseForbidden("School context required.")
    can_publish = _can_create_school_wide_announcement(request.user)
    can_submit = _can_submit_for_approval(request.user, request)
    flags = _get_announcement_feature_flags(request)

    if request.method == 'POST':
        form = AnnouncementCreateForm(request.POST, user=request.user, school=school)
        submit_action = (request.POST.get("submit_action") or SUBMIT_ACTION_PUBLISH).strip()
        if submit_action not in (SUBMIT_ACTION_PUBLISH, SUBMIT_ACTION_DRAFT, SUBMIT_ACTION_SUBMIT_FOR_APPROVAL):
            submit_action = SUBMIT_ACTION_PUBLISH
        if not can_publish and submit_action == SUBMIT_ACTION_PUBLISH:
            submit_action = SUBMIT_ACTION_SUBMIT_FOR_APPROVAL if can_submit else SUBMIT_ACTION_DRAFT
        if submit_action == SUBMIT_ACTION_SUBMIT_FOR_APPROVAL and not can_submit:
            submit_action = SUBMIT_ACTION_DRAFT

        if form.is_valid():
            announcement = form.save(submit_action=submit_action)
            if submit_action == SUBMIT_ACTION_PUBLISH:
                messages.success(request, 'Announcement published successfully.')
            elif submit_action == SUBMIT_ACTION_SUBMIT_FOR_APPROVAL:
                messages.success(request, 'Announcement submitted for approval. It will be visible after an administrator approves it.')
            else:
                messages.success(request, 'Draft saved. You can edit and publish or submit for approval later.')
            if form.cleaned_data.get('send_to_department'):
                messages.info(request, f'Announcement also sent to {form.cleaned_data["send_to_department"].name} department.')
            return redirect('communication:announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementCreateForm(user=request.user, school=school)

    return render(request, 'communication/announcement_create.html', {
        'form': form,
        'can_publish': can_publish,
        'can_submit_for_approval': can_submit,
        'allow_submit_for_approval': flags.get("allow_submit_for_approval", False),
    })


@login_required
def announcement_detail(request: HttpRequest, announcement_id: int):
    """View announcement details. Only published announcements are visible to audience."""
    announcement = get_object_or_404(_announcement_queryset(request), id=announcement_id)
    # Creator, approver, or staff can see draft/pending; others only published
    can_see_unpublished = (
        request.user.is_staff
        or request.user == announcement.created_by
        or request.user == announcement.approved_by
    )
    if announcement.status != Announcement.Status.PUBLISHED and not can_see_unpublished:
        return HttpResponseForbidden("This announcement is not yet published.")

    user_role = getattr(request.user, 'role', '').upper()
    audience = announcement.audience
    can_view = (
        request.user.is_staff or
        audience == 'all' or
        (user_role == 'STUDENT' and audience == 'students') or
        (user_role == 'PARENT' and audience == 'all_parents') or
        (user_role == 'TEACHER' and audience in ['teachers', 'staff']) or
        (user_role in ['ADMIN', 'LEADERSHIP'] and audience == 'staff')
    )
    if not can_view:
        return HttpResponseForbidden("You don't have permission to view this announcement.")
    
    # Get related department announcement if exists
    department_announcement = None
    if hasattr(request.user, 'teacher_profile') and request.user.teacher_profile.department:
        department_announcement = ClassAnnouncement.objects.filter(
            school=_announcement_school(request),
            department=request.user.teacher_profile.department,
            title=announcement.title,
            created_at__date=announcement.created_at.date()
        ).first()
    
    can_approve = _can_approve_announcements(request.user) and announcement.status == Announcement.Status.PENDING_APPROVAL
    return render(request, 'communication/announcement_detail.html', {
        'announcement': announcement,
        'department_announcement': department_announcement,
        'can_edit': request.user == announcement.created_by or request.user.is_staff or _can_create_school_wide_announcement(request.user),
        'can_approve': can_approve,
    })


def _can_create_department_announcement(user) -> bool:
    """Only HOD and leadership (and admin) can create department announcements; other teachers only get notified."""
    if user.is_staff or user.is_superuser:
        return True
    role = getattr(user, "role", None)
    return role in (
        User.Role.HOD,
        User.Role.LEADERSHIP,
        User.Role.ADMIN,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
    )


@login_required
def department_announcement_create(request: HttpRequest):
    """Create a department-specific announcement. Only HOD and leadership can create; other teachers see list/feed only."""
    user = request.user
    school = _announcement_school(request)
    if school is None:
        return HttpResponseForbidden("School context required.")
    if not _can_create_department_announcement(user):
        return HttpResponseForbidden(
            "Only Heads of Department and leadership can create department announcements. You can view and receive them."
        )

    # Get user's department
    user_department = None
    try:
        if hasattr(user, "teacher_profile") and user.teacher_profile and getattr(user.teacher_profile, "department", None):
            user_department = user.teacher_profile.department
    except TeacherProfile.DoesNotExist:
        pass

    if not user_department and not user.is_staff:
        return HttpResponseForbidden("You must be assigned to a department to create department announcements.")
    
    if request.method == 'POST':
        form = ClassAnnouncementForm(request.POST, user=user, school=school)
        if form.is_valid():
            announcement = form.save()
            messages.success(request, f'Department announcement created for {announcement.department or announcement.classroom}.')
            return redirect('portal:teacher_dashboard')
    else:
        initial = {}
        if user_department:
            initial['department'] = user_department
        form = ClassAnnouncementForm(user=user, school=school, initial=initial)
    
    return render(request, 'communication/department_announcement_create.html', {
        'form': form,
        'user_department': user_department,
    })


@login_required
def announcement_edit(request: HttpRequest, announcement_id: int):
    """Edit an existing school-wide announcement. Creator or admins; audit logged."""
    announcement = get_object_or_404(_announcement_queryset(request), id=announcement_id)
    can_publish = _can_create_school_wide_announcement(request.user)
    if not can_publish and request.user != announcement.created_by and not request.user.is_staff:
        return HttpResponseForbidden("You can only edit your own announcements.")
    if request.user != announcement.created_by and not request.user.is_staff and not can_publish:
        return HttpResponseForbidden("You can only edit your own announcements.")
    if request.method == 'POST':
        form = AnnouncementCreateForm(request.POST, instance=announcement, user=request.user, school=_announcement_school(request))
        if form.is_valid():
            was_active = announcement.is_active
            form.save(submit_action=SUBMIT_ACTION_PUBLISH)
            if not form.instance.is_active and was_active:
                log_announcement_audit(announcement, request.user, AnnouncementAuditLog.Action.DEACTIVATED)
            messages.success(request, 'Announcement updated successfully.')
            return redirect('communication:announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementCreateForm(instance=announcement, user=request.user, school=_announcement_school(request))
    return render(request, 'communication/announcement_edit.html', {
        'form': form,
        'announcement': announcement,
    })


@login_required
def announcement_list_pending(request: HttpRequest):
    """List announcements pending approval. Only approvers can access."""
    if not _can_approve_announcements(request.user):
        return HttpResponseForbidden("You do not have permission to approve announcements.")
    if _announcement_school(request) is None:
        return HttpResponseForbidden("School context required.")
    pending = _announcement_queryset(request).filter(
        status=Announcement.Status.PENDING_APPROVAL,
        is_active=True,
    ).select_related("created_by").order_by("-created_at")
    return render(request, "communication/announcement_list_pending.html", {"pending_list": pending})


@login_required
@require_http_methods(["POST"])
@csrf_protect
def announcement_approve(request: HttpRequest, announcement_id: int):
    """Approve a pending announcement: set status to published, set approved_by/approved_at, log audit."""
    if not _can_approve_announcements(request.user):
        return HttpResponseForbidden("You do not have permission to approve announcements.")
    if _announcement_school(request) is None:
        return HttpResponseForbidden("School context required.")
    announcement = get_object_or_404(_announcement_queryset(request), id=announcement_id)
    if announcement.status != Announcement.Status.PENDING_APPROVAL:
        messages.warning(request, "This announcement is not pending approval.")
        return redirect("communication:announcement_detail", announcement_id=announcement.id)
    announcement.status = Announcement.Status.PUBLISHED
    announcement.approved_by = request.user
    announcement.approved_at = timezone.now()
    announcement.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log_announcement_audit(announcement, request.user, AnnouncementAuditLog.Action.APPROVED, notes="Approved for publication")
    messages.success(request, f"Announcement «{announcement.title}» has been approved and published.")
    return redirect("communication:announcement_list_pending")


@login_required
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP, User.Role.HOD)
def class_announcement_create(request: HttpRequest):
    """
    Create a class-level announcement. Teachers target specific classes
    (connected parents see these). Department-wide announcements are created
    via Department announcement (HOD/leadership only).
    """
    user = request.user
    school = _announcement_school(request)
    if school is None:
        return HttpResponseForbidden("School context required.")
    if request.method == 'POST':
        form = ClassAnnouncementForm(request.POST, user=user, school=school)
        if form.is_valid():
            announcement = form.save()
            messages.success(
                request,
                f'Class announcement created for {announcement.classroom or announcement.department}.'
            )
            return redirect('portal:teacher_dashboard_alias')
    else:
        form = ClassAnnouncementForm(user=user, school=school)
        # Teachers (non-HOD): make department optional so they can post to classroom only
        if not _can_create_department_announcement(user):
            form.fields['department'].required = False
    return render(request, 'communication/class_announcement_create.html', {
        'form': form,
    })
