"""
Views for announcement management with department support.
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden
from django.db.models import Q
from django.utils import timezone

from apps.communication.models import Announcement, ClassAnnouncement
from apps.communication.forms_announcements import AnnouncementCreateForm, ClassAnnouncementForm
from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.people.models import TeacherProfile
from apps.academics.models import Department


@login_required
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP)
def announcement_create(request: HttpRequest):
    """Create a new announcement with optional department targeting."""
    if request.method == 'POST':
        form = AnnouncementCreateForm(request.POST, user=request.user)
        if form.is_valid():
            announcement = form.save()
            messages.success(request, 'Announcement created successfully.')
            
            # If department was selected, show info
            if form.cleaned_data.get('send_to_department'):
                messages.info(request, f'Announcement also sent to {form.cleaned_data["send_to_department"].name} department.')
            
            return redirect('communication:announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementCreateForm(user=request.user)
    
    return render(request, 'communication/announcement_create.html', {'form': form})


@login_required
def announcement_detail(request: HttpRequest, announcement_id: int):
    """View announcement details."""
    announcement = get_object_or_404(Announcement, id=announcement_id)
    
    # Check if user should see this announcement
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
            department=request.user.teacher_profile.department,
            title=announcement.title,
            created_at__date=announcement.created_at.date()
        ).first()
    
    return render(request, 'communication/announcement_detail.html', {
        'announcement': announcement,
        'department_announcement': department_announcement,
        'can_edit': request.user == announcement.created_by or request.user.is_staff,
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
        form = ClassAnnouncementForm(request.POST, user=user)
        if form.is_valid():
            announcement = form.save()
            messages.success(request, f'Department announcement created for {announcement.department or announcement.classroom}.')
            return redirect('portal:teacher_dashboard')
    else:
        initial = {}
        if user_department:
            initial['department'] = user_department
        form = ClassAnnouncementForm(user=user, initial=initial)
    
    return render(request, 'communication/department_announcement_create.html', {
        'form': form,
        'user_department': user_department,
    })


@login_required
def announcement_edit(request: HttpRequest, announcement_id: int):
    """Edit an existing announcement."""
    announcement = get_object_or_404(Announcement, id=announcement_id)
    
    # Check permissions
    if request.user != announcement.created_by and not request.user.is_staff:
        return HttpResponseForbidden("You can only edit your own announcements.")
    
    if request.method == 'POST':
        form = AnnouncementCreateForm(request.POST, instance=announcement, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated successfully.')
            return redirect('communication:announcement_detail', announcement_id=announcement.id)
    else:
        form = AnnouncementCreateForm(instance=announcement, user=request.user)
    
    return render(request, 'communication/announcement_edit.html', {
        'form': form,
        'announcement': announcement,
    })
