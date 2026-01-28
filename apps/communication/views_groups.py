"""
Views for message thread/group management.
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.core.paginator import Paginator

from apps.communication.models import MessageThread, ThreadMessage, ThreadReadState
from apps.communication.forms_groups import MessageThreadCreateForm, MessageThreadUpdateForm
from apps.accounts.decorators import role_required
from apps.accounts.models import User
from apps.people.models import TeacherProfile
from apps.academics.models import Department


@login_required
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP)
def group_list(request: HttpRequest):
    """List all groups/threads user is a member of or can access."""
    user = request.user
    
    # Get threads user is a member of
    my_threads = MessageThread.objects.filter(
        members=user,
        is_archived=False
    ).annotate(
        message_count=Count('messages'),
        unread_count=Count('messages', filter=Q(
            messages__created_at__gt=timezone.now() - timezone.timedelta(days=30)
        ))
    ).order_by('-last_message_at', '-updated_at')
    
    # Get department threads if user is a teacher
    department_threads = []
    if hasattr(user, 'teacher_profile') and user.teacher_profile.department:
        department_threads = MessageThread.objects.filter(
            scope=MessageThread.Scope.DEPARTMENT,
            department=user.teacher_profile.department,
            is_archived=False
        ).exclude(id__in=my_threads.values_list('id', flat=True))
    
    # Get threads user created
    created_threads = MessageThread.objects.filter(
        created_by=user,
        is_archived=False
    ).exclude(id__in=my_threads.values_list('id', flat=True))
    
    context = {
        'my_threads': my_threads,
        'department_threads': department_threads,
        'created_threads': created_threads,
        'user_department': getattr(user.teacher_profile, 'department', None) if hasattr(user, 'teacher_profile') else None,
    }
    return render(request, 'communication/group_list.html', context)


@login_required
@role_required(User.Role.TEACHER, User.Role.ADMIN, User.Role.LEADERSHIP)
def group_create(request: HttpRequest):
    """Create a new message thread/group."""
    if request.method == 'POST':
        form = MessageThreadCreateForm(request.POST, user=request.user)
        if form.is_valid():
            thread = form.save(commit=False)
            thread.created_by = request.user
            thread.save()
            form.save_m2m()  # Save members
            
            # Auto-add creator if not in members
            if request.user not in thread.members.all():
                thread.members.add(request.user)
            
            messages.success(request, f'Group "{thread.title}" created successfully.')
            return redirect('communication:group_detail', thread_id=thread.id)
    else:
        form = MessageThreadCreateForm(user=request.user)
    
    return render(request, 'communication/group_create.html', {'form': form})


@login_required
def group_detail(request: HttpRequest, thread_id: int):
    """View and participate in a message thread."""
    thread = get_object_or_404(MessageThread, id=thread_id)
    
    # Check access
    if request.user not in thread.members.all() and not request.user.is_staff:
        return HttpResponseForbidden("You don't have access to this group.")
    
    # Get messages
    thread_messages = thread.messages.filter(is_deleted=False).order_by('created_at')
    
    # Mark as read
    read_state, _ = ThreadReadState.objects.get_or_create(
        thread=thread,
        user=request.user
    )
    read_state.last_read_at = timezone.now()
    read_state.save()
    
    # Handle new message
    if request.method == 'POST' and 'message' in request.POST:
        content = request.POST.get('message', '').strip()
        if content:
            ThreadMessage.objects.create(
                thread=thread,
                author=request.user,
                content=content
            )
            thread.touch_last_message()
            messages.success(request, 'Message sent.')
            return redirect('communication:group_detail', thread_id=thread.id)
    
    context = {
        'thread': thread,
        'messages': thread_messages,
        'is_member': request.user in thread.members.all(),
        'can_manage': (
            request.user == thread.created_by or
            request.user.is_staff or
            (hasattr(request.user, 'teacher_profile') and
             request.user.teacher_profile.department == thread.department and
             thread.scope == MessageThread.Scope.DEPARTMENT)
        ),
    }
    return render(request, 'communication/group_detail.html', context)


@login_required
def group_manage(request: HttpRequest, thread_id: int):
    """Manage group members and settings."""
    thread = get_object_or_404(MessageThread, id=thread_id)
    
    # Check permissions
    can_manage = (
        request.user == thread.created_by or
        request.user.is_staff or
        (hasattr(request.user, 'teacher_profile') and
         request.user.teacher_profile.department == thread.department and
         thread.scope == MessageThread.Scope.DEPARTMENT)
    )
    
    if not can_manage:
        return HttpResponseForbidden("You don't have permission to manage this group.")
    
    if request.method == 'POST':
        form = MessageThreadUpdateForm(request.POST, instance=thread, user=request.user)
        if form.is_valid():
            form.save()
            form.save_m2m()  # Save members
            messages.success(request, 'Group updated successfully.')
            return redirect('communication:group_detail', thread_id=thread.id)
    else:
        form = MessageThreadUpdateForm(instance=thread, user=request.user)
    
    return render(request, 'communication/group_manage.html', {
        'thread': thread,
        'form': form,
    })


@login_required
def group_join(request: HttpRequest, thread_id: int):
    """Join a group/thread."""
    thread = get_object_or_404(MessageThread, id=thread_id)
    
    # Check if user can join
    if thread.scope == MessageThread.Scope.DEPARTMENT:
        if hasattr(request.user, 'teacher_profile'):
            if request.user.teacher_profile.department != thread.department:
                return HttpResponseForbidden("You can only join groups for your department.")
        else:
            return HttpResponseForbidden("Only teachers can join department groups.")
    
    if request.user not in thread.members.all():
        thread.members.add(request.user)
        messages.success(request, f'You joined "{thread.title}".')
    else:
        messages.info(request, 'You are already a member of this group.')
    
    return redirect('communication:group_detail', thread_id=thread.id)


@login_required
def group_leave(request: HttpRequest, thread_id: int):
    """Leave a group/thread."""
    thread = get_object_or_404(MessageThread, id=thread_id)
    
    if request.user in thread.members.all():
        thread.members.remove(request.user)
        messages.success(request, f'You left "{thread.title}".')
    else:
        messages.info(request, 'You are not a member of this group.')
    
    return redirect('communication:group_list')
