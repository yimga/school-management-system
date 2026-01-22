# apps/api/serializers.py
"""
Central serializers for all API endpoints
Location: apps/api/serializers.py
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.people.models import StudentProfile, TeacherProfile
from apps.finance.models import Invoice, Payment
from apps.academics.models import Attendance, ClassRoom
from apps.communication.models import Message, Notification

User = get_user_model()


# ==================== AUTH SERIALIZERS ====================

class UserSerializer(serializers.ModelSerializer):
    """User profile serializer"""
    profile_photo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'profile_photo', 'profile_photo_url', 'is_staff',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
    
    def get_profile_photo_url(self, obj):
        if obj.profile_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
        return None


# ==================== STUDENT SERIALIZERS ====================

class StudentProfileSerializer(serializers.ModelSerializer):
    """Student profile with user details"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StudentProfile
        fields = [
            'id', 'user', 'student_id', 'current_class', 'date_of_birth',
            'gender', 'is_active', 'admission_date'
        ]


class StudentSimpleSerializer(serializers.ModelSerializer):
    """Simplified student info"""
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = StudentProfile
        fields = ['id', 'student_id', 'full_name', 'current_class']


# ==================== TEACHER SERIALIZERS ====================

class TeacherProfileSerializer(serializers.ModelSerializer):
    """Teacher profile with user details"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = TeacherProfile
        fields = [
            'id', 'user', 'staff_id', 'subject', 'department',
            'qualification', 'is_active', 'hire_date'
        ]


# ==================== FINANCE SERIALIZERS ====================

class InvoiceSerializer(serializers.ModelSerializer):
    """Invoice with student details"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    student_id = serializers.CharField(source='student.student_id', read_only=True)
    paid_amount = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'student', 'student_name', 'student_id',
            'amount', 'paid_amount', 'balance', 'status',
            'due_date', 'invoice_date', 'description'
        ]
    
    def get_paid_amount(self, obj):
        return obj.payment_set.filter(status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    def get_balance(self, obj):
        paid = obj.payment_set.filter(status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        return obj.amount - paid


class PaymentSerializer(serializers.ModelSerializer):
    """Payment recording"""
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'amount', 'payment_method',
            'status', 'payment_date', 'reference_number'
        ]


# ==================== ACADEMIC SERIALIZERS ====================

class AttendanceSerializer(serializers.ModelSerializer):
    """Attendance record"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    class_name = serializers.CharField(source='classroom.name', read_only=True)
    
    class Meta:
        model = Attendance
        fields = ['id', 'student', 'student_name', 'classroom', 'class_name', 'date', 'status']


class ClassRoomSerializer(serializers.ModelSerializer):
    """Classroom/Class info"""
    student_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ClassRoom
        fields = ['id', 'name', 'code', 'level', 'capacity', 'student_count']
    
    def get_student_count(self, obj):
        return obj.student_set.filter(is_active=True).count()


# ==================== COMMUNICATION SERIALIZERS ====================

class NotificationSerializer(serializers.ModelSerializer):
    """Notification with user context"""
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'type', 'category',
            'is_read', 'created_at', 'link', 'priority'
        ]


class MessageSerializer(serializers.ModelSerializer):
    """Message between users"""
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'sender_name', 'recipient',
            'recipient_name', 'subject', 'body', 'is_read',
            'is_archived', 'created_at'
        ]


# ==================== DASHBOARD SERIALIZERS ====================

class DashboardStatSerializer(serializers.Serializer):
    """Generic dashboard stat"""
    label = serializers.CharField()
    value = serializers.IntegerField()
    change_percent = serializers.FloatField(required=False)
    icon = serializers.CharField(required=False)


class AdminDashboardOverviewSerializer(serializers.Serializer):
    """Admin dashboard overview"""
    total_students = serializers.IntegerField()
    total_teachers = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    attendance_rate = serializers.FloatField()
    active_users_today = serializers.IntegerField()
    system_health = serializers.CharField()
    last_updated = serializers.DateTimeField()


class TeacherDashboardSerializer(serializers.Serializer):
    """Teacher dashboard summary"""
    my_students = serializers.IntegerField()
    my_classes = serializers.IntegerField()
    pending_grades = serializers.IntegerField()
    ungraded_submissions = serializers.IntegerField()
    class_average = serializers.FloatField()


class ParentDashboardSerializer(serializers.Serializer):
    """Parent dashboard summary"""
    children_count = serializers.IntegerField()
    total_pending_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    messages_unread = serializers.IntegerField()
    upcoming_events = serializers.IntegerField()


class StudentDashboardSerializer(serializers.Serializer):
    """Student dashboard summary"""
    attendance_percentage = serializers.FloatField()
    average_grade = serializers.FloatField()
    pending_assignments = serializers.IntegerField()
    current_classes = serializers.IntegerField()
