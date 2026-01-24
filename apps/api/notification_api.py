# apps/api/notification_api.py
"""
Notification Management APIs
Location: apps/api/notification_api.py

Handle all notification-related endpoints
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


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
        ).order_by('-created_at')
    
    def list(self, request):
        """List notifications with filtering"""
        queryset = self.get_queryset()
        
        notif_type = request.query_params.get('type')
        if notif_type:
            queryset = queryset.filter(severity=notif_type)
        
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        queryset = queryset.filter(created_at__gte=start_date)
        
        data = []
        for notif in queryset[:50]:
            notif_type = "message"
            if notif.severity == "ALERT":
                notif_type = "alert"
            elif notif.severity == "WARNING":
                notif_type = "task"
            data.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'severity': notif.severity,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'link': notif.link,
                'type': notif_type,
                'category': notif.severity.title()
            })
        
        return Response({
            'count': len(data),
            'results': data,
            'notifications': data,
            'unread': len([n for n in data if not n['is_read']])
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        from apps.finance.models import Notification
        
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_queryset().filter(pk=pk).first()
        if not notification:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])

        return Response({'status': 'success', 'notification_id': notification.id})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        from apps.finance.models import Notification
        
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        
        return Response({
            'status': 'success',
            'marked_as_read': count
        })
