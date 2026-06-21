"""
Views for message thread/group management.
"""

import logging
import re

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.shortcuts import render, redirect, get_object_or_404
from django.http import (
    HttpRequest,
    HttpResponseForbidden,
    JsonResponse,
    FileResponse,
    Http404,
)
from django.urls import reverse
from django.utils import timezone

from apps.communication.models import (
    MessageThread,
    ThreadMessage,
    ThreadMessageAttachment,
    ThreadMessageMention,
    ThreadMute,
    ThreadReadState,
)
from apps.communication.forms_groups import (
    MessageThreadCreateForm,
    MessageThreadUpdateForm,
)
from apps.accounts.models import User

logger = logging.getLogger(__name__)

#: Max attachment files accepted on a single group message (mirrors the 1:1
#: direct-thread cap in ``accounts.views._save_message_attachments``).
_THREAD_ATTACHMENT_MAX_FILES = 5

#: Max messages returned by one live-poll fetch (bounds the payload; a larger
#: backlog drains across successive polls). Mirrors the direct-thread limit.
_THREAD_LIVE_POLL_LIMIT = 50


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
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    queryset = MessageThread.objects.all()
    school = getattr(request, "school", None)
    if school is not None:
        queryset = queryset.filter(school=school)
    return queryset


def _attach_thread_unread_counts(threads, user) -> None:
    """Attach a read-state-correct ``unread_count`` to each thread (IM-4).

    The previous group_list annotation counted every message from the last 30
    days regardless of whether the user had read it — a misleading number that
    was, in any case, never rendered. This mirrors the hub's
    ``portal.services._serialize_thread`` logic: unread = non-deleted messages
    posted after the user's ``ThreadReadState.last_read_at`` (every message if
    the user has never opened the thread).
    """
    if not threads:
        return
    thread_ids = [t.id for t in threads]
    # tenant-isolation-allow: read-states-scoped-to-caller-and-the-passed-thread-set
    read_map = dict(
        ThreadReadState.objects.filter(
            thread_id__in=thread_ids, user=user
        ).values_list("thread_id", "last_read_at")
    )
    for t in threads:
        last_read_at = read_map.get(t.id)
        # tenant-isolation-allow: messages-scoped-to-the-callers-own-thread-set
        qs = ThreadMessage.objects.filter(thread_id=t.id, is_deleted=False)
        if last_read_at:
            qs = qs.filter(created_at__gt=last_read_at)
        t.unread_count = qs.count()


def _save_thread_attachments(message, files, uploader):
    """Validate + persist uploaded files as ``ThreadMessageAttachment`` rows (IM-5).

    The group-thread twin of ``accounts.views._save_message_attachments``: each
    file is checked with the shared KB-attachment validators (PDF / Office /
    image only) and a 10 MB cap, the count is bounded, and nothing here is fatal
    to the post — a rejected / unstorable file is collected into ``errors`` and
    surfaced to the user, never raised. Returns ``(saved_count, error_messages)``.
    """
    from apps.accounts.validators import (
        validate_kb_attachment_file,
        validate_file_size_10mb,
    )

    saved = 0
    errors = []
    for f in (files or [])[:_THREAD_ATTACHMENT_MAX_FILES]:
        if not f:
            continue
        name = getattr(f, "name", "") or "file"
        try:
            validate_file_size_10mb(f)
            validate_kb_attachment_file(f)
        except ValidationError as exc:
            errors.append("%s: %s" % (name, "; ".join(exc.messages)))
            continue
        try:
            ThreadMessageAttachment.objects.create(
                message=message,
                file=f,
                original_name=name[:255],
                content_type=(getattr(f, "content_type", "") or "")[:128],
                size_bytes=getattr(f, "size", 0) or 0,
                uploaded_by=uploader,
            )
            saved += 1
        except Exception:  # noqa: BLE001 — a storage hiccup never breaks the post
            logger.warning("thread attachment save failed", exc_info=False)
            errors.append("%s: %s" % (name, _("could not be saved")))
    return saved, errors


