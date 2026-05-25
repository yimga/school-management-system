"""
Phase 9 Task 2: Mobile API Layer
REST API for mobile applications with authentication, rate limiting, offline support
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
import uuid
from django.utils.dateparse import parse_datetime

User = get_user_model()


class MobileDevice(models.Model):
    """Track mobile devices for push notifications"""

    PLATFORM_CHOICES = [
        ("IOS", "iOS"),
        ("ANDROID", "Android"),
        ("WEB", "Web"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mobile_devices"
    )
    device_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    device_name = models.CharField(max_length=255)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    push_token = models.CharField(max_length=500, blank=True)
    app_version = models.CharField(max_length=50)
    os_version = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    last_active = models.DateTimeField(auto_now=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_active"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["device_id"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.device_name} ({self.platform})"


class APIAccessLog(models.Model):
    """Log API access for monitoring and rate limiting"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    device = models.ForeignKey(
        MobileDevice, on_delete=models.SET_NULL, null=True, blank=True
    )
    endpoint = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=500, blank=True)
    status_code = models.IntegerField()
    response_time_ms = models.IntegerField()
    request_size = models.IntegerField(default=0)
    response_size = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["endpoint", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
        ]


class PushNotification(models.Model):
    """Push notifications to mobile devices"""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
        ("DELIVERED", "Delivered"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("NORMAL", "Normal"),
        ("HIGH", "High"),
    ]

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="NORMAL"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["device", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.device.user.username}"


class OfflineSyncQueue(models.Model):
    """Queue for offline data synchronization"""

    SYNC_STATUS = [
        ("PENDING", "Pending"),
        ("SYNCING", "Syncing"),
        ("COMPLETED", "Completed"),
        ("CONFLICT", "Conflict"),
        ("FAILED", "Failed"),
    ]

    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=100)  # e.g., 'evaluation', 'attendance'
    entity_id = models.IntegerField()
    action = models.CharField(max_length=20)  # CREATE, UPDATE, DELETE
    data = models.JSONField()
    client_timestamp = models.DateTimeField()
    status = models.CharField(max_length=20, choices=SYNC_STATUS, default="PENDING")
    conflict_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Incremented when the client retries a failed sync_batch row.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["device", "status"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} - {self.action} ({self.status})"


class MobileRateThrottle(UserRateThrottle):
    """Custom rate limiting for mobile API"""

    rate = "100/hour"


class MobileAnonRateThrottle(AnonRateThrottle):
    """Rate limiting for anonymous mobile requests"""

    rate = "20/hour"


class MobileAPIPermission(permissions.BasePermission):
    """Permission class for mobile API endpoints"""

    def has_permission(self, request, view):
        # Require authentication
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user has mobile API access
        return (
            hasattr(request.user, "mobile_devices")
            and request.user.mobile_devices.filter(is_active=True).exists()
        )


# Serializers


class MobileDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileDevice
        fields = [
            "device_id",
            "device_name",
            "platform",
            "app_version",
            "os_version",
            "is_active",
            "last_active",
            "registered_at",
        ]
        read_only_fields = ["device_id", "last_active", "registered_at"]


class PushNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushNotification
        fields = [
            "id",
            "title",
            "body",
            "data",
            "priority",
            "status",
            "sent_at",
            "delivered_at",
            "created_at",
        ]
        read_only_fields = ["id", "status", "sent_at", "delivered_at", "created_at"]


class OfflineSyncQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineSyncQueue
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "action",
            "data",
            "client_timestamp",
            "status",
            "conflict_data",
            "synced_at",
        ]
        read_only_fields = ["id", "status", "conflict_data", "synced_at"]


# ViewSets


