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
        return Notification.objects.all().order_by('-created_at')
    
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
            data.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'severity': notif.severity,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'link': notif.link
            })
        
        return Response({
            'count': len(data),
            'results': data,
            'unread': len([n for n in data if not n['is_read']])
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        from apps.finance.models import Notification
        
        count = Notification.objects.filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        from apps.finance.models import Notification
        
        count = Notification.objects.filter(is_read=False).update(is_read=True)
        
        return Response({
            'status': 'success',
            'marked_as_read': count
        })