#: Matches an @handle token in message text: @ + 2-40 of [A-Za-z0-9._-].
_MENTION_TOKEN_RE = re.compile(r"@([A-Za-z0-9._\-]{2,40})")


def _member_mention_handles(member) -> set:
    """Handles an @token may use to address ``member`` (all lowercased)."""
    handles = set()
    uname = (getattr(member, "username", "") or "").lower()
    if uname:
        handles.add(uname)
        handles.add(uname.split("@", 1)[0])  # email local-part
    first = (getattr(member, "first_name", "") or "").lower()
    last = (getattr(member, "last_name", "") or "").lower()
    if first:
        handles.add(first)
    if first and last:
        handles.add(f"{first}.{last}")
        handles.add(f"{first}{last}")
    handles.discard("")
    return handles


def _resolve_and_record_mentions(message, thread, author) -> None:
    """Record @mentions of *thread members* in a freshly-posted message (IM-7).

    Tokens are matched against the thread's own members only (by username, email
    local-part, first name, or first.last), so a mention can never resolve to a
    non-member or a cross-tenant user, and the author can't @mention themselves.
    The mention rows drive a distinct, mute-piercing notification (see
    ``signals.notify_on_thread_message``) and the in-thread highlight. Best
    effort: never raises into the post path.
    """
    try:
        tokens = {t.lower() for t in _MENTION_TOKEN_RE.findall(message.content or "")}
    except Exception:  # noqa: BLE001 — a malformed body never breaks the post
        tokens = set()
    if not tokens:
        return
    for member in thread.members.exclude(pk=author.pk):
        if tokens & _member_mention_handles(member):
            try:
                # tenant-isolation-allow: mention-row-for-this-message-and-resolved-member
                ThreadMessageMention.objects.get_or_create(
                    message=message, user=member
                )
            except Exception:  # noqa: BLE001 — a mention write never breaks the post
                logger.warning("thread mention record failed", exc_info=False)


def _can_moderate_thread(user, thread) -> bool:
    """Whether ``user`` may moderate (delete others' messages in) ``thread``.

    Mirrors the ``can_manage`` test used by group_detail / group_manage: the
    thread creator, any staff member, or the lead of a department thread.
    """
    if user == thread.created_by or getattr(user, "is_staff", False):
        return True
    teacher_profile = getattr(user, "teacher_profile", None)
    return bool(
        teacher_profile
        and thread.scope == MessageThread.Scope.DEPARTMENT
        and teacher_profile.department_id == thread.department_id
    )


