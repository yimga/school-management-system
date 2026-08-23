"""
Communication API Views
Messages, Announcements, and Communication management endpoints
"""

import hashlib

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError

from apps.api.permissions import IsAdminUser
from apps.accounts.effective_access import api_any_role_access
from apps.platform_runtime.structured_logging import log_exception_with_context
User = get_user_model()  # role enum (was function-local)


def _school_user_queryset(school):
    User = get_user_model()
    if school is None:
        return User.objects.none()
    return User.objects.filter(
        Q(school_memberships__school=school)
        | Q(teacher_profile__school=school)
        | Q(student_profile__school=school)
    ).distinct()


def _tenant_school_or_response(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school, None
    return None, Response(
        {"error": "School context required."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _can_message_user(sender, recipient, school=None):
    """
    Enforce recipient policy: staff/admin/leadership can message anyone;
    parents can message teachers (of their children) and staff; teachers can message parents (of their students) and staff.
    """
    if not sender or not recipient or not getattr(sender, "is_authenticated", False):
        return False
    if sender.id == recipient.id:
        return False
    if school is not None:
        school_users = _school_user_queryset(school)
        if (
            not school_users.filter(pk=sender.pk).exists()
            or not school_users.filter(pk=recipient.pk).exists()
        ):
            return False
    # Staff / admin / leadership can message anyone
    if getattr(sender, "is_staff", False) or getattr(sender, "is_superuser", False):
        return True
    if api_any_role_access(
        sender,
        {"ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "COMMS_STAFF"},
    ):
        return True
    # Recipient is staff → allow (so parents/teachers can contact school)
    if getattr(recipient, "is_staff", False):
        return True
    role = (getattr(sender, "role", None) or "").upper()
    recipient_role = (getattr(recipient, "role", None) or "").upper()
    # Parent can message teachers (of their children) and other parents in same context - allow teacher/parent
    if role == User.Role.PARENT:
        if recipient_role in (
            "TEACHER",
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "HOD",
            "ACADEMICS_STAFF",
        ):
            return True
        if recipient_role == User.Role.PARENT:
            from apps.people.models import StudentGuardian

            sender_children = set(
                StudentGuardian.objects.filter(
                    guardian_user=sender,
                    **({"student__school": school} if school is not None else {}),
                ).values_list("student_id", flat=True)
            )
            recip_children = set(
                StudentGuardian.objects.filter(
                    guardian_user=recipient,
                    **({"student__school": school} if school is not None else {}),
                ).values_list("student_id", flat=True)
            )
            if sender_children & recip_children:
                return True
        return False
    # Teacher can message parents (of students in their classes) and staff
    if role in ("TEACHER", "HOD", "ACADEMICS_STAFF"):
        if recipient_role in (
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
        ):
            return True
        if recipient_role == User.Role.PARENT:
            from apps.people.models import StudentGuardian
            from apps.evals.models import TeacherAssignment

            teacher_profile = getattr(sender, "teacher_profile", None)
            if not teacher_profile:
                return False
            my_classroom_ids = set(
                TeacherAssignment.objects.filter(
                    teacher=teacher_profile,
                    is_active=True,
                    **(
                        {"subject_assignment__classroom__school": school}
                        if school is not None
                        else {}
                    ),
                ).values_list("subject_assignment__classroom_id", flat=True)
            )
            parent_student_ids = set(
                StudentGuardian.objects.filter(
                    guardian_user=recipient,
                    **({"student__school": school} if school is not None else {}),
                ).values_list("student_id", flat=True)
            )
            from apps.people.models import StudentProfile

            parent_classroom_ids = set(
                StudentProfile.objects.filter(
                    id__in=parent_student_ids,
                    **({"school": school} if school is not None else {}),
                ).values_list("classroom_id", flat=True)
            )
            if my_classroom_ids & parent_classroom_ids:
                return True
        return False
    # Student: allow messaging teachers/staff only
    if role == User.Role.STUDENT:
        return recipient_role in (
            "TEACHER",
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "HOD",
            "ACADEMICS_STAFF",
        )
    return False


class MessageViewSet(viewsets.ModelViewSet):
    """
    Internal messaging API

    Send, retrieve, and manage messages between users
    Support for threads, archiving, and filtering
    """

    permission_classes = [IsAuthenticated]
    filterset_fields = ["recipient", "sender", "is_read", "created_at"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        from apps.communication.models import Message

        user = self.request.user
        school = getattr(self.request, "school", None)
        if school is None:
            return Message.objects.none()
        return Message.objects.filter(
            Q(sender=user) | Q(recipient=user),
            school=school,
        ).select_related("sender", "recipient")

    def list(self, request, *args, **kwargs):
        """
        List messages

        Query Parameters:
        - folder: inbox, sent, archive
        - unread_only: true/false
        - from_user: filter by sender
        - search: search in subject/body
        """
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        queryset = self.get_queryset()

        folder = request.query_params.get("folder", "inbox")
        if folder == "inbox":
            queryset = queryset.filter(recipient=request.user)
        elif folder == "sent":
            queryset = queryset.filter(sender=request.user)
        elif folder == "archive":
            queryset = queryset.filter(is_archived=True)

        unread_only = request.query_params.get("unread_only", "false").lower() == "true"
        if unread_only:
            queryset = queryset.filter(is_read=False)

        from_user = request.query_params.get("from_user")
        if from_user:
            queryset = queryset.filter(sender_id=from_user)

        search_term = request.query_params.get("search")
        if search_term:
            queryset = queryset.filter(
                Q(subject__icontains=search_term) | Q(body__icontains=search_term)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            from apps.api.serializers import MessageSerializer

            serializer = MessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        from apps.api.serializers import MessageSerializer

        serializer = MessageSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Send a new message. Recipient must be allowed by policy (role/relationship).
        """
        from apps.communication.models import Message

        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error
        get_user_model()

        recipient_id = request.data.get("recipient")
        subject = request.data.get("subject")
        body = request.data.get("body")

        if not all([recipient_id, subject, body]):
            return Response(
                {"error": "recipient, subject, and body are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient = get_object_or_404(_school_user_queryset(school), pk=recipient_id)
        if not _can_message_user(request.user, recipient, school=school):
            return Response(
                {"error": "You are not allowed to send messages to this recipient."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.communication.comms_locale import locale_target_for_user

        message = Message.objects.create(
            sender=request.user,
            recipient=recipient,
            school=school,
            subject=subject,
            body=body,
            locale_target=locale_target_for_user(recipient),
        )

        from apps.api.serializers import MessageSerializer

        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark a message as read. Returns 404 for invalid or non-existent pk."""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        message = get_object_or_404(self.get_queryset(), pk=pk, school=school)
        if message.recipient != request.user:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        message.is_read = True
        message.save()

        return Response({"status": "success", "is_read": True})

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive a message"""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        message = get_object_or_404(self.get_queryset(), pk=pk, school=school)
        if message.recipient != request.user and message.sender != request.user:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        message.is_archived = True
        message.save()

        return Response({"status": "success", "is_archived": True})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all unread messages as read"""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        count = (
            self.get_queryset()
            .filter(recipient=request.user, school=school, is_read=False)
            .update(is_read=True)
        )

        return Response({"status": "success", "marked_as_read": count})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get count of unread messages"""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        count = (
            self.get_queryset()
            .filter(recipient=request.user, school=school, is_read=False)
            .count()
        )

        return Response({"unread_count": count})

    @action(detail=False, methods=["get"])
    def conversations(self, request):
        """Get list of unique conversations"""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        get_user_model()

        messages = self.get_queryset()

        conversation_users = set()
        for msg in messages:
            if msg.sender == request.user:
                conversation_users.add(msg.recipient_id)
            else:
                conversation_users.add(msg.sender_id)

        users = (
            _school_user_queryset(school)
            .filter(id__in=conversation_users)
            .values("id", "first_name", "last_name")
        )

        conversations = []
        for user_data in users:
            user_id = user_data["id"]
            user_messages = (
                self.get_queryset()
                .filter(
                    Q(sender=request.user, recipient_id=user_id)
                    | Q(sender_id=user_id, recipient=request.user),
                    school=school,
                )
                .order_by("-created_at")
            )

            if user_messages.exists():
                latest = user_messages.first()
                unread_count = (
                    self.get_queryset()
                    .filter(
                        sender_id=user_id,
                        recipient=request.user,
                        school=school,
                        is_read=False,
                    )
                    .count()
                )

                conversations.append(
                    {
                        "user_id": user_id,
                        "name": f"{user_data['first_name']} {user_data['last_name']}",
                        "last_message": latest.body[:100],
                        "last_message_time": latest.created_at,
                        "unread_count": unread_count,
                    }
                )

        return Response(
            {
                "total_conversations": len(conversations),
                "conversations": sorted(
                    conversations, key=lambda x: x["last_message_time"], reverse=True
                ),
            }
        )


class AnnouncementViewSet(viewsets.ModelViewSet):
    """
    School announcements API

    Create, retrieve, and manage school announcements
    Filter by audience, type, and date
    """

    permission_classes = [IsAuthenticated]
    filterset_fields = ["audience", "announcement_type", "is_active", "created_by"]
    ordering_fields = ["created_at", "expiry_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        from apps.communication.models import Announcement

        school = getattr(self.request, "school", None)
        if school is None:
            return Announcement.objects.none()

        return Announcement.objects.filter(
            school=school,
            is_active=True,
            status=Announcement.Status.PUBLISHED,
            expiry_date__gte=timezone.now(),
        ).select_related("created_by")

    def create(self, request, *args, **kwargs):
        """
        Create a school-wide announcement. Restricted to admins/leadership only
        (same as web). Teachers should use class/department announcements.

        Request Body:
        {
            "title": "School Closed Tomorrow",
            "content": "Due to holiday...",
            "announcement_type": "general",
            "audience": "all_parents",
            "expiry_date": "2025-02-22"
        }
        """
        from apps.communication.models import Announcement
        from apps.communication.views_announcements import (
            _can_create_school_wide_announcement,
        )

        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        if not _can_create_school_wide_announcement(request.user):
            return Response(
                {
                    "error": "Only administrators and leadership can create school-wide announcements."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.communication.models import log_announcement_audit
        from apps.communication.views_announcements import (
            _deliver_published_announcement_best_effort,
        )

        announcement = Announcement.objects.create(
            title=request.data.get("title"),
            content=request.data.get("content"),
            announcement_type=request.data.get("announcement_type", "general"),
            audience=request.data.get("audience", "all"),
            created_by=request.user,
            school=school,
            status=Announcement.Status.PUBLISHED,
        )

        if "expiry_date" in request.data:
            announcement.expiry_date = request.data.get("expiry_date")
            announcement.save()

        log_announcement_audit(announcement, request.user, "created")

        # Same fan-out the two web publish paths perform (views_announcements
        # :publish and :approve). Without it an API-created announcement was
        # PUBLISHED but delivered to no channel at all, and the periodic sweep
        # could not rescue it either (scheduled_at is NULL here).
        _deliver_published_announcement_best_effort(announcement)

        from apps.api.serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer(announcement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get active, published announcements for current user."""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        user = request.user
        now = timezone.now()
        announcements = (
            self.get_queryset().filter(expiry_date__gte=now).order_by("-created_at")
        )

        if user.role == User.Role.STUDENT:
            announcements = announcements.filter(
                Q(audience="all") | Q(audience="students")
            )
        elif user.role == User.Role.PARENT:
            announcements = announcements.filter(
                Q(audience="all") | Q(audience="all_parents")
            )
        elif user.role == User.Role.TEACHER:
            announcements = announcements.filter(
                Q(audience="all") | Q(audience="staff") | Q(audience="teachers")
            )

        from apps.api.serializers import AnnouncementSerializer

        serializer = AnnouncementSerializer(announcements[:10], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate an announcement"""
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error
        if not request.user.is_staff:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        announcement = get_object_or_404(self.get_queryset(), pk=pk, school=school)
        announcement.is_active = False
        announcement.save()

        return Response({"status": "success", "is_active": False})


# --- BroadcastAPI hardening constants (MED-5) ---
# Hard cap on the fan-out audience: a single broadcast may not enqueue more
# than this many Message rows synchronously. Protects against an
# ``recipient_group="all"`` POST writing N rows on a large tenant.
MAX_BROADCAST_RECIPIENTS = 5000  # magic-number-allow: broadcast fan-out hard cap
# bulk_create batch size — bounds the size of each INSERT statement.
BROADCAST_BULK_BATCH_SIZE = 500  # magic-number-allow: bulk_create batch size
# Idempotency dedupe window (seconds). A repeat (admin + idempotency_key)
# inside this TTL returns the prior result instead of re-broadcasting.
BROADCAST_IDEMPOTENCY_TTL_SECONDS = 600  # magic-number-allow: idempotency dedupe window


class BroadcastThrottle(UserRateThrottle):
    """Per-admin rate limit for broadcast fan-out (MED-5).

    Mirrors the ``MobileRateThrottle`` pattern (apps/api/mobile_api.py): a
    ``UserRateThrottle`` subclass with the rate set directly on the class, so
    it does not depend on ``DEFAULT_THROTTLE_RATES`` in settings. A distinct
    ``scope`` keeps its cache bucket separate from the default ``user`` scope.
    """

    scope = "broadcast"
    rate = "12/hour"  # magic-number-allow: broadcast send throttle


class BroadcastAPI(APIView):
    """
    Send broadcast messages to groups
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [BroadcastThrottle]

    def post(self, request):
        """
        Send message to multiple recipients

        Request Body:
        {
            "recipients": [1, 2, 3],
            "recipient_type": "user_ids",
            "subject": "Important Notice",
            "body": "Please read carefully",
            "recipient_group": "all_teachers",  # Alternative to recipients list
            "idempotency_key": "optional-client-supplied-dedupe-token"
        }
        """
        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        from apps.communication.models import Message, NotificationPreference

        users = _school_user_queryset(school)

        recipient_ids = request.data.get("recipients", [])
        recipient_group = request.data.get("recipient_group")
        subject = request.data.get("subject")
        body = request.data.get("body")
        idempotency_key = request.data.get("idempotency_key")

        if not all([subject, body]):
            return Response(
                {"error": "subject and body are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Idempotency: short-circuit a recent duplicate (fail-open). ---
        # Key is scoped to the requesting admin + tenant so two admins (or two
        # schools) can't collide. Cache failure must not block a legitimate send.
        cache_key = None
        if idempotency_key:
            digest = hashlib.sha256(
                str(idempotency_key).encode("utf-8")
            ).hexdigest()
            cache_key = (
                f"broadcast:idem:{getattr(school, 'id', 'none')}"
                f":{getattr(request.user, 'id', 'anon')}:{digest}"
            )
            try:
                prior = cache.get(cache_key)
            except Exception:  # pragma: no cover - cache backend down → fail-open
                prior = None
            if prior is not None:
                prior = dict(prior)
                prior["deduplicated"] = True
                return Response(prior, status=status.HTTP_200_OK)

        if recipient_group:
            if recipient_group == "all_teachers":
                users = users.filter(role="TEACHER")
            elif recipient_group == "all_students":
                users = users.filter(role="STUDENT")
            elif recipient_group == "all_parents":
                users = users.filter(role="PARENT")
            elif recipient_group == "all":
                users = users.all()
            else:
                users = users.none()

            recipient_ids = list(users.values_list("id", flat=True))
        else:
            recipient_ids = list(
                users.filter(id__in=recipient_ids).values_list("id", flat=True)
            )

        total_resolved = len(recipient_ids)

        # --- Recipient cap: truncate-and-report (never silently send a subset). ---
        capped = False
        if total_resolved > MAX_BROADCAST_RECIPIENTS:
            capped = True
            recipient_ids = recipient_ids[:MAX_BROADCAST_RECIPIENTS]

        # --- Preference/consent filter (broadcasts are announcement-class). ---
        # Bulk-load preferences keyed by user_id and drop anyone who muted
        # ANNOUNCEMENTS. Missing preference row == no mute (default allow).
        muted_user_ids = set()
        try:
            prefs = NotificationPreference.objects.filter(
                user_id__in=recipient_ids
            ).only("user_id", "muted_categories")
            for pref in prefs:
                if pref.is_muted(NotificationPreference.Category.ANNOUNCEMENTS):
                    muted_user_ids.add(pref.user_id)
        except (DatabaseError, ValueError, TypeError) as e:
            # Don't let a preference-lookup failure block the whole broadcast;
            # log and proceed as if no one had muted (fail-open, honest count).
            log_exception_with_context(
                "communication.api_views: NotificationPreference filter skipped",
                school_id=getattr(school, "id", None),
                extra={"error": str(e)},
            )

        deliverable_ids = [rid for rid in recipient_ids if rid not in muted_user_ids]
        skipped_preference = len(recipient_ids) - len(deliverable_ids)

        from apps.communication.comms_locale import locale_target_for_user

        User = get_user_model()
        rec_by_id = {u.pk: u for u in User.objects.filter(pk__in=deliverable_ids)}

        # bulk_create is DELIBERATE here: it does NOT fire Message post_save
        # signals. A sibling adds a per-DM notification signal for 1:1 messages
        # that must NOT fan out once per broadcast row. Build all rows then
        # insert in batches.
        rows = [
            Message(
                sender=request.user,
                recipient_id=recipient_id,
                school=school,
                subject=subject,
                body=body,
                locale_target=(
                    locale_target_for_user(rec_by_id.get(recipient_id))
                    if rec_by_id.get(recipient_id)
                    else ""
                ),
            )
            for recipient_id in deliverable_ids
        ]

        sent = 0
        try:
            created = Message.objects.bulk_create(
                rows, batch_size=BROADCAST_BULK_BATCH_SIZE
            )
            sent = len(created)
        except (IntegrityError, DatabaseError, ValidationError, ValueError, TypeError) as e:
            log_exception_with_context(
                "communication.api_views: Message.bulk_create failed",
                school_id=getattr(school, "id", None),
                extra={"deliverable": len(deliverable_ids), "error": str(e)},
            )
            return Response(
                {"error": "Broadcast failed to send."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result = {
            "status": "success",
            # Existing response shape preserved (back-compat):
            "messages_sent": sent,
            "recipients": len(deliverable_ids),
            # New, honest counts:
            "total_resolved": total_resolved,
            "sent": sent,
            "skipped_preference": skipped_preference,
            "capped": capped,
            "cap": MAX_BROADCAST_RECIPIENTS,
        }

        # Store the result for idempotent replay (fail-open on cache error).
        if cache_key is not None:
            try:
                cache.set(
                    cache_key, result, timeout=BROADCAST_IDEMPOTENCY_TTL_SECONDS
                )
            except Exception:  # pragma: no cover - cache backend down → fail-open
                pass

        return Response(result, status=status.HTTP_201_CREATED)


class CommunicationAnalyticsAPI(APIView):
    """
    Communication statistics and analytics
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get communication analytics"""
        from apps.communication.models import Message, Announcement

        school, error = _tenant_school_or_response(request)
        if error is not None:
            return error

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        message_queryset = Message.objects.filter(school=school)
        announcement_queryset = Announcement.objects.filter(school=school)

        messages_total = message_queryset.count()
        messages_this_week = message_queryset.filter(created_at__gte=week_ago).count()
        messages_this_month = message_queryset.filter(created_at__gte=month_ago).count()

        unread_messages = message_queryset.filter(is_read=False).count()

        active_announcements = announcement_queryset.filter(
            is_active=True, status=Announcement.Status.PUBLISHED, expiry_date__gte=now
        ).count()

        most_active_users = (
            message_queryset.values("sender__first_name", "sender__last_name")
            .annotate(message_count=Count("id"))
            .order_by("-message_count")[:10]
        )

        return Response(
            {
                "total_messages": messages_total,
                "messages_this_week": messages_this_week,
                "messages_this_month": messages_this_month,
                "unread_messages": unread_messages,
                "active_announcements": active_announcements,
                "most_active_users": list(most_active_users),
                "average_response_time": "N/A",
            }
        )
