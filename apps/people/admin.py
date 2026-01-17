from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import TeacherProfile, StudentProfile, StudentGuardian


@admin.register(TeacherProfile)
class TeacherProfileAdmin(ModelAdmin):
    list_display = ("user", "staff_id", "phone")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "staff_id")


@admin.register(StudentProfile)
class StudentProfileAdmin(ModelAdmin):
    list_display = ("student_code", "last_name", "first_name", "academic_year", "classroom", "specialty", "is_active")
    list_filter = ("academic_year", "classroom", "specialty", "is_active")
    search_fields = ("student_code", "first_name", "last_name")


@admin.register(StudentGuardian)
class StudentGuardianAdmin(ModelAdmin):
    list_display = ("guardian_user", "student", "relationship", "can_view_results", "can_view_finance")
    list_filter = ("relationship", "can_view_results", "can_view_finance")
    search_fields = ("guardian_user__username", "guardian_user__email", "student__student_code", "student__last_name")