@login_required
def group_list(request: HttpRequest):
    """List all groups/threads user is a member of or can access."""
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden(
            "You don't have permission to access message groups."
        )
    user = request.user
    thread_queryset = _thread_queryset_for_request(request)

    # Get threads user is a member of. Evaluated to a list so we can attach a
    # read-state-correct unread count (IM-4) the template can render.
    my_threads = list(
        thread_queryset.filter(members=user, is_archived=False)
        .prefetch_related("members")
        .order_by("-last_message_at", "-updated_at")
    )
    my_thread_ids = [t.id for t in my_threads]
    _attach_thread_unread_counts(my_threads, user)

    # Get department threads if user is a teacher
    department_threads = []
    if hasattr(user, "teacher_profile") and user.teacher_profile.department:
        department_threads = list(
            thread_queryset.filter(
                scope=MessageThread.Scope.DEPARTMENT,
                department=user.teacher_profile.department,
                is_archived=False,
            )
            .exclude(id__in=my_thread_ids)
            .prefetch_related("members")
        )
        _attach_thread_unread_counts(department_threads, user)

    # Get threads user created
    created_threads = thread_queryset.filter(
        created_by=user, is_archived=False
    ).exclude(id__in=my_thread_ids)

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

    # Get messages (author + attachments prefetched for render).
    thread_messages = (
        thread.messages.filter(is_deleted=False)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("created_at")
    )

    # Mark as read
    read_state, _created = ThreadReadState.objects.get_or_create(
        thread=thread, user=request.user
    )
    read_state.last_read_at = timezone.now()
    read_state.save()

    # Handle new message (text and/or attachments — IM-5).
    if request.method == "POST" and "message" in request.POST:
        if not is_member:
            return HttpResponseForbidden("Join this group before sending messages.")
        if thread.is_archived:
            return HttpResponseForbidden(
                "This group is archived and cannot receive new messages."
            )
        content = request.POST.get("message", "").strip()
        attachment_files = request.FILES.getlist("attachments")
        if content or attachment_files:
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
            msg = ThreadMessage.objects.create(
                thread=thread,
                author=request.user,
                content=content,
                locale_target=locale_target or "",
            )
            if attachment_files:
                _saved, attach_errors = _save_thread_attachments(
                    msg, attachment_files, request.user
                )
                if attach_errors:
                    messages.warning(
                        request,
                        _("Some attachments were not added: %(errs)s")
                        % {"errs": "; ".join(attach_errors)},
                    )
            # Record @mentions before the request commits so the notification
            # signal's on_commit hook can see them (mute-piercing mention path).
            _resolve_and_record_mentions(msg, thread, request.user)
            thread.touch_last_message()
            messages.success(request, _("Message sent."))
            return redirect("communication:group_detail", thread_id=thread.id)

    can_manage = (
        request.user == thread.created_by
        or request.user.is_staff
        or (
            hasattr(request.user, "teacher_profile")
            and request.user.teacher_profile.department == thread.department
            and thread.scope == MessageThread.Scope.DEPARTMENT
        )
    )

    # Read receipts (IM-5): for the caller's OWN messages, how many other members
    # have opened the thread since the message was posted. Computed from each
    # member's ThreadReadState.last_read_at — the same signal the unread badge uses.
    message_list = list(thread_messages)
    member_ids = list(thread.members.values_list("id", flat=True))
    other_member_ids = [mid for mid in member_ids if mid != request.user.id]
    total_others = len(other_member_ids)
    # tenant-isolation-allow: read-states-scoped-to-this-fetched-school-scoped-thread
    read_at_map = dict(
        ThreadReadState.objects.filter(thread=thread)
        .exclude(user_id=request.user.id)
        .values_list("user_id", "last_read_at")
    )
    for m in message_list:
        if m.author_id == request.user.id and total_others:
            m.show_read_by = True
            m.read_by_total = total_others
            m.read_by_count = sum(
                1
                for mid in other_member_ids
                if read_at_map.get(mid) and read_at_map[mid] >= m.created_at
            )
        else:
            m.show_read_by = False

    # tenant-isolation-allow: mute-row-scoped-to-caller-and-this-fetched-thread
    is_muted = ThreadMute.objects.filter(
        thread=thread, user=request.user
    ).exists()

    context = {
        "thread": thread,
        "messages": message_list,
        "is_member": is_member,
        "can_manage": can_manage,
        "is_muted": is_muted,
        "current_user_id": request.user.id,
        "live_endpoint": reverse(
            "communication:group_messages_since", args=[thread.id]
        ),
        "typing_endpoint": reverse(
            "communication:group_typing", args=[thread.id]
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


@login_required
def group_messages_since(request: HttpRequest, thread_id: int):
    """JSON of group messages newer than ``?after`` for live delivery (IM-5).

    The group-thread twin of ``accounts.views.direct_thread_messages_since``: the
    client passes the highest message id it has rendered and this returns anything
    newer (with attachments), plus refreshed read-receipt counts for the caller's
    OWN messages so "read by" ticks up live. Viewing also stamps the caller's
    ThreadReadState, keeping the unread badge and others' receipts current.
    """
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
    if not can_view:
        return HttpResponseForbidden("You don't have access to this group.")

    try:
        after = int(request.GET.get("after") or 0)
    except (TypeError, ValueError):
        after = 0

    new_qs = (
        thread.messages.filter(is_deleted=False, id__gt=after)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("created_at")[:_THREAD_LIVE_POLL_LIMIT]
    )

    messages_payload = []
    for m in new_qs:
        author = m.author
        attachments = [
            {
                "name": att.original_name,
                "url": reverse(
                    "communication:group_attachment_download", args=[att.id]
                ),
            }
            for att in m.attachments.all()
        ]
        messages_payload.append(
            {
                "id": m.id,
                "mine": m.author_id == request.user.id,
                "author_name": (
                    (author.get_full_name() if author else "")
                    or getattr(author, "username", "")
                    or "Someone"
                ),
                "content": m.content or "",
                "created_at": m.created_at.isoformat(),
                "edited": bool(m.edited_at),
                "attachments": attachments,
            }
        )

    # Refresh read-receipt counts for the caller's most recent own messages so
    # the author sees "read by" tick up live. Excludes the caller's own read
    # state, so it reflects OTHER members opening the thread.
    member_ids = list(thread.members.values_list("id", flat=True))
    other_member_ids = [mid for mid in member_ids if mid != request.user.id]
    total_others = len(other_member_ids)
    receipts = []
    if total_others:
        # tenant-isolation-allow: read-states-scoped-to-this-fetched-school-scoped-thread
        read_at_map = dict(
            ThreadReadState.objects.filter(thread=thread)
            .exclude(user_id=request.user.id)
            .values_list("user_id", "last_read_at")
        )
        own_msgs = list(
            thread.messages.filter(is_deleted=False, author_id=request.user.id)
            .order_by("-id")
            .values_list("id", "created_at")[:_THREAD_LIVE_POLL_LIMIT]
        )
        for mid, created_at in own_msgs:
            read_by = sum(
                1
                for omid in other_member_ids
                if read_at_map.get(omid) and read_at_map[omid] >= created_at
            )
            receipts.append({"id": mid, "read_by": read_by, "total": total_others})

    # The viewer is live on the thread → keep their read state fresh.
    if is_member:
        read_state, _created = ThreadReadState.objects.get_or_create(
            thread=thread, user=request.user
        )
        read_state.last_read_at = timezone.now()
        read_state.save(update_fields=["last_read_at", "updated_at"])

    return JsonResponse({"messages": messages_payload, "receipts": receipts})


@login_required
def group_attachment_download(request: HttpRequest, attachment_id: int):
    """Serve a group-message attachment to thread members only (IM-5).

    Access is gated on membership of the attachment's parent thread. A staff
    member or the thread creator may also fetch it, but only within their own
    tenant (``request.school``); a superuser always may. A guessed id can't leak
    another group's — or another tenant's — file.
    """
    # tenant-isolation-allow: access-gated-below-on-parent-thread-membership-and-school
    attachment = get_object_or_404(
        ThreadMessageAttachment.objects.select_related("message__thread"),
        pk=attachment_id,
    )
    thread = attachment.message.thread
    school = getattr(request, "school", None)
    same_school = school is None or thread.school_id == getattr(school, "id", None)
    allowed = (
        thread.members.filter(id=request.user.id).exists()
        or request.user.is_superuser
        or (
            (request.user.is_staff or request.user == thread.created_by)
            and same_school
        )
    )
    if not allowed:
        return HttpResponseForbidden("You don't have access to this attachment.")

    try:
        handle = attachment.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("Attachment file is unavailable.")
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=attachment.original_name or "attachment",
    )
    if attachment.content_type:
        response["Content-Type"] = attachment.content_type
    return response


@login_required
def group_message_edit(request: HttpRequest, thread_id: int, message_id: int):
    """Edit your own group message (IM-6).

    Only the author may edit, and only in a thread that still accepts posts. The
    model stamps ``edited_at`` on save; we record ``edited_by`` for the audit
    trail. Served as a small server-rendered form (no inline JS, CSP-clean).
    """
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden("You don't have permission to access this group.")
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)
    message = get_object_or_404(
        ThreadMessage, id=message_id, thread=thread, is_deleted=False
    )
    if message.author_id != request.user.id:
        return HttpResponseForbidden("You can only edit your own messages.")
    if thread.is_archived:
        return HttpResponseForbidden("This group is archived.")

    if request.method == "POST":
        content = (request.POST.get("message") or "").strip()
        if not content:
            messages.error(request, _("A message can't be empty."))
        else:
            message.content = content
            message.edited_by = request.user
            message.save(
                update_fields=["content", "edited_by", "edited_at", "updated_at"]
            )
            messages.success(request, _("Message updated."))
            return redirect("communication:group_detail", thread_id=thread.id)

    return render(
        request,
        "communication/group_message_edit.html",
        {"thread": thread, "message": message},
    )


