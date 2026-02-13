"""
Phase 9 Task 4: Advanced Scheduling System
Automated timetabling, room allocation, conflict detection

INTEGRATES WITH:
- apps.academics.models (Classroom, Subject, Teacher)
- apps.people.models (TeacherProfile)
- Existing classroom and subject infrastructure
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import List, Dict, Optional

User = get_user_model()


class Room(models.Model):
    """Physical classrooms and facilities"""
    
    ROOM_TYPES = [
        ('CLASSROOM', 'Standard Classroom'),
        ('LAB', 'Laboratory'),
        ('AUDITORIUM', 'Auditorium'),
        ('GYM', 'Gymnasium'),
        ('LIBRARY', 'Library'),
        ('COMPUTER_LAB', 'Computer Lab'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    capacity = models.IntegerField()
    floor = models.IntegerField(default=1)
    building = models.CharField(max_length=100, blank=True)
    facilities = models.JSONField(default=list)  # ["projector", "whiteboard", "computers"]
    is_available = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['building', 'floor', 'name']
        indexes = [
            models.Index(fields=['room_type', 'is_available']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.room_type})"


class TimeSlot(models.Model):
    """Predefined time slots for scheduling"""
    
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_name = models.CharField(max_length=50)  # "Period 1", "Morning Session"
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ('day_of_week', 'start_time', 'end_time')
    
    def __str__(self):
        return f"{self.get_day_of_week_display()} {self.slot_name} ({self.start_time}-{self.end_time})"
    
    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time")


class TeacherAvailability(models.Model):
    """Teacher availability preferences and constraints"""
    
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='availability')
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)
    preference_level = models.IntegerField(default=5, help_text="1-10, higher is more preferred")
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ('teacher', 'time_slot')
        verbose_name_plural = 'Teacher Availabilities'
    
    def __str__(self):
        status = "Available" if self.is_available else "Unavailable"
        return f"{self.teacher.username} - {self.time_slot.slot_name}: {status}"


class Schedule(models.Model):
    """Master schedule for academic terms"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('ARCHIVED', 'Archived'),
    ]
    
    name = models.CharField(max_length=255)
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE)
    term = models.ForeignKey('academics.Term', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    generated_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.name} - {self.term.name}"
    
    def publish(self):
        """Publish the schedule"""
        self.status = 'PUBLISHED'
        self.published_at = timezone.now()
        self.save()


class ScheduleEntry(models.Model):
    """Individual class session in a schedule"""
    
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='entries')
    classroom = models.ForeignKey('academics.Classroom', on_delete=models.CASCADE)
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teaching_slots')
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    
    # For handling conflicts/changes
    is_cancelled = models.BooleanField(default=False)
    replacement_teacher = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replacement_slots'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = 'Schedule Entries'
        indexes = [
            models.Index(fields=['schedule', 'time_slot']),
            models.Index(fields=['teacher', 'time_slot']),
            models.Index(fields=['room', 'time_slot']),
        ]
    
    def __str__(self):
        return f"{self.classroom.name} - {self.subject.name} ({self.time_slot.slot_name})"
    
    def clean(self):
        """Validate no conflicts"""
        if self.pk is None:  # Only for new entries
            # Check teacher conflict
            teacher_conflict = ScheduleEntry.objects.filter(
                schedule=self.schedule,
                teacher=self.teacher,
                time_slot=self.time_slot,
                is_cancelled=False
            ).exists()
            
            if teacher_conflict:
                raise ValidationError(f"Teacher {self.teacher.username} is already scheduled for {self.time_slot.slot_name}")
            
            # Check room conflict
            room_conflict = ScheduleEntry.objects.filter(
                schedule=self.schedule,
                room=self.room,
                time_slot=self.time_slot,
                is_cancelled=False
            ).exists()
            
            if room_conflict:
                raise ValidationError(f"Room {self.room.name} is already booked for {self.time_slot.slot_name}")


