"""
Communication API Views
Messages, Announcements, and Communication management endpoints
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime, timedelta

from apps.api.permissions import IsAdminUser, IsTeacherOrAdmin


class MessageViewSet(viewsets.ModelViewSet):
    """
    Internal messaging API
    
    Send, retrieve, and manage messages between users
    Support for threads, archiving, and filtering
    """
    permission_classes = [IsAuthenticated]
    filterset_fields = ['recipient', 'sender', 'is_read', 'created_at']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        from apps.communication.models import Message
        
        user = self.request.user
        return Message.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).select_related('sender', 'recipient')
    
    def list(self, request, *args, **kwargs):
        """
        List messages
        
        Query Parameters:
        - folder: inbox, sent, archive
        - unread_only: true/false
        - from_user: filter by sender
        - search: search in subject/body
        """
        queryset = self.get_queryset()
        
        folder = request.query_params.get('folder', 'inbox')
        if folder == 'inbox':
            queryset = queryset.filter(recipient=request.user)
        elif folder == 'sent':
            queryset = queryset.filter(sender=request.user)
        elif folder == 'archive':
            queryset = queryset.filter(is_archived=True)
        
        unread_only = request.query_params.get('unread_only', 'false').lower() == 'true'
        if unread_only:
            queryset = queryset.filter(is_read=False)
        
        from_user = request.query_params.get('from_user')
        if from_user:
            queryset = queryset.filter(sender_id=from_user)
        
        search_term = request.query_params.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(subject__icontains=search_term) |
                Q(body__icontains=search_term)
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
        Send a new message
        
        Request Body:
        {
            "recipient": 1,
            "subject": "Important Update",
            "body": "Please see the attached document",
            "priority": "normal"
        }
        """
        from apps.communication.models import Message
        
        recipient_id = request.data.get('recipient')
        subject = request.data.get('subject')
        body = request.data.get('body')
        
        if not all([recipient_id, subject, body]):
            return Response(
                {'error': 'recipient, subject, and body are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        message = Message.objects.create(
            sender=request.user,
            recipient_id=recipient_id,
            subject=subject,
            body=body
        )
        
        from apps.api.serializers import MessageSerializer
        serializer = MessageSerializer(message)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a message as read"""
        from apps.communication.models import Message
        
        message = Message.objects.get(pk=pk)
        
        if message.recipient != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.is_read = True
        message.save()
        
        return Response({'status': 'success', 'is_read': True})
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a message"""
        from apps.communication.models import Message
        
        message = Message.objects.get(pk=pk)
        
        if message.recipient != request.user and message.sender != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.is_archived = True
        message.save()
        
        return Response({'status': 'success', 'is_archived': True})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all unread messages as read"""
        from apps.communication.models import Message
        
        count = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        
        return Response({
            'status': 'success',
            'marked_as_read': count
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread messages"""
        from apps.communication.models import Message
        
        count = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['get'])
    def conversations(self, request):
        """Get list of unique conversations"""
        from apps.communication.models import Message
        from django.contrib.auth.models import User
        
        messages = self.get_queryset()
        
        conversation_users = set()
        for msg in messages:
            if msg.sender == request.user:
                conversation_users.add(msg.recipient_id)
            else:
                conversation_users.add(msg.sender_id)
        
        users = User.objects.filter(id__in=conversation_users).values(
            'id', 'first_name', 'last_name'
        )
        
        conversations = []
        for user_data in users:
            user_id = user_data['id']
            user_messages = Message.objects.filter(
                Q(sender=request.user, recipient_id=user_id) |
                Q(sender_id=user_id, recipient=request.user)
            ).order_by('-created_at')
            
            if user_messages.exists():
                latest = user_messages.first()
                unread_count = Message.objects.filter(
                    sender_id=user_id,
                    recipient=request.user,
                    is_read=False
                ).count()
                
                conversations.append({
                    'user_id': user_id,
                    'name': f"{user_data['first_name']} {user_data['last_name']}",
                    'last_message': latest.body[:100],
                    'last_message_time': latest.created_at,
                    'unread_count': unread_count
                })
        
        return Response({
            'total_conversations': len(conversations),
            'conversations': sorted(
                conversations,
                key=lambda x: x['last_message_time'],
                reverse=True
            )
        })


