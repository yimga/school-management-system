from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import (
    AcademicYear, Term, Department, Specialty, ClassRoom, Subject, SubjectAssignment
)


@admin.register(AcademicYear)
class AcademicYearAdmin(ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Term)
class TermAdmin(ModelAdmin):
    list_display = ("academic_year", "name", "start_date", "end_date", "is_active")
    list_filter = ("academic_year", "name", "is_active")
    search_fields = ("academic_year__name",)


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Specialty)
class SpecialtyAdmin(ModelAdmin):
    list_display = ("name", "code", "department")
    list_filter = ("department",)
    search_fields = ("name", "code", "department__name")


@admin.register(ClassRoom)
class ClassRoomAdmin(ModelAdmin):
    list_display = ("name", "code", "department")
    list_filter = ("department",)
    search_fields = ("name", "code", "department__name")


@admin.register(Subject)
class SubjectAdmin(ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(SubjectAssignment)
class SubjectAssignmentAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "specialty", "subject", "coefficient")
    list_filter = ("academic_year", "term", "classroom", "specialty", "subject")
    search_fields = ("classroom__name", "specialty__name", "subject__name", "academic_year__name")