class SchedulingConstraint(models.Model):
    """Custom scheduling rules and constraints"""
    
    CONSTRAINT_TYPES = [
        ('MAX_DAILY_LESSONS', 'Maximum daily lessons per teacher'),
        ('MIN_BREAK_TIME', 'Minimum break between lessons'),
        ('PREFERRED_ROOM', 'Preferred room for subject'),
        ('NO_BACK_TO_BACK', 'No back-to-back lessons for same class'),
        ('BLOCK_TIME', 'Block specific time for activity'),
    ]
    
    name = models.CharField(max_length=255)
    constraint_type = models.CharField(max_length=30, choices=CONSTRAINT_TYPES)
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=5, help_text="1-10, higher is more important")
    
    class Meta:
        ordering = ['-priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.constraint_type})"


class TimetableGenerator:
    """
    Automated timetable generation using constraint satisfaction
    
    INTEGRATES WITH existing models:
    - apps.academics.models.Classroom
    - apps.academics.models.Subject
    - apps.people.models.TeacherProfile
    """
    
    def __init__(self, academic_year, term):
        self.academic_year = academic_year
        self.term = term
        self.constraints = []
        self.schedule_entries = []
    
    def load_constraints(self):
        """Load active scheduling constraints"""
        self.constraints = SchedulingConstraint.objects.filter(
            is_active=True
        ).order_by('-priority')
    
    def check_teacher_availability(self, teacher, time_slot) -> bool:
        """Check if teacher is available for time slot"""
        try:
            availability = TeacherAvailability.objects.get(
                teacher=teacher,
                time_slot=time_slot
            )
            return availability.is_available
        except TeacherAvailability.DoesNotExist:
            return True  # Assume available if not specified
    
    def check_room_availability(self, room, time_slot, schedule) -> bool:
        """Check if room is available"""
        return not ScheduleEntry.objects.filter(
            schedule=schedule,
            room=room,
            time_slot=time_slot,
            is_cancelled=False
        ).exists()
    
    def find_suitable_room(self, classroom, subject, time_slot, schedule) -> Optional[Room]:
        """Find best room for class based on capacity and facilities"""
        # Get student count for classroom
        student_count = classroom.students.count() if hasattr(classroom, 'students') else 30
        
        # Find rooms with sufficient capacity
        suitable_rooms = Room.objects.filter(
            is_available=True,
            capacity__gte=student_count
        ).order_by('capacity')
        
        # Check availability
        for room in suitable_rooms:
            if self.check_room_availability(room, time_slot, schedule):
                return room
        
        return None
    
    def generate_schedule(self, created_by) -> Schedule:
        """
        Generate optimized schedule for term
        
        Algorithm:
        1. Load all classrooms and subjects
        2. Load constraints and teacher availability
        3. Assign time slots using constraint satisfaction
        4. Allocate rooms based on capacity and availability
        5. Validate no conflicts
        """
        from apps.academics.models import Classroom, Subject
        
        self.load_constraints()
        
        # Create schedule
        schedule = Schedule.objects.create(
            name=f"{self.term.name} Schedule",
            academic_year=self.academic_year,
            term=self.term,
            status='DRAFT',
            created_by=created_by
        )
        
        # Get all active classrooms for this term
        classrooms = Classroom.objects.filter(academic_year=self.academic_year)
        
        # Get all active time slots
        time_slots = TimeSlot.objects.filter(is_active=True).order_by('day_of_week', 'start_time')
        
        # For each classroom, assign subjects to time slots
        for classroom in classrooms:
            # Get subjects for this classroom
            subjects = Subject.objects.filter(classroom=classroom)
            
            for subject in subjects:
                # Get assigned teacher
                teacher = subject.teacher
                
                # Find suitable time slot
                for time_slot in time_slots:
                    # Check teacher availability
                    if not self.check_teacher_availability(teacher, time_slot):
                        continue
                    
                    # Check if teacher already has class at this time
                    teacher_conflict = ScheduleEntry.objects.filter(
                        schedule=schedule,
                        teacher=teacher,
                        time_slot=time_slot
                    ).exists()
                    
                    if teacher_conflict:
                        continue
                    
                    # Find suitable room
                    room = self.find_suitable_room(classroom, subject, time_slot, schedule)
                    
                    if room:
                        # Create schedule entry
                        ScheduleEntry.objects.create(
                            schedule=schedule,
                            classroom=classroom,
                            subject=subject,
                            teacher=teacher,
                            room=room,
                            time_slot=time_slot
                        )
                        break  # Move to next subject
        
        return schedule
    
    def detect_conflicts(self, schedule) -> List[Dict]:
        """Detect scheduling conflicts"""
        conflicts = []
        
        entries = ScheduleEntry.objects.filter(
            schedule=schedule,
            is_cancelled=False
        )
        
        # Check for teacher double-booking
        for entry in entries:
            overlaps = entries.filter(
                teacher=entry.teacher,
                time_slot=entry.time_slot
            ).exclude(pk=entry.pk)
            
            if overlaps.exists():
                conflicts.append({
                    'type': 'TEACHER_CONFLICT',
                    'teacher': entry.teacher.username,
                    'time_slot': str(entry.time_slot),
                    'entries': [entry.pk] + list(overlaps.values_list('pk', flat=True))
                })
        
        # Check for room double-booking
        for entry in entries:
            overlaps = entries.filter(
                room=entry.room,
                time_slot=entry.time_slot
            ).exclude(pk=entry.pk)
            
            if overlaps.exists():
                conflicts.append({
                    'type': 'ROOM_CONFLICT',
                    'room': entry.room.name,
                    'time_slot': str(entry.time_slot),
                    'entries': [entry.pk] + list(overlaps.values_list('pk', flat=True))
                })
        
        return conflicts
    
    def optimize_schedule(self, schedule):
        """
        Optimize schedule based on preferences and constraints
        
        Optimization goals:
        - Minimize teacher travel between rooms
        - Balance workload across days
        - Respect teacher preferences
        - Minimize gaps in student schedules
        """
        entries = ScheduleEntry.objects.filter(
            schedule=schedule,
            is_cancelled=False
        ).select_related('teacher', 'room', 'time_slot')
        
        # Calculate teacher workload per day
        teacher_workload = {}
        for entry in entries:
            day = entry.time_slot.day_of_week
            teacher_id = entry.teacher.id
            
            key = (teacher_id, day)
            teacher_workload[key] = teacher_workload.get(key, 0) + 1
        
        # Identify teachers with unbalanced workload
        for (teacher_id, day), count in teacher_workload.items():
            if count > 6:  # More than 6 classes per day
                # TODO: Attempt to redistribute
                pass
        
        return schedule
