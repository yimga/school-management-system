from django.contrib import admin

from unfold.admin import ModelAdmin
from .models import (
    AcademicYear, Term, Department, Specialty, Classroom, Subject, SubjectAssignment
)


@admin.register(AcademicYear)
class AcademicYearAdmin(ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Term)
class TermAdmin(ModelAdmin):
    list_display = ("academic_year", "position", "name", "custom_label", "start_date", "end_date", "is_active")
    list_filter = ("academic_year", "is_active")
    search_fields = ("academic_year__name", "name", "custom_label")


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Specialty)
class SpecialtyAdmin(ModelAdmin):
    list_display = ("name", "code", "department")
    list_filter = ("department",)
    search_fields = ("name", "code", "department__name")


@admin.register(Classroom)
class ClassroomAdmin(ModelAdmin):
    list_display = ("name", "code", "department", "academic_year", "allows_third_term")
    list_filter = ("department", "academic_year", "allows_third_term")
    search_fields = ("name", "code", "department__name", "academic_year__name")


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
        terms = Term.objects.filter(academic_year_id=year_id).order_by("start_date", "id")
        used_positions = set(terms.exclude(position__isnull=True).values_list("position", flat=True))
        
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
                    Term.objects.filter(academic_year_id=year_id, position=pos).count()
                    for pos in range(1, 5)
                ):
                    pos += 1
                if pos <= 4:
                    term.position = pos
                    term.save(update_fields=["position"])
                    total_assigned += 1
    
    messages.success(
        request,
        f"Assigned positions to {total_assigned} terms across {len(years)} academic year(s)."
    )


assign_positions_to_year.short_description = "Assign positions 1–4 per year (start_date order)"
TermAdmin.actions = [assign_positions_to_year]
