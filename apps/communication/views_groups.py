"""
Views for message thread/group management.
"""

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden
from django.db.models import Q, Count
from django.utils import timezone

from apps.communication.models import MessageThread, ThreadMessage, ThreadReadState
from apps.communication.forms_groups import (
    MessageThreadCreateForm,
    MessageThreadUpdateForm,
)
from apps.accounts.models import User


GROUP_MESSAGING_ROLES = {
    User.Role.TEACHER,
    User.Role.ADMIN,
    User.Role.LEADERSHIP,
    User.Role.IT_ADMIN,
    User.Role.PRINCIPAL,
    User.Role.VICE_PRINCIPAL,
    User.Role.DEAN,
    User.Role.PROPRIETOR,
    User.Role.SECRETARY,
    User.Role.COMMS_STAFF,
}


def _can_access_group_messaging(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = getattr(user, "role", None)
    if role in (User.Role.PARENT, User.Role.STUDENT):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    if role in GROUP_MESSAGING_ROLES:
        return True
    has_perm = getattr(user, "has_feature_permission", None)
    if callable(has_perm):
        return bool(
            has_perm("communication.manage") or has_perm("module.communication.write")
        )
    return False


def _matches_audience_role(user, audience_role: str) -> bool:
    if not audience_role:
        return True
    role = (getattr(user, "role", "") or "").upper()
    audience = (audience_role or "").upper()
    if audience == "STAFF":
        return role in {
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "HOD",
            "DEPT_LEAD",
            "SECRETARY",
            "COMMS_STAFF",
            "IT_ADMIN",
            "BURSAR",
            "ACCOUNTANT",
            "FINANCE_STAFF",
            "ACADEMICS_STAFF",
            "PROPRIETOR",
            "TEACHER",
        } or bool(getattr(user, "is_staff", False))
    return role == audience


def _thread_queryset_for_request(request: HttpRequest):
    queryset = MessageThread.objects.all()
    school = getattr(request, "school", None)
    if school is not None:
        queryset = queryset.filter(school=school)
    return queryset


@login_required
def group_list(request: HttpRequest):
    """List all groups/threads user is a member of or can access."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to access message groups."
        )
    user = request.user
    thread_queryset = _thread_queryset_for_request(request)

    # Get threads user is a member of
    my_threads = (
        thread_queryset.filter(members=user, is_archived=False)
        .annotate(
            message_count=Count("messages"),
            unread_count=Count(
                "messages",
                filter=Q(
                    messages__created_at__gt=timezone.now()
                    - timezone.timedelta(days=30)
                ),
            ),
        )
        .order_by("-last_message_at", "-updated_at")
    )

    # Get department threads if user is a teacher
    department_threads = []
    if hasattr(user, "teacher_profile") and user.teacher_profile.department:
        department_threads = thread_queryset.filter(
            scope=MessageThread.Scope.DEPARTMENT,
            department=user.teacher_profile.department,
            is_archived=False,
        ).exclude(id__in=my_threads.values_list("id", flat=True))

    # Get threads user created
    created_threads = thread_queryset.filter(
        created_by=user, is_archived=False
    ).exclude(id__in=my_threads.values_list("id", flat=True))

    context = {
        "my_threads": my_threads,
        "department_threads": department_threads,
        "created_threads": created_threads,
        "user_department": getattr(user.teacher_profile, "department", None)
        if hasattr(user, "teacher_profile")
        else None,
    }
    return render(request, "communication/group_list.html", context)


@login_required
def group_create(request: HttpRequest):
    """Create a new message thread/group."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to create message groups."
        )
    school = getattr(request, "school", None)
    if request.method == "POST":
        form = MessageThreadCreateForm(request.POST, user=request.user, school=school)
        if form.is_valid():
            thread = form.save(commit=False)
            thread.created_by = request.user
            if school is not None:
                thread.school = school
            thread.save()
            form.save_m2m()  # Save members

            # Auto-add creator if not in members
            if request.user not in thread.members.all():
                thread.members.add(request.user)

            messages.success(request, f'Group "{thread.title}" created successfully.')
            return redirect("communication:group_detail", thread_id=thread.id)
    else:
        form = MessageThreadCreateForm(user=request.user, school=school)

    return render(request, "communication/group_create.html", {"form": form})


