from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import TeacherAssignment, Evaluation, AssessmentWeights, EvaluationEvidence


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
    list_display = (
        "academic_year",
        "term",
        "subject_assignment",
        "student",
        "teacher",
        "seq1_score",
        "seq2_score",
        "exam_score",
        "mock_score",
        "practical_score",
        "total_score",
    )
    list_filter = ("academic_year", "term", "subject_assignment__classroom", "subject_assignment__specialty", "subject_assignment__subject")
    search_fields = ("student__student_code", "student__first_name", "student__last_name")


@admin.register(AssessmentWeights)
class AssessmentWeightsAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "seq1_weight", "seq2_weight", "exam_weight", "mock_weight", "practical_weight", "score_scale")
    list_filter = ("academic_year", "term", "classroom")


@admin.register(EvaluationEvidence)
class EvaluationEvidenceAdmin(ModelAdmin):
    list_display = ("evaluation", "media_type", "uploaded_by", "uploaded_at")
    list_filter = ("media_type", "uploaded_at")
    search_fields = ("evaluation__student__student_code", "evaluation__student__first_name", "evaluation__student__last_name")
