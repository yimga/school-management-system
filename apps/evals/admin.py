from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin
from .models import TeacherAssignment, Evaluation, AssessmentWeights, EvaluationEvidence, GradeAudit, OfflineMarkEntry


class TeacherAssignmentAdmin(ModelAdmin):
    list_display = ("teacher", "academic_year", "subject_assignment", "is_active")
    list_filter = ("academic_year", "is_active")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = (
        "teacher__user__username",
        "teacher__user__first_name",
        "teacher__user__last_name",
        "subject_assignment__subject__name",
        "subject_assignment__classroom__name",
        "subject_assignment__specialty__name",
    )


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
        "letter_grade",
    )
    list_filter = ("academic_year", "term", "subject_assignment__classroom", "subject_assignment__specialty", "subject_assignment__subject")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("student__student_code", "student__first_name", "student__last_name")


class AssessmentWeightsAdmin(ModelAdmin):
    list_display = ("academic_year", "term", "classroom", "seq1_weight", "seq2_weight", "exam_weight", "mock_weight", "practical_weight", "score_scale")
    list_filter = ("academic_year", "term", "classroom", "grading_scale")
    list_per_page = 50  # PERFORMANCE: Add pagination


class EvaluationEvidenceAdmin(ModelAdmin):
    list_display = ("evaluation", "media_type", "uploaded_by", "uploaded_at")
    list_filter = ("media_type", "uploaded_at")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("evaluation__student__student_code", "evaluation__student__first_name", "evaluation__student__last_name")


class GradeAuditAdmin(ModelAdmin):
    list_display = ('evaluation', 'changed_by', 'change_type', 'changed_at')
    list_filter = ('change_type', 'changed_at')
    list_per_page = 50  # PERFORMANCE: Add pagination
    readonly_fields = (
        'evaluation', 'changed_by', 'changed_at', 'change_type',
        'seq1_before', 'seq1_after', 'seq2_before', 'seq2_after',
        'exam_before', 'exam_after', 'mock_before', 'mock_after',
        'practical_before', 'practical_after', 'remarks_before', 'remarks_after',
    )
    ordering = ['-changed_at']


class OfflineMarkEntryAdmin(ModelAdmin):
    list_display = ('student', 'subject_assignment', 'status', 'created_offline_at')
    list_filter = ('status', 'created_offline_at')
    list_per_page = 50  # PERFORMANCE: Add pagination
    fieldsets = (
        ('Grade Entry', {
            'fields': ('student', 'subject_assignment', 'teacher', 'seq1_score', 'seq2_score', 'exam_score', 'mock_score', 'practical_score', 'remarks'),
        }),
        ('Sync Status', {
            'fields': ('status', 'created_offline_at', 'synced_at', 'synced_by'),
        }),
        ('Conflict Resolution', {
            'fields': ('conflict_with_evaluation', 'offline_conflict_resolved', 'conflict_resolution_note'),
        }),
    )
    readonly_fields = ('created_offline_at', 'synced_at', 'synced_by')


# Register all models with custom admin site
admin_site.register(TeacherAssignment, TeacherAssignmentAdmin)
admin_site.register(Evaluation, EvaluationAdmin)
admin_site.register(AssessmentWeights, AssessmentWeightsAdmin)
admin_site.register(EvaluationEvidence, EvaluationEvidenceAdmin)
admin_site.register(GradeAudit, GradeAuditAdmin)
admin_site.register(OfflineMarkEntry, OfflineMarkEntryAdmin)

