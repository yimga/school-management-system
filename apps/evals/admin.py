from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import TeacherAssignment, Evaluation


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(ModelAdmin):
    list_display = ("teacher", "academic_year", "subject_assignment", "is_active")
    list_filter = ("academic_year", "is_active")
    search_fields = (
        "teacher__user__username",
        "teacher__user__first_name",
        "teacher__user__last_name",
        "subject_assignment__subject__name",
        "subject_assignment__classroom__name",
        "subject_assignment__specialty__name",
    )


@admin.register(Evaluation)
class EvaluationAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "subject_assignment", "student", "teacher", "test1", "test2")
    list_filter = ("academic_year", "term", "subject_assignment__classroom", "subject_assignment__specialty", "subject_assignment__subject")
    search_fields = ("student__student_code", "student__first_name", "student__last_name")

