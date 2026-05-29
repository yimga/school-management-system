# apps/api/notification_api.py
"""
Notification Management APIs
Location: apps/api/notification_api.py

Handle all notification-related endpoints
"""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Notifications"],
        summary="List notifications for the caller",
        description=(
            "Return up to 50 most-recent notifications the caller is the "
            "recipient of (or created). Filterable by severity, read state, and "
            "rolling day window."
        ),
        parameters=[
            OpenApiParameter(name="type", type=str, location=OpenApiParameter.QUERY, required=False, description="Filter by severity (ALERT / WARNING / INFO)."),
            OpenApiParameter(name="is_read", type=bool, location=OpenApiParameter.QUERY, required=False, description="Filter by read-state."),
            OpenApiParameter(name="days", type=int, location=OpenApiParameter.QUERY, required=False, description="Rolling window in days (default 7)."),
        ],
        request=None,
        responses={
            200: inline_serializer(
                name="NotificationListResponse",
                fields={
                    "count": serializers.IntegerField(),
                    "results": serializers.ListField(child=serializers.DictField()),
                    "notifications": serializers.ListField(child=serializers.DictField()),
                    "unread": serializers.IntegerField(),
                },
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
    unread_count=extend_schema(
        tags=["Notifications"],
        summary="Get the caller's unread notification count",
        request=None,
        responses={200: inline_serializer(name="UnreadCountResponse", fields={"unread_count": serializers.IntegerField()})},
    ),
    read=extend_schema(
        tags=["Notifications"],
        summary="Mark a notification as read",
        request=None,
        responses={
            200: inline_serializer(name="NotificationReadResponse", fields={"status": serializers.CharField(), "notification_id": serializers.IntegerField()}),
            404: OpenApiResponse(description="Notification not found"),
        },
    ),
    mark_all_read=extend_schema(
        tags=["Notifications"],
        summary="Mark all of the caller's notifications as read",
        request=None,
        responses={200: inline_serializer(name="MarkAllReadResponse", fields={"status": serializers.CharField(), "marked_as_read": serializers.IntegerField()})},
    ),
)
class NotificationViewSet(viewsets.ViewSet):
    """
    Notification API with filtering and bulk actions

    Endpoints:
    - GET /api/notifications/  - List all
    - POST /api/notifications/mark-all-read/  - Mark all as read
    - GET /api/notifications/unread-count/  - Count unread
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get notifications"""
        from apps.finance.models import Notification

        user = self.request.user
        return Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).order_by("-created_at")

    def list(self, request):
        """List notifications with filtering"""
        queryset = self.get_queryset()

        notif_type = request.query_params.get("type")
        if notif_type:
            queryset = queryset.filter(severity=notif_type)

        is_read = request.query_params.get("is_read")
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == "true")

        days = int(request.query_params.get("days", 7))
        start_date = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(created_at__gte=start_date)

        data = []
        for notif in queryset[:50]:
            notif_type = "message"
            if notif.severity == "ALERT":
                notif_type = "alert"
            elif notif.severity == "WARNING":
                notif_type = "task"
            data.append(
                {
                    "id": notif.id,
                    "title": notif.title,
                    "message": notif.message,
                    "severity": notif.severity,
                    "is_read": notif.is_read,
                    "created_at": notif.created_at.isoformat(),
                    "link": notif.link,
                    "type": notif_type,
                    "category": notif.severity.title(),
                }
            )

        return Response(
            {
                "count": len(data),
                "results": data,
                "notifications": data,
                "unread": len([n for n in data if not n["is_read"]]),
            }
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get count of unread notifications"""

        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread_count": count})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_queryset().filter(pk=pk).first()
        if not notification:
            return Response(
                {"error": "Notification not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])

        return Response({"status": "success", "notification_id": notification.id})

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        """Mark all notifications as read"""

        count = self.get_queryset().filter(is_read=False).update(is_read=True)

        return Response({"status": "success", "marked_as_read": count})

    @action(detail=False, methods=["post"], url_path="self-capture")
    def self_capture(self, request):
        """
        Persist a client-side toast/snackbar as a Notification record so
        bottom-of-screen flashes land in the user's notifications inbox
        instead of disappearing.

        Body: { "title": str, "message": str, "type": "success|error|warning|info", "link": optional }

        v4.00.25 (2026-05-29) — added to support the UX directive that
        bottom-of-screen toasts should be suppressed and routed into the
        notifications page.
        """
        from apps.finance.models import Notification

        title = (request.data.get("title") or "").strip()[:200]
        message = (request.data.get("message") or "").strip()[:2000]
        toast_type = (request.data.get("type") or "info").strip().lower()
        link = (request.data.get("link") or "").strip()[:500] or None

        if not message:
            return Response(
                {"status": "error", "detail": "message required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        severity_map = {
            "success": "INFO",
            "info": "INFO",
            "warning": "WARNING",
            "error": "ALERT",
        }
        severity = severity_map.get(toast_type, "INFO")

        if not title:
            title = {
                "INFO": "Update",
                "WARNING": "Heads up",
                "ALERT": "Attention",
            }.get(severity, "Notice")

        notification = Notification.objects.create(
            title=title,
            message=message,
            severity=severity,
            recipient=request.user,
            created_by=request.user,
            link=link or "",
        )

        return Response(
            {
                "status": "success",
                "notification_id": notification.id,
                "severity": severity,
            },
            status=status.HTTP_201_CREATED,
        )