class AnnouncementViewSet(viewsets.ModelViewSet):
    """
    School announcements API
    
    Create, retrieve, and manage school announcements
    Filter by audience, type, and date
    """
    permission_classes = [IsAuthenticated]
    filterset_fields = ['audience', 'announcement_type', 'is_active', 'created_by']
    ordering_fields = ['created_at', 'expiry_date']
    ordering = ['-created_at']
    
    def get_queryset(self):
        from apps.communication.models import Announcement
        
        return Announcement.objects.filter(
            is_active=True,
            expiry_date__gte=timezone.now()
        ).select_related('created_by')
    
    def create(self, request, *args, **kwargs):
        """
        Create a new announcement
        
        Requires: Admin or Teacher role
        
        Request Body:
        {
            "title": "School Closed Tomorrow",
            "content": "Due to holiday...",
            "announcement_type": "general",
            "audience": "all_parents",
            "expiry_date": "2025-02-22"
        }
        """
        if not (request.user.is_staff or request.user.role in ['ADMIN', 'TEACHER', 'HOD']):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.communication.models import Announcement
        
        announcement = Announcement.objects.create(
            title=request.data.get('title'),
            content=request.data.get('content'),
            announcement_type=request.data.get('announcement_type', 'general'),
            audience=request.data.get('audience', 'all'),
            created_by=request.user
        )
        
        if 'expiry_date' in request.data:
            announcement.expiry_date = request.data.get('expiry_date')
            announcement.save()
        
        from apps.api.serializers import AnnouncementSerializer
        serializer = AnnouncementSerializer(announcement)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active announcements for current user"""
        from apps.communication.models import Announcement
        
        user = request.user
        
        now = timezone.now()
        announcements = Announcement.objects.filter(
            is_active=True,
            expiry_date__gte=now
        ).order_by('-created_at')
        
        if user.role == 'STUDENT':
            announcements = announcements.filter(
                Q(audience='all') | Q(audience='students')
            )
        elif user.role == 'PARENT':
            announcements = announcements.filter(
                Q(audience='all') | Q(audience='all_parents')
            )
        elif user.role == 'TEACHER':
            announcements = announcements.filter(
                Q(audience='all') | Q(audience='staff') | Q(audience='teachers')
            )
        
        from apps.api.serializers import AnnouncementSerializer
        serializer = AnnouncementSerializer(announcements[:10], many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an announcement"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from apps.communication.models import Announcement
        
        announcement = Announcement.objects.get(pk=pk)
        announcement.is_active = False
        announcement.save()
        
        return Response({'status': 'success', 'is_active': False})


class BroadcastAPI(APIView):
    """
    Send broadcast messages to groups
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        """
        Send message to multiple recipients
        
        Request Body:
        {
            "recipients": [1, 2, 3],
            "recipient_type": "user_ids",
            "subject": "Important Notice",
            "body": "Please read carefully",
            "recipient_group": "all_teachers"  # Alternative to recipients list
        }
        """
        from apps.communication.models import Message
        from django.contrib.auth.models import User
        
        recipient_ids = request.data.get('recipients', [])
        recipient_group = request.data.get('recipient_group')
        subject = request.data.get('subject')
        body = request.data.get('body')
        
        if not all([subject, body]):
            return Response(
                {'error': 'subject and body are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if recipient_group:
            if recipient_group == 'all_teachers':
                users = User.objects.filter(role='TEACHER')
            elif recipient_group == 'all_students':
                users = User.objects.filter(role='STUDENT')
            elif recipient_group == 'all_parents':
                users = User.objects.filter(role='PARENT')
            elif recipient_group == 'all':
                users = User.objects.all()
            else:
                users = User.objects.none()
            
            recipient_ids = users.values_list('id', flat=True)
        
        messages_created = 0
        for recipient_id in recipient_ids:
            try:
                Message.objects.create(
                    sender=request.user,
                    recipient_id=recipient_id,
                    subject=subject,
                    body=body
                )
                messages_created += 1
            except Exception as e:
                continue
        
        return Response({
            'status': 'success',
            'messages_sent': messages_created,
            'recipients': len(recipient_ids)
        }, status=status.HTTP_201_CREATED)


class CommunicationAnalyticsAPI(APIView):
    """
    Communication statistics and analytics
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        """Get communication analytics"""
        from apps.communication.models import Message, Announcement
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        messages_total = Message.objects.count()
        messages_this_week = Message.objects.filter(created_at__gte=week_ago).count()
        messages_this_month = Message.objects.filter(created_at__gte=month_ago).count()
        
        unread_messages = Message.objects.filter(is_read=False).count()
        
        active_announcements = Announcement.objects.filter(
            is_active=True,
            expiry_date__gte=now
        ).count()
        
        most_active_users = Message.objects.values('sender__first_name', 'sender__last_name').annotate(
            message_count=Count('id')
        ).order_by('-message_count')[:10]
        
        return Response({
            'total_messages': messages_total,
            'messages_this_week': messages_this_week,
            'messages_this_month': messages_this_month,
            'unread_messages': unread_messages,
            'active_announcements': active_announcements,
            'most_active_users': list(most_active_users),
            'average_response_time': 'N/A'
        })
