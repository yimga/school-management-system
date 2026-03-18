from django import forms
from django.core.exceptions import FieldError

from apps.academics.models import AcademicYear, Term, Subject, SubjectAssignment
from apps.people.models import TeacherProfile
from .models import (
    GradeApprovalRequest,
    TeacherAssignment,
    EvaluationEvidence,
    Evaluation,
    AssessmentWeights,
)


def _scope_queryset_by_school(queryset, school):
    if school is None:
        return queryset
    for lookup in ("school", "academic_year__school", "classroom__school"):
        try:
            return queryset.filter(**{lookup: school})
        except FieldError:
            continue
    return queryset


class EvaluationFilterForm(forms.Form):
    year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    classroom = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    missing = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        academic_year = kwargs.pop("academic_year", None)
        school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)
        self.fields["year"].queryset = _scope_queryset_by_school(
            AcademicYear.objects.all().order_by("-start_date"),
            school,
        )
        self.fields["subject"].queryset = _scope_queryset_by_school(
            Subject.objects.all().order_by("name"),
            school,
        )
        if academic_year:
            self.fields["term"].queryset = Term.objects.filter(
                academic_year=academic_year
            ).order_by("start_date")
            self.fields["classroom"].queryset = academic_year.classrooms.order_by(
                "name"
            )
            self.fields["year"].initial = academic_year


class BulkEvaluationCreateForm(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject_assignment = forms.ModelChoiceField(
        queryset=SubjectAssignment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    teacher = forms.ModelChoiceField(
        queryset=TeacherProfile.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        academic_year = kwargs.pop("academic_year", None)
        term = kwargs.pop("term", None)
        school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = _scope_queryset_by_school(
            AcademicYear.objects.all().order_by("-start_date"),
            school,
        )

        if academic_year:
            self.fields["academic_year"].initial = academic_year
            self.fields["term"].queryset = Term.objects.filter(
                academic_year=academic_year
            ).order_by("start_date")

        if term:
            self.fields["term"].initial = term

        subject_qs = SubjectAssignment.objects.all().select_related(
            "academic_year",
            "term",
            "classroom",
            "specialty",
            "subject",
        )
        subject_qs = _scope_queryset_by_school(subject_qs, school)
        if academic_year:
            subject_qs = subject_qs.filter(academic_year=academic_year)
        if term:
            subject_qs = subject_qs.filter(term=term)
        self.fields["subject_assignment"].queryset = subject_qs.order_by(
            "classroom__name",
            "specialty__name",
            "subject__name",
        )

        teacher_qs = _scope_queryset_by_school(
            TeacherProfile.objects.all().select_related("user"),
            school,
        ).order_by("user__last_name", "user__first_name")
        self.fields["teacher"].queryset = teacher_qs

    def clean(self):
        cleaned = super().clean()
        academic_year = cleaned.get("academic_year")
        term = cleaned.get("term")
        subject_assignment = cleaned.get("subject_assignment")

        if not academic_year or not term or not subject_assignment:
            return cleaned

        if subject_assignment.academic_year_id != academic_year.id:
            self.add_error(
                "subject_assignment",
                "Subject assignment does not match the selected academic year.",
            )

        if subject_assignment.term_id != term.id:
            self.add_error(
                "subject_assignment",
                "Subject assignment does not match the selected term.",
            )

        if (
            getattr(term, "position", None) == 3
            and not subject_assignment.classroom.allows_third_term
        ):
            self.add_error(
                "term", "Third term is not allowed for the selected classroom."
            )

        assignment = (
            TeacherAssignment.objects.filter(
                academic_year=academic_year,
                subject_assignment=subject_assignment,
                is_active=True,
            )
            .select_related("teacher")
            .first()
        )
        if assignment and not cleaned.get("teacher"):
            cleaned["teacher"] = assignment.teacher

        return cleaned


class EvaluationEvidenceForm(forms.ModelForm):
    class Meta:
        model = EvaluationEvidence
        fields = ["evaluation", "media_type", "file", "caption"]
        widgets = {
            "evaluation": forms.Select(attrs={"class": "form-select"}),
            "media_type": forms.Select(attrs={"class": "form-select"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        evaluation = kwargs.pop("evaluation", None)
        super().__init__(*args, **kwargs)
        if evaluation:
            self.fields["evaluation"].initial = evaluation
            self.fields["evaluation"].queryset = Evaluation.objects.filter(
                id=evaluation.id
            )


class AssessmentWeightsForm(forms.ModelForm):
    class Meta:
        model = AssessmentWeights
        fields = [
            "academic_year",
            "term",
            "classroom",
            "seq1_weight",
            "seq2_weight",
            "exam_weight",
            "mock_weight",
            "practical_weight",
            "score_scale",
        ]
        widgets = {
            "academic_year": forms.Select(attrs={"class": "form-select"}),
            "term": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "seq1_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "seq2_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "exam_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "mock_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "practical_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "score_scale": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        academic_year = kwargs.pop("academic_year", None)
        super().__init__(*args, **kwargs)
        if academic_year:
            self.fields["academic_year"].initial = academic_year
            self.fields["term"].queryset = Term.objects.filter(
                academic_year=academic_year
            ).order_by("start_date")
            self.fields["classroom"].queryset = academic_year.classrooms.order_by(
                "name"
            )


class BatchFillMissingForm(forms.Form):
    fill_value = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": "0.01"}
        ),
        help_text="Value to fill for missing required components.",
    )


class MarkSheetUploadForm(forms.Form):
    subject_assignment_id = forms.IntegerField(widget=forms.HiddenInput())
    marksheet_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        help_text="Upload a PNG/JPG marksheet. Mobile browsers can capture new photos as needed.",
    )

    def clean_marksheet_file(self):
        file = self.cleaned_data.get("marksheet_file")
        if not file:
            raise forms.ValidationError("Please upload a marksheet image.")
        if file.size > 8 * 1024 * 1024:
            raise forms.ValidationError("File too large (max 8 MB).")
        return file


class GradeApprovalDecisionForm(forms.Form):
    status = forms.ChoiceField(
        choices=GradeApprovalRequest.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial=GradeApprovalRequest.Status.APPROVED,
    )
    reviewer_notes = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        required=False,
        help_text="Optional notes for the teacher if requesting revisions or rejecting.",
    )

    def __init__(self, *args, status_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if status_choices is not None:
            self.fields["status"].choices = status_choices


class GradeApprovalBypassForm(forms.Form):
    status = forms.ChoiceField(
        choices=GradeApprovalRequest.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial=GradeApprovalRequest.Status.APPROVED,
        help_text="Bypass should normally be used to finalize (approve/reject) when an approver is unavailable.",
    )
    bypass_reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        required=True,
        help_text="Required. Explain why the normal approval chain is being bypassed.",
    )
    reviewer_notes = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        required=False,
        help_text="Optional notes sent back to the teacher.",
    )

    def __init__(self, *args, status_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if status_choices is not None:
            self.fields["status"].choices = status_choices