@login_required
def group_detail(request: HttpRequest, thread_id: int):
    """View and participate in a message thread."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden("You don't have permission to access this group.")
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)

    is_member = thread.members.filter(id=request.user.id).exists()
    can_view = (
        is_member
        or request.user.is_staff
        or request.user.is_superuser
        or request.user == thread.created_by
    )

    # Check access
    if not can_view:
        return HttpResponseForbidden("You don't have access to this group.")

    # Get messages
    thread_messages = thread.messages.filter(is_deleted=False).order_by("created_at")

    # Mark as read
    read_state, _ = ThreadReadState.objects.get_or_create(
        thread=thread, user=request.user
    )
    read_state.last_read_at = timezone.now()
    read_state.save()

    # Handle new message
    if request.method == "POST" and "message" in request.POST:
        if not is_member:
            return HttpResponseForbidden("Join this group before sending messages.")
        if thread.is_archived:
            return HttpResponseForbidden(
                "This group is archived and cannot receive new messages."
            )
        content = request.POST.get("message", "").strip()
        if content:
            locale_target = ""
            try:
                from django.utils import translation

                lang = translation.get_language() or "en"
                if thread.school_id:
                    from apps.schools.models import School

                    sch = (
                        School.objects.filter(pk=thread.school_id)
                        .select_related("default_region")
                        .first()
                    )
                    if (
                        sch
                        and sch.default_region_id
                        and getattr(sch.default_region, "default_language", None)
                    ):
                        lang = sch.default_region.default_language or lang
                locale_target = str(lang)[:10]
            except Exception:
                locale_target = ""
            ThreadMessage.objects.create(
                thread=thread,
                author=request.user,
                content=content,
                locale_target=locale_target or "",
            )
            thread.touch_last_message()
            messages.success(request, _("Message sent."))
            return redirect("communication:group_detail", thread_id=thread.id)

    context = {
        "thread": thread,
        "messages": thread_messages,
        "is_member": is_member,
        "can_manage": (
            request.user == thread.created_by
            or request.user.is_staff
            or (
                hasattr(request.user, "teacher_profile")
                and request.user.teacher_profile.department == thread.department
                and thread.scope == MessageThread.Scope.DEPARTMENT
            )
        ),
    }
    return render(request, "communication/group_detail.html", context)


@login_required
def group_manage(request: HttpRequest, thread_id: int):
    """Manage group members and settings."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to manage message groups."
        )
    school = getattr(request, "school", None)
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)

    # Check permissions
    can_manage = (
        request.user == thread.created_by
        or request.user.is_staff
        or (
            hasattr(request.user, "teacher_profile")
            and request.user.teacher_profile.department == thread.department
            and thread.scope == MessageThread.Scope.DEPARTMENT
        )
    )

    if not can_manage:
        return HttpResponseForbidden("You don't have permission to manage this group.")

    if request.method == "POST":
        form = MessageThreadUpdateForm(
            request.POST, instance=thread, user=request.user, school=school
        )
        if form.is_valid():
            form.save()
            form.save_m2m()  # Save members
            messages.success(request, _("Group updated successfully."))
            return redirect("communication:group_detail", thread_id=thread.id)
    else:
        form = MessageThreadUpdateForm(
            instance=thread, user=request.user, school=school
        )

    return render(
        request,
        "communication/group_manage.html",
        {
            "thread": thread,
            "form": form,
        },
    )


@login_required
def group_join(request: HttpRequest, thread_id: int):
    """Join a group/thread."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to join message groups."
        )
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)
    if thread.is_archived:
        return HttpResponseForbidden("This group is archived.")
    if not _matches_audience_role(request.user, thread.audience_role):
        return HttpResponseForbidden("You don't match the audience for this group.")

    # Check if user can join
    if thread.scope == MessageThread.Scope.DEPARTMENT:
        if request.user.is_staff or request.user.is_superuser:
            pass
        elif hasattr(request.user, "teacher_profile"):
            if request.user.teacher_profile.department != thread.department:
                return HttpResponseForbidden(
                    "You can only join groups for your department."
                )
        else:
            return HttpResponseForbidden("Only teachers can join department groups.")

    if request.user not in thread.members.all():
        thread.members.add(request.user)
        messages.success(request, f'You joined "{thread.title}".')
    else:
        messages.info(request, _("You are already a member of this group."))

    return redirect("communication:group_detail", thread_id=thread.id)


@login_required
def group_leave(request: HttpRequest, thread_id: int):
    """Leave a group/thread."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to leave message groups."
        )
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)

    if request.user in thread.members.all():
        thread.members.remove(request.user)
        messages.success(request, f'You left "{thread.title}".')
    else:
        messages.info(request, _("You are not a member of this group."))

    return redirect("communication:group_list")
