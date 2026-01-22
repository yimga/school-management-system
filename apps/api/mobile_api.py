"""
Phase 9 Task 2: Mobile API Layer
REST API for mobile applications with authentication, rate limiting, offline support
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
import uuid

User = get_user_model()


class MobileDevice(models.Model):
    """Track mobile devices for push notifications"""
    
    PLATFORM_CHOICES = [
        ('IOS', 'iOS'),
        ('ANDROID', 'Android'),
        ('WEB', 'Web'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mobile_devices')
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
        ordering = ['-last_active']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['device_id']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name} ({self.platform})"


class APIAccessLog(models.Model):
    """Log API access for monitoring and rate limiting"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    device = models.ForeignKey(MobileDevice, on_delete=models.SET_NULL, null=True, blank=True)
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
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['endpoint', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
        ]


class PushNotification(models.Model):
    """Push notifications to mobile devices"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('DELIVERED', 'Delivered'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
    ]
    
    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='NORMAL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.device.user.username}"


class OfflineSyncQueue(models.Model):
    """Queue for offline data synchronization"""
    
    SYNC_STATUS = [
        ('PENDING', 'Pending'),
        ('SYNCING', 'Syncing'),
        ('COMPLETED', 'Completed'),
        ('CONFLICT', 'Conflict'),
        ('FAILED', 'Failed'),
    ]
    
    device = models.ForeignKey(MobileDevice, on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=100)  # e.g., 'evaluation', 'attendance'
    entity_id = models.IntegerField()
    action = models.CharField(max_length=20)  # CREATE, UPDATE, DELETE
    data = models.JSONField()
    client_timestamp = models.DateTimeField()
    status = models.CharField(max_length=20, choices=SYNC_STATUS, default='PENDING')
    conflict_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['device', 'status']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]
    
    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} - {self.action} ({self.status})"


class MobileRateThrottle(UserRateThrottle):
    """Custom rate limiting for mobile API"""
    rate = '100/hour'


class MobileAnonRateThrottle(AnonRateThrottle):
    """Rate limiting for anonymous mobile requests"""
    rate = '20/hour'


class MobileAPIPermission(permissions.BasePermission):
    """Permission class for mobile API endpoints"""
    
    def has_permission(self, request, view):
        # Require authentication
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user has mobile API access
        return hasattr(request.user, 'mobile_devices') and \
               request.user.mobile_devices.filter(is_active=True).exists()


# Serializers

class MobileDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileDevice
        fields = ['device_id', 'device_name', 'platform', 'app_version', 
                 'os_version', 'is_active', 'last_active', 'registered_at']
        read_only_fields = ['device_id', 'last_active', 'registered_at']


class PushNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushNotification
        fields = ['id', 'title', 'body', 'data', 'priority', 'status', 
                 'sent_at', 'delivered_at', 'created_at']
        read_only_fields = ['id', 'status', 'sent_at', 'delivered_at', 'created_at']


class OfflineSyncQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineSyncQueue
        fields = ['id', 'entity_type', 'entity_id', 'action', 'data', 
                 'client_timestamp', 'status', 'conflict_data', 'synced_at']
        read_only_fields = ['id', 'status', 'conflict_data', 'synced_at']


# ViewSets

class MobileDeviceViewSet(viewsets.ModelViewSet):
    """Mobile device registration and management"""
    
    serializer_class = MobileDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]
    
    def get_queryset(self):
        return MobileDevice.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def update_push_token(self, request, pk=None):
        """Update device push notification token"""
        device = self.get_object()
        push_token = request.data.get('push_token')
        
        if not push_token:
            return Response(
                {'error': 'push_token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        device.push_token = push_token
        device.save()
        
        return Response({'status': 'token updated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate device"""
        device = self.get_object()
        device.is_active = False
        device.save()
        
        return Response({'status': 'device deactivated'})


class PushNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """View push notifications"""
    
    serializer_class = PushNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]
    
    def get_queryset(self):
        return PushNotification.objects.filter(
            device__user=self.request.user
        ).order_by('-created_at')[:50]
    
    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        """Mark notification as delivered"""
        notification = self.get_object()
        notification.status = 'DELIVERED'
        notification.delivered_at = timezone.now()
        notification.save()
        
        return Response({'status': 'marked delivered'})


class OfflineSyncViewSet(viewsets.ModelViewSet):
    """Offline data synchronization"""
    
    serializer_class = OfflineSyncQueueSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [MobileRateThrottle]
    
    def get_queryset(self):
        return OfflineSyncQueue.objects.filter(
            device__user=self.request.user,
            status__in=['PENDING', 'CONFLICT']
        )
    
    def perform_create(self, serializer):
        """Queue offline changes for sync"""
        device_id = self.request.data.get('device_id')
        
        try:
            device = MobileDevice.objects.get(
                device_id=device_id,
                user=self.request.user
            )
        except MobileDevice.DoesNotExist:
            return Response(
                {'error': 'Invalid device_id'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer.save(device=device)
    
    @action(detail=False, methods=['post'])
    def sync_batch(self, request):
        """Sync batch of offline changes"""
        changes = request.data.get('changes', [])
        device_id = request.data.get('device_id')
        
        if not device_id:
            return Response(
                {'error': 'device_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            device = MobileDevice.objects.get(
                device_id=device_id,
                user=request.user
            )
        except MobileDevice.DoesNotExist:
            return Response(
                {'error': 'Invalid device_id'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        for change in changes:
            sync_item = OfflineSyncQueue.objects.create(
                device=device,
                entity_type=change['entity_type'],
                entity_id=change['entity_id'],
                action=change['action'],
                data=change['data'],
                client_timestamp=change['client_timestamp']
            )
            
            # Process sync (simplified - implement actual sync logic)
            sync_item.status = 'COMPLETED'
            sync_item.synced_at = timezone.now()
            sync_item.save()
            
            results.append({
                'id': sync_item.id,
                'status': sync_item.status
            })
        
        return Response({'synced': len(results), 'results': results})
    
    @action(detail=True, methods=['post'])
    def resolve_conflict(self, request, pk=None):
        """Resolve sync conflict"""
        sync_item = self.get_object()
        resolution = request.data.get('resolution')  # 'client' or 'server'
        
        if resolution not in ['client', 'server']:
            return Response(
                {'error': 'resolution must be "client" or "server"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Apply resolution logic (simplified)
        sync_item.status = 'COMPLETED'
        sync_item.synced_at = timezone.now()
        sync_item.save()
        
        return Response({'status': 'conflict resolved'})