@login_required
def group_message_delete(request: HttpRequest, thread_id: int, message_id: int):
    """Soft-delete a group message (IM-6).

    The author may delete their own message; a thread moderator (creator / staff /
    department lead) may delete anyone's. Soft delete preserves the audit row
    (``is_deleted`` + ``deleted_at`` + ``deleted_by``); the message stops
    rendering everywhere it is filtered on ``is_deleted=False``.
    """
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden("You don't have permission to access this group.")
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)
    message = get_object_or_404(
        ThreadMessage, id=message_id, thread=thread, is_deleted=False
    )
    is_author = message.author_id == request.user.id
    if not (is_author or _can_moderate_thread(request.user, thread)):
        return HttpResponseForbidden("You can't delete this message.")

    if request.method == "POST":
        # .update() (not .save()) so the model's save() override doesn't stamp
        # edited_at — a delete is not an edit.
        # tenant-isolation-allow: row-scoped-to-this-fetched-school-scoped-thread
        ThreadMessage.objects.filter(pk=message.pk).update(
            is_deleted=True,
            deleted_at=timezone.now(),
            deleted_by=request.user,
        )
        messages.success(request, _("Message deleted."))
    return redirect("communication:group_detail", thread_id=thread.id)


@login_required
def group_mute_toggle(request: HttpRequest, thread_id: int):
    """Mute / unmute a group thread for the caller (IM-7).

    Muting stops "new message" notifications for this thread; the member stays in
    it and can still read it, and a direct @mention still notifies them.
    """
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden("You don't have permission to access this group.")
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)
    if not thread.members.filter(id=request.user.id).exists():
        return HttpResponseForbidden("Join this group before muting it.")
    if request.method == "POST":
        # tenant-isolation-allow: mute-row-scoped-to-caller-and-this-fetched-thread
        existing = ThreadMute.objects.filter(
            thread=thread, user=request.user
        ).first()
        if existing:
            existing.delete()
            messages.success(request, _("Notifications unmuted for this group."))
        else:
            ThreadMute.objects.create(thread=thread, user=request.user)
            messages.success(
                request, _("Muted. You won't be notified of new posts here.")
            )
    return redirect("communication:group_detail", thread_id=thread.id)


@login_required
def group_typing(request: HttpRequest, thread_id: int):
    """Typing indicator for a group thread (IM-7), cache-backed (no DB).

    POST marks the caller as typing for a few seconds; GET returns the other
    members currently typing. Membership-gated; ephemeral and best-effort.
    """
    if not _can_access_group_messaging(request.user):
        return HttpResponseForbidden("You don't have permission to access this group.")
    thread = get_object_or_404(_thread_queryset_for_request(request), id=thread_id)
    if not thread.members.filter(id=request.user.id).exists():
        return HttpResponseForbidden("You're not a member of this group.")
    from apps.communication.typing import typing_cache_key, typing_response

    return typing_response(request, typing_cache_key("thread", thread.id))
