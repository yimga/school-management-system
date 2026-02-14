# apps/api/serializers.py
"""Shared serializers for API endpoints (CRUD + dashboard DTOs)."""
from django.contrib.auth import get_user_model
from django.db import models
from rest_framework import serializers

from apps.academics.models import Classroom
from apps.communication.models import Announcement, Message
from apps.finance.models import Invoice, Notification, Payment
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile

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
    """CRUD serializer for student profiles (frontend DTO)."""

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "student_code",
            "admission_number",
            "gender",
            "date_of_birth",
            "place_of_birth",
            "status",
            "joined_term",
            "joined_date",
            "section",
            "parent_phone",
            "referral_code",
            "academic_year",
            "classroom",
            "specialty",
            "exam_candidate_number",
            "exam_center_code",
            "exam_system",
            "is_active",
        ]
        read_only_fields = ["student_code", "referral_code"]

    def validate(self, attrs):
        # Business rule example: if classroom provided, academic_year must be set.
        classroom = attrs.get("classroom") or getattr(self.instance, "classroom", None)
        year = attrs.get("academic_year") or getattr(self.instance, "academic_year", None)
        if classroom and not year:
            raise serializers.ValidationError("academic_year is required when classroom is set.")
        return attrs


class StudentGuardianSerializer(serializers.ModelSerializer):
    """Serializer for guardian-student links (junction table)."""

    class Meta:
        model = StudentGuardian
        fields = [
            "id",
            "guardian_user",
            "student",
            "relationship",
            "phone",
            "email",
            "whatsapp_number",
            "address",
            "preferred_contact",
            "receives_email",
            "receives_sms",
            "receives_whatsapp",
            "can_view_results",
            "can_view_finance",
        ]

    def validate_guardian_user(self, user):
        role = (getattr(user, "role", "") or "").upper()
        if role not in ("PARENT", "TEACHER"):
            raise serializers.ValidationError("guardian_user must have role PARENT or TEACHER.")
        return user


class StudentSimpleSerializer(serializers.ModelSerializer):
    """Simplified student info"""
    full_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = StudentProfile
        fields = ["id", "student_code", "full_name", "classroom", "specialty"]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


# ==================== TEACHER SERIALIZERS ====================

class TeacherProfileSerializer(serializers.ModelSerializer):
    """CRUD serializer for teachers (links to user)."""

    class Meta:
        model = TeacherProfile
        fields = [
            "id",
            "user",
            "staff_id",
            "phone",
            "department",
            "position_title",
            "reports_to",
            "pay_grade",
            "salary_amount",
            "salary_cap",
            "next_pay_date",
            "payment_method",
            "default_dashboard_view",
            "allow_finance_panel",
            "allow_paystub_access",
            "allow_leave_approvals",
            "mark_reminder_opt_in",
            "is_active",
        ]


# ==================== FINANCE SERIALIZERS ====================

class InvoiceSerializer(serializers.ModelSerializer):
    """Invoice serializer aligned to current finance models."""
    student_name = serializers.SerializerMethodField()
    student_id = serializers.CharField(source='student.student_code', read_only=True)
    paid_amount = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'student', 'student_name', 'student_id',
            'invoice_type', 'status', 'issued_date', 'due_date',
            'reference', 'payment_code', 'total_amount',
            'balance_amount', 'paid_amount', 'balance', 'notes'
        ]

    def get_student_name(self, obj):
        if not obj.student:
            return ""
        return obj.student.get_full_name()
    
    def get_paid_amount(self, obj):
        return obj.payments.filter(status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    def get_balance(self, obj):
        paid = obj.payments.filter(status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        return obj.total_amount - paid


class PaymentSerializer(serializers.ModelSerializer):
    """Payment recording serializer aligned to current finance models."""
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'student', 'amount', 'method', 'payment_method',
            'status', 'paid_at', 'reference', 'reference_number',
            'external_reference', 'receipt_number',
            'physical_receipt_book_serial', 'physical_receipt_number',
        ]


# ==================== ACADEMIC SERIALIZERS ====================

class AttendanceSerializer(serializers.Serializer):
    """Lightweight serializer for attendance records (model-agnostic)."""

    id = serializers.IntegerField(read_only=True)
    student = serializers.IntegerField(source="student_id")
    student_name = serializers.SerializerMethodField()
    classroom = serializers.IntegerField(source="classroom_id")
    class_name = serializers.SerializerMethodField()
    date = serializers.DateField()
    status = serializers.CharField()
    updated_at = serializers.DateTimeField(read_only=True)

    def get_student_name(self, obj):
        student = getattr(obj, "student", None)
        first = getattr(student, "first_name", "") or getattr(getattr(student, "user", None), "first_name", "")
        last = getattr(student, "last_name", "") or getattr(getattr(student, "user", None), "last_name", "")
        return f"{first} {last}".strip()

    def get_class_name(self, obj):
        classroom = getattr(obj, "classroom", None)
        return getattr(classroom, "name", None)


class ClassroomSerializer(serializers.ModelSerializer):
    """Classroom/Class info"""

    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Classroom
        fields = ["id", "academic_year", "department", "name", "code", "allows_third_term", "student_count"]

    def get_student_count(self, obj):
        # Classroom uses related_name="students"; avoid evaluating obj.student_set as default
        rel = getattr(obj, "students", None) or getattr(obj, "student_set", None)
        return rel.filter(is_active=True).count() if rel else 0


# ==================== COMMUNICATION SERIALIZERS ====================

class AnnouncementSerializer(serializers.ModelSerializer):
    """School-wide announcements (communication app)."""
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'content', 'announcement_type', 'audience',
            'status', 'is_active', 'is_urgent', 'created_by', 'created_by_name',
            'created_at', 'updated_at', 'expiry_date',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status', 'created_by']

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class NotificationSerializer(serializers.ModelSerializer):
    """Notification with user context"""
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "link",
            "severity",
            "is_read",
            "created_at",
            "recipient",
            "created_by",
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
