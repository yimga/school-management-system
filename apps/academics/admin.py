from django.contrib import admin
from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin
from .models import (
    AcademicYear,
    Term,
    Department,
    Specialty,
    Classroom,
    ClassroomPromotionMapping,
    Subject,
    SubjectAssignment,
    CourseSyllabus,
    ClassBooklist,
    Incident,
    CurriculumStandard,
    CurriculumNode,
    WorkflowConfig,
    CertificationExamSession,
    CertificationCandidate,
    CertificationAuditLog,
    CertificationExamPreset,
    CertificationFeeTemplate,
    CertificationFeeLine,
    CertificationDocumentChecklist,
    CertificationDocumentItem,
    CertificationCandidateDocumentStatus,
)
from .scheduling import (
    Room,
    TimeSlot,
    Schedule,
    ScheduleEntry,
    TeacherAvailability,
    SchedulingConstraint,
)


class AcademicYearAdmin(ModelAdmin):
    list_display = (
        "name",
        "start_date",
        "end_date",
        "is_active",
        "is_locked",
        "enable_gce_registration",
    )
    list_filter = ("is_active", "is_locked", "enable_gce_registration")
    search_fields = ("name",)


class TermAdmin(ModelAdmin):
    list_display = (
        "academic_year",
        "position",
        "name",
        "custom_label",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = ("academic_year", "is_active")
    search_fields = ("academic_year__name", "name", "custom_label")


class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class SpecialtyAdmin(ModelAdmin):
    list_display = ("name", "code", "department")
    list_filter = ("department",)
    search_fields = ("name", "code", "department__name")


class ClassroomAdmin(ModelAdmin):
    list_display = ("name", "code", "department", "academic_year", "allows_third_term")
    list_filter = ("department", "academic_year", "allows_third_term")
    search_fields = ("name", "code", "department__name", "academic_year__name")


class ClassroomPromotionMappingAdmin(ModelAdmin):
    list_display = (
        "source_year",
        "source_classroom",
        "target_year",
        "target_classroom",
    )
    list_filter = ("source_year", "target_year")
    search_fields = ("source_classroom__name", "target_classroom__name")
    autocomplete_fields = ("source_classroom", "target_classroom")


class SubjectAdmin(ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


class SubjectAssignmentAdmin(ModelAdmin):
    list_display = (
        "academic_year",
        "term",
        "classroom",
        "specialty",
        "subject",
        "coefficient",
    )
    list_filter = ("academic_year", "term", "classroom", "specialty", "subject")
    search_fields = (
        "classroom__name",
        "specialty__name",
        "subject__name",
        "academic_year__name",
    )


class CourseSyllabusAdmin(ModelAdmin):
    list_display = (
        "subject_assignment",
        "status",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = (
        "subject_assignment__subject__name",
        "subject_assignment__classroom__name",
    )
    raw_id_fields = ("reviewed_by", "created_by")
    readonly_fields = ("created_at", "updated_at", "submitted_at", "reviewed_at")
    filter_horizontal = ("curriculum_nodes",)


class ClassBooklistAdmin(ModelAdmin):
    list_display = ("classroom", "academic_year", "term", "updated_at")
    list_filter = ("academic_year", "term")
    search_fields = ("classroom__name",)


class _CountryBoardChoicesAdminMixin:
    """Filter the ``board`` choice field to the active tenant's country (local-first).

    The board enum is global; a US school must not see "GCE Board (Cameroon)".
    ``apps.academics.exam_boards.allowed_board_choices`` fails open (full list) for
    an unknown/empty country, so this only ever narrows — never blocks a valid board.
    """

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "board":
            from apps.academics.exam_boards import allowed_board_choices

            school = getattr(request, "school", None) or getattr(request, "tenant", None)
            kwargs["choices"] = allowed_board_choices(getattr(school, "country_code", ""))
        return super().formfield_for_choice_field(db_field, request, **kwargs)


class CertificationExamSessionAdmin(_CountryBoardChoicesAdminMixin, ModelAdmin):
    list_display = (
        "name",
        "academic_year",
        "board",
        "level",
        "is_active",
        "registration_opens_at",
        "registration_closes_at",
    )
    list_filter = ("academic_year", "board", "level", "is_active")
    search_fields = ("name", "academic_year__name")


class CertificationCandidateAdmin(ModelAdmin):
    list_display = (
        "student",
        "session",
        "status",
        "candidate_number",
        "ca_uploaded_at",
        "updated_at",
    )
    list_filter = (
        "session",
        "status",
        "session__academic_year",
        "session__board",
        "session__level",
    )
    search_fields = (
        "student__first_name",
        "student__last_name",
        "candidate_number",
        "session__name",
    )


class CertificationAuditLogAdmin(ModelAdmin):
    list_display = ("created_at", "session", "candidate", "actor", "action")
    list_filter = ("session", "actor", "action")
    search_fields = ("session__name", "action", "detail", "actor__username")


class CertificationExamPresetAdmin(_CountryBoardChoicesAdminMixin, ModelAdmin):
    list_display = ("name", "code", "board", "level", "is_active", "updated_at")
    list_filter = ("board", "level", "is_active")
    search_fields = ("name", "code")


class CertificationFeeLineInline(admin.TabularInline):
    model = CertificationFeeLine
    extra = 0


class CertificationFeeTemplateAdmin(ModelAdmin):
    list_display = (
        "name",
        "preset",
        "currency",
        "is_default_for_preset",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "currency",
        "is_default_for_preset",
        "is_active",
        "preset__board",
        "preset__level",
    )
    search_fields = ("name", "preset__name", "preset__code")
    inlines = [CertificationFeeLineInline]


class CertificationDocumentItemInline(admin.TabularInline):
    model = CertificationDocumentItem
    extra = 0


class CertificationDocumentChecklistAdmin(ModelAdmin):
    list_display = (
        "name",
        "preset",
        "is_default_for_preset",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "is_default_for_preset",
        "is_active",
        "preset__board",
        "preset__level",
    )
    search_fields = ("name", "preset__name", "preset__code")
    inlines = [CertificationDocumentItemInline]


class CertificationCandidateDocumentStatusAdmin(ModelAdmin):
    list_display = ("candidate", "item", "status", "received_at", "verified_at")
    list_filter = ("status", "item__checklist", "candidate__session")
    search_fields = (
        "candidate__student__first_name",
        "candidate__student__last_name",
        "item__label",
        "item__code",
    )


from django import forms


class TermAdminForm(forms.ModelForm):
    class Meta:
        model = Term
        fields = "__all__"
        help_texts = {
            "position": "Order of the term within the academic year (1–4).",
            "custom_label": "Optional display name (e.g., Semester 1).",
        }

    def clean(self):
        cleaned = super().clean()
        is_active = cleaned.get("is_active")
        position = cleaned.get("position")
        if is_active and not position:
            self.add_error("position", "Active terms must have a position (1–4).")
        return cleaned


TermAdmin.form = TermAdminForm


def assign_positions_to_year(modeladmin, request, queryset):
    """Admin action to auto-assign positions 1–4 per year based on start_date order."""
    from django.contrib import messages
    from django.db import transaction

    years = set(queryset.values_list("academic_year_id", flat=True))
    total_assigned = 0

    for year_id in years:
        terms = Term.objects.filter(academic_year_id=year_id).order_by(  # tenant-isolation-allow: django-admin-action-scoped-by-FK (academic_year scopes the tenant via its school FK; this is a staff-only admin bulk action)
            "start_date", "id"
        )
        used_positions = set(
            terms.exclude(position__isnull=True).values_list("position", flat=True)
        )

        updates = []
        next_pos = 1
        for term in terms:
            if term.position:
                continue
            while next_pos in used_positions and next_pos <= 4:
                next_pos += 1
            if next_pos > 4:
                continue
            updates.append(term)
            used_positions.add(next_pos)
            next_pos += 1

        with transaction.atomic():
            for idx, term in enumerate(updates, start=1):
                # Find next free position
                pos = 1
                while pos in set(
                    Term.objects.filter(academic_year_id=year_id, position=pos).count()  # tenant-isolation-allow: django-admin-action-scoped-by-FK (same FK-scoping as above)
                    for pos in range(1, 5)
                ):
                    pos += 1
                if pos <= 4:
                    term.position = pos
                    term.save(update_fields=["position"])
                    total_assigned += 1

    messages.success(
        request,
        f"Assigned positions to {total_assigned} terms across {len(years)} academic year(s).",
    )


assign_positions_to_year.short_description = (
    "Assign positions 1–4 per year (start_date order)"
)
TermAdmin.actions = [assign_positions_to_year]


# Register all models with custom admin site
register_tenant_admin(AcademicYear, AcademicYearAdmin)
register_tenant_admin(Term, TermAdmin)
register_tenant_admin(Department, DepartmentAdmin)
register_tenant_admin(Specialty, SpecialtyAdmin)
register_tenant_admin(Classroom, ClassroomAdmin)
register_tenant_admin(ClassroomPromotionMapping, ClassroomPromotionMappingAdmin)
register_tenant_admin(Subject, SubjectAdmin)


class IncidentAdmin(ModelAdmin):
    list_display = (
        "date",
        "school",
        "incident_type",
        "student",
        "teacher",
        "severity",
        "status",
        "notify_parent",
        "created_at",
    )
    list_filter = ("school", "incident_type", "severity", "status", "notify_parent")
    search_fields = (
        "description",
        "student__first_name",
        "student__last_name",
        "teacher__user__first_name",
        "teacher__user__last_name",
        "school__name",
    )
    raw_id_fields = ("school", "student", "teacher", "created_by")
    date_hierarchy = "date"


register_tenant_admin(Incident, IncidentAdmin)
register_tenant_admin(SubjectAssignment, SubjectAssignmentAdmin)
register_tenant_admin(CourseSyllabus, CourseSyllabusAdmin)
register_tenant_admin(ClassBooklist, ClassBooklistAdmin)


class CurriculumNodeInline(admin.TabularInline):
    model = CurriculumNode
    fk_name = "standard"
    extra = 0
    ordering = ("order", "code")


class CurriculumStandardAdmin(ModelAdmin):
    list_display = ("name", "country_code")
    list_filter = ("country_code",)
    search_fields = ("name", "description")
    inlines = [CurriculumNodeInline]


class CurriculumNodeAdmin(ModelAdmin):
    list_display = ("code", "title", "standard", "parent", "level_type", "order")
    list_filter = ("standard", "level_type")
    search_fields = ("code", "title")
    raw_id_fields = ("parent",)
    ordering = ("standard", "order", "code")


register_tenant_admin(CurriculumStandard, CurriculumStandardAdmin)
register_tenant_admin(CurriculumNode, CurriculumNodeAdmin)
register_tenant_admin(CertificationExamSession, CertificationExamSessionAdmin)
register_tenant_admin(CertificationCandidate, CertificationCandidateAdmin)
register_tenant_admin(CertificationAuditLog, CertificationAuditLogAdmin)
register_tenant_admin(CertificationExamPreset, CertificationExamPresetAdmin)
register_tenant_admin(CertificationFeeTemplate, CertificationFeeTemplateAdmin)
register_tenant_admin(
    CertificationDocumentChecklist, CertificationDocumentChecklistAdmin
)
register_tenant_admin(
    CertificationCandidateDocumentStatus, CertificationCandidateDocumentStatusAdmin
)


# --- Scheduling (timetable) ---
class RoomAdmin(ModelAdmin):
    list_display = (
        "name",
        "room_type",
        "building",
        "floor",
        "capacity",
        "is_available",
    )
    list_filter = ("room_type", "is_available")
    search_fields = ("name", "building")


class TimeSlotAdmin(ModelAdmin):
    list_display = ("slot_name", "day_of_week", "start_time", "end_time", "is_active")
    list_filter = ("day_of_week", "is_active")
    search_fields = ("slot_name",)
    ordering = ("day_of_week", "start_time")


class ScheduleEntryInline(admin.TabularInline):
    model = ScheduleEntry
    extra = 0
    autocomplete_fields = ("classroom", "subject", "teacher", "room", "time_slot")
    raw_id_fields = ("replacement_teacher",)


class ScheduleAdmin(ModelAdmin):
    list_display = (
        "name",
        "academic_year",
        "term",
        "status",
        "generated_at",
        "published_at",
    )
    list_filter = ("status", "academic_year", "term")
    search_fields = ("name",)
    inlines = [ScheduleEntryInline]
    autocomplete_fields = ("academic_year", "term", "created_by")


class ScheduleEntryAdmin(ModelAdmin):
    list_display = (
        "schedule",
        "classroom",
        "subject",
        "teacher",
        "room",
        "time_slot",
        "is_cancelled",
    )
    list_filter = ("schedule__term", "schedule__academic_year", "is_cancelled")
    search_fields = ("classroom__name", "subject__name", "teacher__username")
    autocomplete_fields = (
        "schedule",
        "classroom",
        "subject",
        "teacher",
        "room",
        "time_slot",
    )


class TeacherAvailabilityAdmin(ModelAdmin):
    list_display = ("teacher", "time_slot", "is_available", "preference_level")
    list_filter = ("is_available",)
    search_fields = ("teacher__username", "time_slot__slot_name")


class SchedulingConstraintAdmin(ModelAdmin):
    list_display = ("name", "constraint_type", "is_active", "priority")
    list_filter = ("constraint_type", "is_active")


register_tenant_admin(Room, RoomAdmin)
register_tenant_admin(TimeSlot, TimeSlotAdmin)
register_tenant_admin(Schedule, ScheduleAdmin)
register_tenant_admin(ScheduleEntry, ScheduleEntryAdmin)
register_tenant_admin(TeacherAvailability, TeacherAvailabilityAdmin)
register_tenant_admin(SchedulingConstraint, SchedulingConstraintAdmin)


class WorkflowConfigAdmin(ModelAdmin):
    list_display = ("workflow_key", "is_active", "step_count_display", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("workflow_key",)

    def step_count_display(self, obj):
        return len(obj.steps) if obj.steps else 0

    step_count_display.short_description = "Steps"


register_tenant_admin(WorkflowConfig, WorkflowConfigAdmin)


# Education-system phase 2 (2026-05-11): LMS spine admin.
from .models_lms import LMSAssignment, LMSSubmission  # noqa: E402


class LMSAssignmentAdmin(ModelAdmin):
    list_display = (
        "title",
        "classroom",
        "subject",
        "teacher",
        "term",
        "status",
        "due_at",
        "points_possible",
        "school",
    )
    list_filter = ("status", "assignment_type", "school")
    search_fields = ("title", "instructions")
    raw_id_fields = ("school", "classroom", "subject", "term", "teacher")
    date_hierarchy = "due_at"
    ordering = ["-due_at", "-id"]


class LMSSubmissionAdmin(ModelAdmin):
    list_display = (
        "assignment",
        "student",
        "status",
        "submitted_at",
        "score",
        "graded_at",
        "graded_by",
        "school",
    )
    list_filter = ("status", "school")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "student__student_code",
        "assignment__title",
    )
    raw_id_fields = ("school", "assignment", "student", "graded_by")
    date_hierarchy = "submitted_at"
    ordering = ["-submitted_at", "-id"]


register_tenant_admin(LMSAssignment, LMSAssignmentAdmin)
register_tenant_admin(LMSSubmission, LMSSubmissionAdmin)