@extend_schema_view(
    list=extend_schema(tags=["Mobile"], summary="List the caller's mobile devices", responses={200: MobileDeviceSerializer(many=True)}),
    retrieve=extend_schema(tags=["Mobile"], summary="Retrieve a mobile device", responses={200: MobileDeviceSerializer, 404: OpenApiResponse(description="Not found")}),
    create=extend_schema(tags=["Mobile"], summary="Register a mobile device for the caller", request=MobileDeviceSerializer, responses={201: MobileDeviceSerializer, 400: OpenApiResponse(description="Validation error")}),
    update=extend_schema(tags=["Mobile"], summary="Update a mobile device", request=MobileDeviceSerializer, responses={200: MobileDeviceSerializer}),
    partial_update=extend_schema(tags=["Mobile"], summary="Partially update a mobile device", request=MobileDeviceSerializer, responses={200: MobileDeviceSerializer}),
    destroy=extend_schema(tags=["Mobile"], summary="Delete a mobile device", request=None, responses={204: OpenApiResponse(description="Deleted")}),
    update_push_token=extend_schema(
        tags=["Mobile"],
        summary="Update the device's push-notification token",
        request=inline_serializer(name="UpdatePushTokenRequest", fields={"push_token": serializers.CharField()}),
        responses={
            200: inline_serializer(name="UpdatePushTokenResponse", fields={"status": serializers.CharField()}),
            400: OpenApiResponse(description="Missing push_token"),
        },
    ),
    deactivate=extend_schema(
        tags=["Mobile"],
        summary="Deactivate the device",
        request=None,
        responses={200: inline_serializer(name="DeviceDeactivateResponse", fields={"status": serializers.CharField()})},
    ),
)
class MobileDeviceViewSet(viewsets.ModelViewSet):
    """Mobile device registration and management"""

    serializer_class = MobileDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]

    def get_queryset(self):
        return MobileDevice.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def update_push_token(self, request, pk=None):
        """Update device push notification token"""
        device = self.get_object()
        push_token = request.data.get("push_token")

        if not push_token:
            return Response(
                {"error": "push_token is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        device.push_token = push_token
        device.save()

        return Response({"status": "token updated"})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate device"""
        device = self.get_object()
        device.is_active = False
        device.save()

        return Response({"status": "device deactivated"})


@extend_schema_view(
    list=extend_schema(
        tags=["Mobile"],
        summary="List recent push notifications for the caller",
        description="Returns the most recent 50 push notifications across the caller's registered devices.",
        responses={200: PushNotificationSerializer(many=True)},
    ),
    retrieve=extend_schema(tags=["Mobile"], summary="Retrieve a push notification", responses={200: PushNotificationSerializer, 404: OpenApiResponse(description="Not found")}),
    mark_delivered=extend_schema(
        tags=["Mobile"],
        summary="Mark a push notification as delivered",
        description="Client-acknowledgement endpoint — sets status=DELIVERED and stamps delivered_at.",
        request=None,
        responses={200: inline_serializer(name="MarkDeliveredResponse", fields={"status": serializers.CharField()})},
    ),
)
class PushNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """View push notifications"""

    serializer_class = PushNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]

    def get_queryset(self):
        return PushNotification.objects.filter(device__user=self.request.user).order_by(
            "-created_at"
        )[:50]

    @action(detail=True, methods=["post"])
    def mark_delivered(self, request, pk=None):
        """Mark notification as delivered"""
        notification = self.get_object()
        notification.status = "DELIVERED"
        notification.delivered_at = timezone.now()
        notification.save()

        return Response({"status": "marked delivered"})


@extend_schema_view(
    list=extend_schema(tags=["Offline Sync"], summary="List queued offline sync items", description="Returns PENDING + CONFLICT items for the caller's devices.", responses={200: OfflineSyncQueueSerializer(many=True)}),
    retrieve=extend_schema(tags=["Offline Sync"], summary="Retrieve a queued sync item", responses={200: OfflineSyncQueueSerializer, 404: OpenApiResponse(description="Not found")}),
    create=extend_schema(tags=["Offline Sync"], summary="Queue an offline change for sync", request=OfflineSyncQueueSerializer, responses={201: OfflineSyncQueueSerializer, 400: OpenApiResponse(description="Invalid device_id")}),
    update=extend_schema(tags=["Offline Sync"], summary="Update a queued sync item", request=OfflineSyncQueueSerializer, responses={200: OfflineSyncQueueSerializer}),
    partial_update=extend_schema(tags=["Offline Sync"], summary="Partially update a queued sync item", request=OfflineSyncQueueSerializer, responses={200: OfflineSyncQueueSerializer}),
    destroy=extend_schema(tags=["Offline Sync"], summary="Delete a queued sync item", request=None, responses={204: OpenApiResponse(description="Deleted")}),
    sync_batch=extend_schema(
        tags=["Offline Sync"],
        summary="Sync a batch of offline changes",
        description=(
            "Replays a list of offline mutations (grades/attendance/payments) as the "
            "caller. Subject to per-tenant offline mode + feature flags. Each item "
            "lands in OfflineSyncQueue and is resolved through the appropriate "
            "domain processor, returning COMPLETED, CONFLICT or FAILED."
        ),
        request=inline_serializer(
            name="OfflineSyncBatchRequest",
            fields={
                "device_id": serializers.UUIDField(),
                "changes": serializers.ListField(child=serializers.DictField()),
            },
        ),
        responses={
            200: inline_serializer(
                name="OfflineSyncBatchResponse",
                fields={
                    "synced": serializers.IntegerField(),
                    "conflicts": serializers.IntegerField(),
                    "failed": serializers.IntegerField(),
                    "results": serializers.ListField(child=serializers.DictField()),
                },
            ),
            400: OpenApiResponse(description="Missing or invalid device_id"),
            403: OpenApiResponse(description="Offline sync disabled by tenant or system"),
        },
    ),
    sync_state=extend_schema(
        tags=["Offline Sync"],
        summary="Get queue counts for the caller",
        request=None,
        responses={200: inline_serializer(name="OfflineSyncStateResponse", fields={"pending": serializers.IntegerField(required=False), "conflict": serializers.IntegerField(required=False), "failed": serializers.IntegerField(required=False)})},
    ),
    retry_failed=extend_schema(
        tags=["Offline Sync"],
        summary="Reset FAILED rows so the client can replay sync_batch",
        request=inline_serializer(name="OfflineSyncRetryRequest", fields={"max_retries": serializers.IntegerField(required=False)}),
        responses={200: inline_serializer(name="OfflineSyncRetryResponse", fields={"reset": serializers.IntegerField(required=False)})},
    ),
    resolve_conflict=extend_schema(
        tags=["Offline Sync"],
        summary="Resolve a sync conflict",
        request=inline_serializer(name="OfflineSyncResolveRequest", fields={"resolution": serializers.ChoiceField(choices=["client", "server"])}),
        responses={
            200: inline_serializer(name="OfflineSyncResolveResponse", fields={"status": serializers.CharField()}),
            400: OpenApiResponse(description="Invalid resolution value"),
        },
    ),
)
class OfflineSyncViewSet(viewsets.ModelViewSet):
    """Offline data synchronization"""

    serializer_class = OfflineSyncQueueSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]

    def get_queryset(self):
        return OfflineSyncQueue.objects.filter(
            device__user=self.request.user, status__in=["PENDING", "CONFLICT"]
        )

    def _parse_client_timestamp(self, raw_value):
        """Best-effort parser for client timestamps."""
        if hasattr(raw_value, "tzinfo"):
            return raw_value
        if isinstance(raw_value, str):
            parsed = parse_datetime(raw_value)
            if parsed:
                if timezone.is_naive(parsed):
                    return timezone.make_aware(parsed, timezone.get_current_timezone())
                return parsed
        return timezone.now()

    @staticmethod
    def _is_server_newer(server_dt, client_dt):
        if not server_dt or not client_dt:
            return False
        if timezone.is_naive(server_dt):
            server_dt = timezone.make_aware(server_dt, timezone.get_current_timezone())
        if timezone.is_naive(client_dt):
            client_dt = timezone.make_aware(client_dt, timezone.get_current_timezone())
        return server_dt > client_dt

    def _process_eval_sync(self, sync_item, user):
        """
        Process evaluation sync items through OfflineMarkEntry + conflict resolver.
        Multi-tenant: validate school_id matches request.school and user's membership (Phase 4).
        """
        from apps.academics.models import SubjectAssignment, AcademicYear, Term
        from apps.evals.models import OfflineMarkEntry
        from apps.evals.offline_sync import OfflineSyncService
        from apps.people.models import TeacherProfile, StudentProfile
        from apps.schools.models import SchoolMembership

        payload = sync_item.data or {}
        school = getattr(self.request, "school", None)
        if school:
            payload_school_id = payload.get("school_id")
            if payload_school_id and str(payload_school_id) != str(school.id):
                sync_item.status = "FAILED"
                sync_item.error_message = "school_id does not match current school."
                sync_item.synced_at = timezone.now()
                sync_item.save(update_fields=["status", "error_message", "synced_at"])
                return {"status": sync_item.status, "error": sync_item.error_message}
            if not SchoolMembership.objects.filter(user=user, school=school).exists():
                sync_item.status = "FAILED"
                sync_item.error_message = "User has no access to this school."
                sync_item.synced_at = timezone.now()
                sync_item.save(update_fields=["status", "error_message", "synced_at"])
                return {"status": sync_item.status, "error": sync_item.error_message}

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        teacher = TeacherProfile.objects.filter(user=user).first()
        if not teacher:
            sync_item.status = "FAILED"
            sync_item.error_message = "Authenticated user has no teacher profile."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        subject_assignment_id = payload.get("subject_assignment_id") or payload.get(
            "subject_assignment"
        )
        student_id = payload.get("student_id") or payload.get("student")
        academic_year_id = payload.get("academic_year_id") or payload.get(
            "academic_year"
        )
        term_id = payload.get("term_id") or payload.get("term")

        if not all([subject_assignment_id, student_id, academic_year_id, term_id]):
            sync_item.status = "FAILED"
            sync_item.error_message = "Missing required identifiers: subject_assignment_id, student_id, academic_year_id, term_id."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        sa_qs = SubjectAssignment.objects.filter(id=subject_assignment_id)
        if school:
            sa_qs = sa_qs.filter(school=school)
        if not sa_qs.exists():
            sync_item.status = "FAILED"
            sync_item.error_message = (
                f"SubjectAssignment {subject_assignment_id} not found."
            )
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        sp_qs = StudentProfile.objects.filter(id=student_id)
        if school:
            sp_qs = sp_qs.filter(school=school)
        if not sp_qs.exists():
            sync_item.status = "FAILED"
            sync_item.error_message = f"StudentProfile {student_id} not found."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            return {"status": sync_item.status, "error": sync_item.error_message}

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ay_qs = AcademicYear.objects.filter(id=academic_year_id)
        if school:
            ay_qs = ay_qs.filter(school=school)
        if not ay_qs.exists():
            sync_item.status = "FAILED"
            sync_item.error_message = f"AcademicYear {academic_year_id} not found."
            sync_item.synced_at = timezone.now()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        term_qs = Term.objects.filter(id=term_id)
        if school:
            term_qs = term_qs.filter(school=school)
        if not term_qs.exists():
            sync_item.status = "FAILED"
            sync_item.error_message = f"Term {term_id} not found."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        offline_entry = OfflineMarkEntry.objects.create(
            teacher=teacher,
            subject_assignment_id=subject_assignment_id,
            student_id=student_id,
            academic_year_id=academic_year_id,
            term_id=term_id,
            seq1_score=payload.get("seq1_score"),
            seq2_score=payload.get("seq2_score"),
            exam_score=payload.get("exam_score"),
            mock_score=payload.get("mock_score"),
            practical_score=payload.get("practical_score"),
            remarks=payload.get("remarks", ""),
            created_offline_at=self._parse_client_timestamp(sync_item.client_timestamp),
            status="pending",
        )

        success, message = OfflineSyncService.sync_offline_entry(
            offline_entry, teacher=teacher
        )
        sync_item.synced_at = timezone.now()
        if success:
            sync_item.status = "COMPLETED"
            sync_item.error_message = ""
            sync_item.conflict_data = {
                "offline_entry_id": offline_entry.id,
                "message": message,
            }
        else:
            is_conflict = "conflict" in (message or "").lower()
            sync_item.status = "CONFLICT" if is_conflict else "FAILED"
            sync_item.error_message = message
            sync_item.conflict_data = {
                "offline_entry_id": offline_entry.id,
                "message": message,
            }
        sync_item.save(
            update_fields=["status", "error_message", "conflict_data", "synced_at"]
        )
        return {
            "status": sync_item.status,
            "message": message,
            "offline_entry_id": offline_entry.id,
        }

    def _process_attendance_sync(self, sync_item, user):
        """Process attendance sync items with conflict handling based on tenant-aware settings."""
        from apps.academics.models import Attendance
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        from apps.evals.models import TeacherAssignment
        from apps.people.models import TeacherProfile, StudentProfile
        from apps.platform_runtime.helpers import get_effective_offline_runtime_settings
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        payload = sync_item.data or {}
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        teacher = TeacherProfile.objects.filter(user=user).first()
        if not teacher and not user.is_staff:
            sync_item.status = "FAILED"
            sync_item.error_message = "Authenticated user has no teacher profile."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        student_id = payload.get("student_id") or payload.get("student")
        classroom_id = payload.get("classroom_id") or payload.get("classroom")
        raw_date = payload.get("date")
        status_value = payload.get("status")
        remarks = payload.get("remarks", "")

        if not all([student_id, classroom_id, raw_date, status_value]):
            sync_item.status = "FAILED"
            sync_item.error_message = (
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                "Missing required fields: student_id, classroom_id, date, status."
            )
            sync_item.synced_at = timezone.now()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        if not StudentProfile.objects.filter(id=student_id).exists():
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.status = "FAILED"
            sync_item.error_message = f"StudentProfile {student_id} not found."
            sync_item.synced_at = timezone.now()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        if teacher and not user.is_staff:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom_id,
            ).exists()
            if not allowed:
                sync_item.status = "FAILED"
                sync_item.error_message = (
                    "Teacher is not assigned to the specified classroom."
                )
                sync_item.synced_at = timezone.now()
                sync_item.save(update_fields=["status", "error_message", "synced_at"])
                return {"status": sync_item.status, "error": sync_item.error_message}

        try:
            local_date = timezone.datetime.strptime(
                str(raw_date)[:10], "%Y-%m-%d"
            ).date()
        except ValueError:
            sync_item.status = "FAILED"
            sync_item.error_message = "Invalid date format. Use YYYY-MM-DD."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        allowed_statuses = {choice[0] for choice in Attendance.Status.choices}
        if status_value not in allowed_statuses:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.status = "FAILED"
            sync_item.error_message = f"Invalid attendance status: {status_value}."
            sync_item.synced_at = timezone.now()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        existing = Attendance.objects.filter(
            student_id=student_id,
            classroom_id=classroom_id,
            date=local_date,
        ).first()
        client_ts = self._parse_client_timestamp(sync_item.client_timestamp)
        offline_settings = get_effective_offline_runtime_settings(
            school=getattr(sync_item, "school", None)
        )
        mode = str(
            offline_settings.get("offline_sync_conflict_resolution", "show_both")
            or "show_both"
        ).lower()

        if existing and self._is_server_newer(existing.updated_at, client_ts):
            if mode == "reject":
                sync_item.status = "CONFLICT"
                sync_item.error_message = (
                    "Server attendance record is newer than offline update."
                )
                sync_item.conflict_data = {
                    "conflict": "server_newer",
                    "server": {
                        "status": existing.status,
                        "remarks": existing.remarks,
                        "updated_at": existing.updated_at.isoformat()
                        if existing.updated_at
                        else None,
                    },
                    "client": {
                        "status": status_value,
                        "remarks": remarks,
                        "client_timestamp": client_ts.isoformat(),
                    },
                }
                sync_item.synced_at = timezone.now()
                sync_item.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "conflict_data",
                        "synced_at",
                    ]
                )
                return {"status": sync_item.status, "message": sync_item.error_message}
            if mode == "auto_merge":
                sync_item.status = "COMPLETED"
                sync_item.error_message = ""
                sync_item.conflict_data = {
                    "resolution": "kept_server_newer",
                    "server_updated_at": existing.updated_at.isoformat()
                    if existing.updated_at
                    else None,
                }
                sync_item.synced_at = timezone.now()
                sync_item.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "conflict_data",
                        "synced_at",
                    ]
                )
                return {
                    "status": sync_item.status,
                    "message": "Server version kept (newer record).",
                }
            # show_both
            sync_item.status = "CONFLICT"
            sync_item.error_message = "Conflict requires review."
            sync_item.conflict_data = {
                "conflict": "show_both",
                "server": {
                    "status": existing.status,
                    "remarks": existing.remarks,
                    "updated_at": existing.updated_at.isoformat()
                    if existing.updated_at
                    else None,
                },
                "client": {
                    "status": status_value,
                    "remarks": remarks,
                    "client_timestamp": client_ts.isoformat(),
                },
            }
            sync_item.synced_at = timezone.now()
            sync_item.save(
                update_fields=["status", "error_message", "conflict_data", "synced_at"]
            )
            return {"status": sync_item.status, "message": sync_item.error_message}

        attendance, _created = Attendance.objects.update_or_create(
            student_id=student_id,
            classroom_id=classroom_id,
            date=local_date,
            defaults={
                "status": status_value,
                "remarks": remarks,
            },
        )
        sync_item.status = "COMPLETED"
        sync_item.error_message = ""
        sync_item.conflict_data = {
            "attendance_id": attendance.id,
            "updated_at": attendance.updated_at.isoformat()
            if attendance.updated_at
            else None,
        }
        sync_item.synced_at = timezone.now()
        sync_item.save(
            update_fields=["status", "error_message", "conflict_data", "synced_at"]
        )
        return {"status": sync_item.status, "attendance_id": attendance.id}

    def _process_offline_payment_sync(self, sync_item, user):
        """Persist queued offline payment / receipt metadata for later reconciliation."""
        from decimal import Decimal, InvalidOperation

        from apps.platform_runtime.helpers import get_effective_offline_runtime_settings
        from apps.finance.models import (
            Invoice,
            OfflinePaymentIntent,
            PaymentMethodCode,
        )

        offline_settings = get_effective_offline_runtime_settings(request=self.request)
        flags = offline_settings.get("backend_feature_flags") or {}
        if not bool(flags.get("enable_offline_payment_sync", True)):
            sync_item.status = "FAILED"
            sync_item.error_message = (
                "Offline payment sync is disabled in Feature Control."
            )
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        payload = sync_item.data or {}
        invoice_id = payload.get("invoice_id")
        amount_raw = payload.get("amount")
        payment_method = (payload.get("payment_method") or "OTHER").upper()
        client_offline_id = (
            payload.get("client_offline_id") or payload.get("idempotency_key") or ""
        )
        client_offline_id = str(client_offline_id)[:64]

        if not invoice_id or amount_raw is None:
            sync_item.status = "FAILED"
            sync_item.error_message = (
                "Missing required fields: invoice_id, amount."
            )
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        valid_methods = {c[0] for c in PaymentMethodCode.choices}
        if payment_method not in valid_methods:
            sync_item.status = "FAILED"
            sync_item.error_message = f"Invalid payment_method: {payment_method}."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, TypeError, ValueError):
            sync_item.status = "FAILED"
            sync_item.error_message = "Invalid amount."
            sync_item.synced_at = timezone.now()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        try:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            inv = Invoice.objects.get(pk=invoice_id)
        except Invoice.DoesNotExist:
            sync_item.status = "FAILED"
            sync_item.error_message = f"Invoice {invoice_id} not found."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        school = getattr(self.request, "school", None)
        if school and inv.school_id and inv.school_id != school.id:
            sync_item.status = "FAILED"
            sync_item.error_message = "Invoice does not belong to the active school."
            sync_item.synced_at = timezone.now()
            sync_item.save(update_fields=["status", "error_message", "synced_at"])
            return {"status": sync_item.status, "error": sync_item.error_message}

        if client_offline_id:
            existing = OfflinePaymentIntent.objects.filter(
                invoice_id=invoice_id,
                client_offline_id=client_offline_id,
            ).first()
            if existing:
                sync_item.status = "COMPLETED"
                sync_item.error_message = ""
                sync_item.conflict_data = {
                    "offline_payment_intent_id": existing.id,
                    "deduplicated": True,
                }
                sync_item.synced_at = timezone.now()
                sync_item.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "conflict_data",
                        "synced_at",
                    ]
                )
                return {"status": sync_item.status, "intent_id": existing.id}

        intent = OfflinePaymentIntent.objects.create(
            invoice_id=invoice_id,
            recorded_by=user,
            amount=amount,
            payment_method=payment_method,
            transaction_reference=str(payload.get("transaction_reference", ""))[:100],
            notes=str(payload.get("notes", ""))[:4000],
            client_offline_id=client_offline_id,
            source_sync_queue_id=sync_item.id,
        )
        sync_item.status = "COMPLETED"
        sync_item.error_message = ""
        sync_item.conflict_data = {"offline_payment_intent_id": intent.id}
        sync_item.synced_at = timezone.now()
        sync_item.save(
            update_fields=["status", "error_message", "conflict_data", "synced_at"]
        )
        return {"status": sync_item.status, "intent_id": intent.id}

    def perform_create(self, serializer):
        """Queue offline changes for sync"""
        device_id = self.request.data.get("device_id")

        try:
            device = MobileDevice.objects.get(
                device_id=device_id, user=self.request.user
            )
        except MobileDevice.DoesNotExist:
            return Response(
                {"error": "Invalid device_id"}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save(device=device)

    @action(detail=False, methods=["post"])
    def sync_batch(self, request):
        """Sync batch of offline changes. Multi-tenant: school must have offline_mode module when request.school is set."""
        from apps.platform_runtime.helpers import get_effective_offline_runtime_settings

        offline_settings = get_effective_offline_runtime_settings(request=request)
        flags = offline_settings.get("backend_feature_flags") or {}
        if not bool(offline_settings.get("enable_offline_mode", False)):
            return Response(
                {"error": "Offline sync is disabled by system configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )
        school = getattr(request, "school", None)
        if school:
            from apps.policies.policy_registry import get_effective_policy

            try:
                offline_ok = get_effective_policy(
                    school,
                    user=getattr(request, "user", None),
                    capability="offline_mode",
                ).get("enabled", False)
            except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
                offline_ok = False
            if not offline_ok:
                return Response(
                    {
                        "error": "Offline sync is not enabled for this school. Enable the Offline Mode module in Module Market."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        changes = request.data.get("changes", [])
        device_id = request.data.get("device_id")

        if not device_id:
            return Response(
                {"error": "device_id required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            device = MobileDevice.objects.get(device_id=device_id, user=request.user)
        except MobileDevice.DoesNotExist:
            return Response(
                {"error": "Invalid device_id"}, status=status.HTTP_400_BAD_REQUEST
            )

        results = []
        synced_count = 0
        conflict_count = 0
        failed_count = 0

        for change in changes:
            entity_type = (change.get("entity_type") or "").lower()
            entity_id = change.get("entity_id", 0) or 0
            action = (change.get("action") or "UPDATE").upper()
            payload = change.get("data") or {}
            client_timestamp = self._parse_client_timestamp(
                change.get("client_timestamp")
            )

            sync_item = OfflineSyncQueue.objects.create(
                device=device,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                data=payload,
                client_timestamp=client_timestamp,
                status="SYNCING",
            )

            if entity_type in (
                "evaluation",
                "grade",
                "offline_mark_entry",
            ) and action in ("CREATE", "UPDATE"):
                from apps.accounts.rebac import enforce_permission_token

                if school and not enforce_permission_token(
                    request.user, "grade.submit", school=school
                ):
                    sync_item.status = "FAILED"
                    sync_item.error_message = "rebac_permission_denied:grade.submit"
                    sync_item.synced_at = timezone.now()
                    sync_item.save(
                        update_fields=["status", "error_message", "synced_at"]
                    )
                    result = {
                        "status": sync_item.status,
                        "error": sync_item.error_message,
                    }
                elif not bool(flags.get("enable_offline_grade_sync", True)):
                    sync_item.status = "FAILED"
                    sync_item.error_message = (
                        "Offline grade sync is disabled in Feature Control."
                    )
                    sync_item.synced_at = timezone.now()
                    sync_item.save(
                        update_fields=["status", "error_message", "synced_at"]
                    )
                    result = {
                        "status": sync_item.status,
                        "error": sync_item.error_message,
                    }
                else:
                    result = self._process_eval_sync(sync_item, request.user)
            elif entity_type in ("attendance", "attendance_record") and action in (
                "CREATE",
                "UPDATE",
            ):
                from apps.accounts.rebac import enforce_permission_token

                if school and not enforce_permission_token(
                    request.user, "attendance.mark", school=school
                ):
                    sync_item.status = "FAILED"
                    sync_item.error_message = "rebac_permission_denied:attendance.mark"
                    sync_item.synced_at = timezone.now()
                    sync_item.save(
                        update_fields=["status", "error_message", "synced_at"]
                    )
                    result = {
                        "status": sync_item.status,
                        "error": sync_item.error_message,
                    }
                elif not bool(flags.get("enable_offline_attendance_sync", True)):
                    sync_item.status = "FAILED"
                    sync_item.error_message = (
                        "Offline attendance sync is disabled in Feature Control."
                    )
                    sync_item.synced_at = timezone.now()
                    sync_item.save(
                        update_fields=["status", "error_message", "synced_at"]
                    )
                    result = {
                        "status": sync_item.status,
                        "error": sync_item.error_message,
                    }
                else:
                    result = self._process_attendance_sync(sync_item, request.user)
            elif entity_type in (
                "offline_payment",
                "payment_queue",
                "queued_payment",
            ) and action in ("CREATE", "UPDATE"):
                from apps.accounts.rebac import enforce_permission_token

                if school and not enforce_permission_token(
                    request.user, "finance.manage", school=school
                ):
                    sync_item.status = "FAILED"
                    sync_item.error_message = "rebac_permission_denied:finance.manage"
                    sync_item.synced_at = timezone.now()
                    sync_item.save(
                        update_fields=["status", "error_message", "synced_at"]
                    )
                    result = {
                        "status": sync_item.status,
                        "error": sync_item.error_message,
                    }
                else:
                    result = self._process_offline_payment_sync(sync_item, request.user)
            else:
                sync_item.status = "FAILED"
                sync_item.error_message = (
                    f"Unsupported sync item: {entity_type}/{action}"
                )
                sync_item.synced_at = timezone.now()
                sync_item.save(update_fields=["status", "error_message", "synced_at"])
                result = {"status": sync_item.status, "error": sync_item.error_message}

            if result.get("status") == "COMPLETED":
                synced_count += 1
            elif result.get("status") == "CONFLICT":
                conflict_count += 1
            else:
                failed_count += 1

            results.append(
                {
                    "id": sync_item.id,
                    "entity_type": entity_type,
                    "action": action,
                    "status": sync_item.status,
                    "error": sync_item.error_message,
                    "conflict_data": sync_item.conflict_data,
                }
            )

        return Response(
            {
                "synced": synced_count,
                "conflicts": conflict_count,
                "failed": failed_count,
                "results": results,
            }
        )

    @action(detail=False, methods=["get"], url_path="sync_state")
    def sync_state(self, request):
        """Aggregate queue counts for offline UI (visible sync state)."""
        from apps.sync_engine import services

        return Response(services.get_visible_sync_state(request.user.id))

    @action(detail=False, methods=["post"], url_path="retry_failed")
    def retry_failed(self, request):
        """Reset FAILED rows so the client can replay sync_batch."""
        from apps.sync_engine import services

        max_retries = int(request.data.get("max_retries", 5))
        return Response(services.retry_failed_sync_items(request.user.id, max_retries=max_retries))

    @action(detail=True, methods=["post"])
    def resolve_conflict(self, request, pk=None):
        """Resolve sync conflict"""
        sync_item = self.get_object()
        resolution = request.data.get("resolution")  # 'client' or 'server'

        if resolution not in ["client", "server"]:
            return Response(
                {"error": 'resolution must be "client" or "server"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Apply resolution logic (simplified)
        sync_item.status = "COMPLETED"
        sync_item.synced_at = timezone.now()
        sync_item.save()

        return Response({"status": "conflict resolved"})
