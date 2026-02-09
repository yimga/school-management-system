"""
Phase 9 Task 4: Scheduling System - Tests
Timetabling, room allocation, conflict detection tests
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import time

from apps.academics.scheduling import (
    Room,
    TimeSlot,
    TeacherAvailability,
    Schedule,
    ScheduleEntry,
    SchedulingConstraint,
    TimetableGenerator,
)

User = get_user_model()


class RoomTestCase(TestCase):
    """Test room model"""
    
    def test_create_room(self):
        """Test room creation"""
        room = Room.objects.create(
            name='Room 101',
            room_type='CLASSROOM',
            capacity=30,
            floor=1,
            facilities=['projector', 'whiteboard']
        )
        
        self.assertEqual(room.name, 'Room 101')
        self.assertEqual(room.capacity, 30)
        self.assertEqual(len(room.facilities), 2)
    
    def test_room_string_representation(self):
        """Test room __str__"""
        room = Room.objects.create(
            name='Lab 1',
            room_type='LAB',
            capacity=20
        )
        
        self.assertEqual(str(room), 'Lab 1 (LAB)')


class TimeSlotTestCase(TestCase):
    """Test time slot model"""
    
    def test_create_time_slot(self):
        """Test time slot creation"""
        slot = TimeSlot.objects.create(
            day_of_week=0,  # Monday
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name='Period 1'
        )
        
        self.assertEqual(slot.day_of_week, 0)
        self.assertEqual(slot.start_time, time(9, 0))
    
    def test_time_slot_validation(self):
        """Test time slot validation (start before end)"""
        slot = TimeSlot(
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(9, 0),  # Invalid: end before start
            slot_name='Invalid'
        )
        
        with self.assertRaises(ValidationError):
            slot.clean()


class TeacherAvailabilityTestCase(TestCase):
    """Test teacher availability"""
    
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher1',
            email='teacher1@example.com',
            password='password123'
        )
        self.time_slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name='Period 1'
        )
    
    def test_create_availability(self):
        """Test availability creation"""
        availability = TeacherAvailability.objects.create(
            teacher=self.teacher,
            time_slot=self.time_slot,
            is_available=True,
            preference_level=8
        )
        
        self.assertTrue(availability.is_available)
        self.assertEqual(availability.preference_level, 8)


class ScheduleTestCase(TestCase):
    """Test schedule model"""
    
    def setUp(self):
        from apps.academics.models import AcademicYear, Term
        
        self.user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password123'
        )
        
        self.academic_year = AcademicYear.objects.create(
            name='2024-2025',
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date()
        )
        
        self.term = Term.objects.create(
            name='Term 1',
            academic_year=self.academic_year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date()
        )
    
    def test_create_schedule(self):
        """Test schedule creation"""
        schedule = Schedule.objects.create(
            name='Term 1 Schedule',
            academic_year=self.academic_year,
            term=self.term,
            created_by=self.user
        )
        
        self.assertEqual(schedule.status, 'DRAFT')
        self.assertIsNone(schedule.published_at)
    
    def test_publish_schedule(self):
        """Test schedule publishing"""
        schedule = Schedule.objects.create(
            name='Term 1 Schedule',
            academic_year=self.academic_year,
            term=self.term,
            created_by=self.user
        )
        
        schedule.publish()
        
        self.assertEqual(schedule.status, 'PUBLISHED')
        self.assertIsNotNone(schedule.published_at)


class ScheduleEntryTestCase(TestCase):
    """Test schedule entry model"""
    
    def setUp(self):
        from apps.academics.models import AcademicYear, Term, Classroom, Subject, Department
        
        self.department = Department.objects.create(name="Science", code="SCI")
        
        self.user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password123'
        )
        
        self.teacher = User.objects.create_user(
            username='teacher1',
            email='teacher1@example.com',
            password='password123'
        )
        
        self.academic_year = AcademicYear.objects.create(
            name='2024-2025',
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date()
        )
        
        self.term = Term.objects.create(
            name='Term 1',
            academic_year=self.academic_year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date()
        )
        
        self.schedule = Schedule.objects.create(
            name='Term 1 Schedule',
            academic_year=self.academic_year,
            term=self.term,
            created_by=self.user
        )
        
        self.classroom = Classroom.objects.create(
            name='Class A',
            code='CLA',
            academic_year=self.academic_year,
            department=self.department,
        )
        
        self.subject = Subject.objects.create(
            name='Mathematics',
        )
        
        self.room = Room.objects.create(
            name='Room 101',
            room_type='CLASSROOM',
            capacity=30
        )
        
        self.time_slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name='Period 1'
        )
    
    def test_create_schedule_entry(self):
        """Test schedule entry creation"""
        entry = ScheduleEntry.objects.create(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.time_slot
        )
        
        self.assertFalse(entry.is_cancelled)
        self.assertEqual(entry.teacher, self.teacher)
    
    def test_teacher_conflict_detection(self):
        """Test teacher double-booking detection"""
        # Create first entry
        ScheduleEntry.objects.create(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.time_slot
        )
        
        # Try to create conflicting entry
        room2 = Room.objects.create(
            name='Room 102',
            room_type='CLASSROOM',
            capacity=30
        )
        
        entry2 = ScheduleEntry(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,  # Same teacher
            room=room2,
            time_slot=self.time_slot  # Same time slot
        )
        
        with self.assertRaises(ValidationError):
            entry2.clean()


class TimetableGeneratorTestCase(TestCase):
    """Test timetable generation"""
    
    def setUp(self):
        from apps.academics.models import AcademicYear, Term
        
        self.user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='password123'
        )
        
        self.academic_year = AcademicYear.objects.create(
            name='2024-2025',
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date()
        )
        
        self.term = Term.objects.create(
            name='Term 1',
            academic_year=self.academic_year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date()
        )
        
        self.generator = TimetableGenerator(self.academic_year, self.term)
    
    def test_generator_initialization(self):
        """Test generator initialization"""
        self.assertEqual(self.generator.academic_year, self.academic_year)
        self.assertEqual(self.generator.term, self.term)
    
    def test_load_constraints(self):
        """Test constraint loading"""
        SchedulingConstraint.objects.create(
            name='Max 6 daily lessons',
            constraint_type='MAX_DAILY_LESSONS',
            parameters={'max_lessons': 6},
            priority=8
        )
        
        self.generator.load_constraints()
        
        self.assertGreater(len(self.generator.constraints), 0)
    
    def test_check_teacher_availability(self):
        """Test teacher availability check"""
        teacher = User.objects.create_user(
            username='teacher1',
            email='teacher1@example.com',
            password='password123'
        )
        
        time_slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name='Period 1'
        )
        
        # No availability record means available by default
        is_available = self.generator.check_teacher_availability(teacher, time_slot)
        self.assertTrue(is_available)
        
        # Create unavailable record
        TeacherAvailability.objects.create(
            teacher=teacher,
            time_slot=time_slot,
            is_available=False
        )
        
        is_available = self.generator.check_teacher_availability(teacher, time_slot)
        self.assertFalse(is_available)
    
    def test_detect_conflicts(self):
        """Test conflict detection"""
        from apps.academics.models import Classroom, Subject, Department
        
        department = Department.objects.create(name="Science", code="SCI-CONFLICT")
        teacher = User.objects.create_user(
            username='teacher1',
            email='teacher1@example.com',
            password='password123'
        )
        
        classroom = Classroom.objects.create(
            name='Class A',
            code='CLA-CONFLICT',
            academic_year=self.academic_year,
            department=department,
        )
        
        subject = Subject.objects.create(
            name='Mathematics',
        )
        
        room = Room.objects.create(
            name='Room 101',
            room_type='CLASSROOM',
            capacity=30
        )
        
        time_slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
            slot_name='Period 1'
        )
        
        schedule = Schedule.objects.create(
            name='Test Schedule',
            academic_year=self.academic_year,
            term=self.term,
            created_by=self.user
        )
        
        # Create two entries with same teacher and time
        ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=classroom,
            subject=subject,
            teacher=teacher,
            room=room,
            time_slot=time_slot
        )
        
        # Force create second entry (bypass validation for test)
        ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=classroom,
            subject=subject,
            teacher=teacher,
            room=room,
            time_slot=time_slot
        )
        
        conflicts = self.generator.detect_conflicts(schedule)
        
        # Should detect conflicts
        self.assertGreater(len(conflicts), 0)
