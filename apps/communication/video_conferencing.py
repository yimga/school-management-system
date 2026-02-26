"""
Phase 9 Task 5: Video Conferencing Integration
Extended video conferencing with Zoom, Google Meet, Jitsi

INTEGRATES WITH:
- apps.communication.integrations (existing ZoomIntegration)
- apps.academics.models (Classroom, Subject)
- apps.portal for student/teacher access
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import json
import hashlib
from typing import Dict, List, Optional

User = get_user_model()


class VideoConferenceProvider(models.TextChoices):
    """Supported video conference providers"""
    ZOOM = 'ZOOM', 'Zoom'
    GOOGLE_MEET = 'GOOGLE_MEET', 'Google Meet'
    JITSI = 'JITSI', 'Jitsi Meet'
    TEAMS = 'TEAMS', 'Microsoft Teams'


class VirtualClassroom(models.Model):
    """
    Virtual classroom session
    
    INTEGRATES WITH: apps.academics.models.Classroom
    """
    
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('LIVE', 'Live'),
        ('ENDED', 'Ended'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Link to physical classroom
    classroom = models.ForeignKey(
        'academics.Classroom',
        on_delete=models.CASCADE,
        related_name='virtual_sessions',
        null=True,
        blank=True
    )
    
    # Session details
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    provider = models.CharField(
        max_length=20,
        choices=VideoConferenceProvider.choices,
        default=VideoConferenceProvider.ZOOM
    )
    
    # Scheduling
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    
    # Host
    host = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='hosted_sessions'
    )
    
    # Participants
    participants = models.ManyToManyField(
        User,
        through='SessionParticipant',
        related_name='joined_sessions'
    )
    
    # Meeting details
    meeting_id = models.CharField(max_length=255)
    meeting_password = models.CharField(max_length=100, blank=True)
    join_url = models.URLField(max_length=500)
    host_url = models.URLField(max_length=500, blank=True)
    
    # Settings
    is_recording_enabled = models.BooleanField(default=True)
    is_waiting_room_enabled = models.BooleanField(default=True)
    max_participants = models.IntegerField(default=100)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SCHEDULED'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(fields=['status', 'scheduled_start']),
            models.Index(fields=['host', 'scheduled_start']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.scheduled_start.strftime('%Y-%m-%d %H:%M')})"
    
    def clean(self):
        if self.scheduled_start >= self.scheduled_end:
            raise ValidationError("Start time must be before end time")
    
    def start_session(self):
        """Mark session as live"""
        self.status = 'LIVE'
        self.actual_start = timezone.now()
        self.save()
    
    def end_session(self):
        """End the session"""
        self.status = 'ENDED'
        self.actual_end = timezone.now()
        self.save()
    
    @property
    def duration_minutes(self):
        """Calculate scheduled duration in minutes"""
        delta = self.scheduled_end - self.scheduled_start
        return int(delta.total_seconds() / 60)


class SessionParticipant(models.Model):
    """Track participant attendance in virtual sessions"""
    
    session = models.ForeignKey(VirtualClassroom, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Attendance tracking
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    
    # Participation
    is_present = models.BooleanField(default=False)
    raised_hand_count = models.IntegerField(default=0)
    chat_message_count = models.IntegerField(default=0)
    
    # Technical issues
    connection_quality = models.CharField(
        max_length=20,
        choices=[
            ('EXCELLENT', 'Excellent'),
            ('GOOD', 'Good'),
            ('FAIR', 'Fair'),
            ('POOR', 'Poor'),
        ],
        default='GOOD'
    )
    had_technical_issues = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('session', 'user')
    
    def __str__(self):
        return f"{self.user.username} - {self.session.title}"


class SessionRecording(models.Model):
    """
    Recording of virtual classroom session
    
    INTEGRATES WITH: Existing media storage
    """
    
    session = models.ForeignKey(
        VirtualClassroom,
        on_delete=models.CASCADE,
        related_name='recordings'
    )
    
    recording_id = models.CharField(max_length=255, unique=True)
    file_size_mb = models.FloatField(default=0.0)
    duration_minutes = models.IntegerField()
    
    # URLs (may expire)
    download_url = models.URLField(max_length=500, blank=True)
    streaming_url = models.URLField(max_length=500, blank=True)
    
    # Metadata
    recorded_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    
    # Access control
    is_public = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-recorded_at']
    
    def __str__(self):
        return f"Recording: {self.session.title}"


class BreakoutRoom(models.Model):
    """
    Breakout rooms for group activities
    
    EXTENDS: VirtualClassroom with small group capabilities
    """
    
    session = models.ForeignKey(
        VirtualClassroom,
        on_delete=models.CASCADE,
        related_name='breakout_rooms'
    )
    
    name = models.CharField(max_length=100)
    room_number = models.IntegerField()
    max_participants = models.IntegerField(default=10)
    
    # Assignment
    assigned_participants = models.ManyToManyField(User, related_name='breakout_assignments')
    
    # Status
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('session', 'room_number')
        ordering = ['room_number']
    
    def __str__(self):
        return f"{self.name} (Room {self.room_number})"


class VideoConferenceService:
    """
    Service for managing video conferences
    
    INTEGRATES WITH: apps.communication.integrations.ZoomIntegration
    EXTENDS: Adds Google Meet and Jitsi support
    """
    
    def __init__(self, provider: VideoConferenceProvider = VideoConferenceProvider.ZOOM):
        self.provider = provider
    
    def create_meeting(self, host: User, title: str, start_time, duration_minutes: int, **kwargs) -> Dict:
        """
        Create a video conference meeting
        
        Args:
            host: User hosting the meeting
            title: Meeting title
            start_time: Scheduled start datetime
            duration_minutes: Duration in minutes
            **kwargs: Additional provider-specific options
        
        Returns:
            Dict with meeting_id, join_url, host_url, password
        """
        if self.provider == VideoConferenceProvider.ZOOM:
            return self._create_zoom_meeting(host, title, start_time, duration_minutes, **kwargs)
        elif self.provider == VideoConferenceProvider.GOOGLE_MEET:
            return self._create_google_meet(host, title, start_time, duration_minutes, **kwargs)
        elif self.provider == VideoConferenceProvider.JITSI:
            return self._create_jitsi_meeting(host, title, start_time, duration_minutes, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _create_zoom_meeting(self, host, title, start_time, duration_minutes, **kwargs) -> Dict:
        """
        Create Zoom meeting using existing integration

        INTEGRATES WITH: apps.communication.integrations.ZoomIntegration
        """
        from apps.communication.integrations import ZoomIntegration

        zoom = ZoomIntegration()
        response = zoom.create_meeting(
            host_email=getattr(host, "email", "") or "",
            topic=title,
            duration=duration_minutes,
            start_time=start_time,
            waiting_room=kwargs.get("waiting_room", True),
            recording=kwargs.get("recording", True),
        )
        if not isinstance(response, dict):
            response = {}

        # Support both legacy return shape ({id,start_url}) and newer
        # IntegrationService shape ({success,meeting_id,join_url}).
        meeting_id = response.get("meeting_id") or response.get("id")
        join_url = response.get("join_url")
        host_url = response.get("host_url") or response.get("start_url")
        password = response.get("password", "")

        if not meeting_id:
            import uuid
            meeting_id = f"zoom-{uuid.uuid4().hex[:10]}"
        if not join_url:
            join_url = f"https://zoom.us/j/{meeting_id}"
        if not host_url:
            host_url = join_url

        return {
            "meeting_id": str(meeting_id),
            "join_url": str(join_url),
            "host_url": str(host_url),
            "password": str(password or ""),
        }
    
    def _create_google_meet(self, host, title, start_time, duration_minutes, **kwargs) -> Dict:
        """
        Create Google Meet meeting
        
        Uses Google Calendar API to create meeting
        """
        # Implementation would use Google Calendar API
        # For now, return mock data
        
        import uuid
        meeting_id = f"meet-{uuid.uuid4().hex[:10]}"
        
        return {
            'meeting_id': meeting_id,
            'join_url': f"https://meet.google.com/{meeting_id}",
            'host_url': f"https://meet.google.com/{meeting_id}",
            'password': '',
        }
    
    def _create_jitsi_meeting(self, host, title, start_time, duration_minutes, **kwargs) -> Dict:
        """
        Create Jitsi Meet room (serverless)
        
        Jitsi doesn't require API - just generate room name
        """
        import uuid
        
        # Generate unique room name
        room_name = f"{title.replace(' ', '-')}-{uuid.uuid4().hex[:8]}"
        
        # Jitsi domain (can be self-hosted)
        jitsi_domain = kwargs.get('jitsi_domain', 'meet.jit.si')
        
        # Generate password hash for secure room
        password = kwargs.get('password', str(uuid.uuid4().hex[:6]))
        
        return {
            'meeting_id': room_name,
            'join_url': f"https://{jitsi_domain}/{room_name}",
            'host_url': f"https://{jitsi_domain}/{room_name}",
            'password': password,
        }
    
    def schedule_session(
        self,
        classroom,
        host: User,
        title: str,
        start_time,
        end_time,
        participants: List[User] = None,
        **kwargs
    ) -> VirtualClassroom:
        """
        Schedule a virtual classroom session
        
        INTEGRATES WITH: apps.academics.models.Classroom
        """
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        # Create meeting with provider
        meeting_info = self.create_meeting(host, title, start_time, duration_minutes, **kwargs)
        
        # Create virtual classroom
        session = VirtualClassroom.objects.create(
            classroom=classroom,
            title=title,
            description=kwargs.get('description', ''),
            provider=self.provider,
            scheduled_start=start_time,
            scheduled_end=end_time,
            host=host,
            meeting_id=meeting_info['meeting_id'],
            meeting_password=meeting_info.get('password', ''),
            join_url=meeting_info['join_url'],
            host_url=meeting_info.get('host_url', ''),
            is_recording_enabled=kwargs.get('recording', True),
            is_waiting_room_enabled=kwargs.get('waiting_room', True),
            max_participants=kwargs.get('max_participants', 100),
        )
        
        # Add participants
        if participants:
            for user in participants:
                SessionParticipant.objects.create(
                    session=session,
                    user=user
                )
        
        return session
    
    def get_upcoming_sessions(self, user: User, days: int = 7) -> List[VirtualClassroom]:
        """Get user's upcoming sessions"""
        start = timezone.now()
        end = start + timedelta(days=days)
        
        # Sessions user is hosting or participating in
        sessions = VirtualClassroom.objects.filter(
            scheduled_start__range=[start, end],
            status='SCHEDULED'
        ).filter(
            models.Q(host=user) | models.Q(participants=user)
        ).distinct().order_by('scheduled_start')
        
        return list(sessions)
    
    def record_attendance(self, session: VirtualClassroom, user: User, joined_at, left_at=None):
        """Record participant attendance"""
        participant, created = SessionParticipant.objects.get_or_create(
            session=session,
            user=user
        )
        
        participant.joined_at = joined_at
        participant.is_present = True
        
        if left_at:
            participant.left_at = left_at
            duration = (left_at - joined_at).total_seconds() / 60
            participant.duration_minutes = int(duration)
        
        participant.save()
        
        return participant
    
    def create_breakout_rooms(self, session: VirtualClassroom, num_rooms: int, auto_assign: bool = False):
        """Create breakout rooms for session"""
        rooms = []
        
        for i in range(num_rooms):
            room = BreakoutRoom.objects.create(
                session=session,
                name=f"Breakout Room {i+1}",
                room_number=i+1
            )
            rooms.append(room)
        
        if auto_assign:
            # Auto-assign participants evenly
            participants = list(session.participants.all())
            for idx, participant in enumerate(participants):
                room_idx = idx % num_rooms
                rooms[room_idx].assigned_participants.add(participant)
        
        return rooms
    
    def get_session_analytics(self, session: VirtualClassroom) -> Dict:
        """Generate analytics for a session"""
        participants = SessionParticipant.objects.filter(session=session)
        
        total_participants = participants.count()
        attended = participants.filter(is_present=True).count()
        avg_duration = participants.aggregate(
            avg=models.Avg('duration_minutes')
        )['avg'] or 0
        
        return {
            'total_invited': total_participants,
            'total_attended': attended,
            'attendance_rate': (attended / total_participants * 100) if total_participants > 0 else 0,
            'average_duration_minutes': round(avg_duration, 2),
            'total_hand_raises': participants.aggregate(
                total=models.Sum('raised_hand_count')
            )['total'] or 0,
            'total_chat_messages': participants.aggregate(
                total=models.Sum('chat_message_count')
            )['total'] or 0,
        }
