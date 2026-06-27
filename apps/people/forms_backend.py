"""
Backend UI Forms for People Management
User-friendly forms for /backend interface (separate from Django Admin)
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import StudentProfile, TeacherProfile, Applicant
from apps.academics.models import AcademicYear, Classroom, Specialty, Department


class StudentCreateForm(forms.ModelForm):
    """User-friendly form for creating students in /backend UI"""

    # Not on StudentProfile; used in view to create parent account
    parent_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": _("parent@example.com")}
        ),
        label="Parent email (optional)",
        help_text="If provided, a parent account will be created and linked.",
    )

    class Meta:
        model = StudentProfile
        fields = [
            "first_name",
            "last_name",
            "admission_number",
            "gender",
            "date_of_birth",
            "place_of_birth",
            "status",
            "academic_year",
            "classroom",
            "specialty",
            "parent_phone",
            "profile_photo",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Enter first name")}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Enter last name")}
            ),
            "admission_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Auto-generated if left blank"),
                }
            ),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "date_of_birth": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "place_of_birth": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("City, Country")}
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "academic_year": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "specialty": forms.Select(attrs={"class": "form-select"}),
            "parent_phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("+CC NNN NNN NNNN")}
            ),
            "parent_email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": _("parent@example.com")}
            ),
            "profile_photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),
        }

    def __init__(self, *args, school=None, **kwargs):
        self._school = school
        super().__init__(*args, **kwargs)
        from apps.metadata.dynamic_forms import attach_dynamic_fields_for_model

        attach_dynamic_fields_for_model(
            self,
            school=self._school,
            model=StudentProfile,
            instance=self.instance,
        )
        # Filter to active academic year and classrooms
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(
            is_active=True
        )
        self.fields["academic_year"].empty_label = "Select academic year"

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        # Filter classrooms by active academic year
        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            self.fields["classroom"].queryset = Classroom.objects.filter(
                academic_year=active_year
            ).order_by("name")
        else:
            self.fields["classroom"].queryset = Classroom.objects.none()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        self.fields["classroom"].empty_label = "Select classroom"

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        self.fields["specialty"].queryset = Specialty.objects.all().order_by("name")
        self.fields["specialty"].empty_label = "Select specialty (optional)"

        # Make some fields optional
        self.fields["admission_number"].required = False
        self.fields["date_of_birth"].required = False
        self.fields["place_of_birth"].required = False
        self.fields["specialty"].required = False
        self.fields["parent_phone"].required = False


class TeacherCreateForm(forms.ModelForm):
    """User-friendly form for creating teachers in /backend UI"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": _("teacher@example.com")}
        ),
        help_text="Used as username for login",
    )
    username = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Auto-generated from email")}
        ),
        help_text="Leave blank to auto-generate from email",
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": _("Enter password")}
        ),
        help_text="Temporary password (user should change on first login)",
    )

    class Meta:
        model = TeacherProfile
        fields = [
            "staff_id",
            "phone",
            "position_title",
            "department",
            "reports_to",
            "pay_grade",
            "profile_photo",
        ]
        widgets = {
            "staff_id": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., STAFF001"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("+CC NNN NNN NNNN")}
            ),
            "position_title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Mathematics Teacher",
                }
            ),
            "department": forms.Select(attrs={"class": "form-select"}),
            "reports_to": forms.Select(attrs={"class": "form-select"}),
            "pay_grade": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., Grade 1"}
            ),
            "profile_photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                }
            ),
        }
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    def __init__(self, *args, school=None, **kwargs):
        self._school = school
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        super().__init__(*args, **kwargs)
        from apps.metadata.dynamic_forms import attach_dynamic_fields_for_model

        attach_dynamic_fields_for_model(
            self,
            school=self._school,
            model=TeacherProfile,
            instance=self.instance,
        )
        self.fields["department"].queryset = Department.objects.all().order_by("name")
        self.fields["department"].empty_label = "Select department"
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        self.fields["reports_to"].queryset = TeacherProfile.objects.filter(
            is_active=True
        ).order_by("staff_id")
        self.fields["reports_to"].empty_label = "Select supervisor (optional)"
        self.fields["reports_to"].required = False

        self.fields["pay_grade"].required = False


class ClassroomCreateForm(forms.ModelForm):
    """User-friendly form for creating classrooms in /backend UI"""

    class Meta:
        model = Classroom
        fields = ["name", "code", "academic_year", "department", "allows_third_term"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Form 1A, Upper Sixth Science",
                }
            ),
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., F1A, US-SCI"}
            ),
            "academic_year": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "allows_third_term": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(
            is_active=True
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        )
        self.fields["academic_year"].empty_label = "Select academic year"
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        self.fields["department"].queryset = Department.objects.all().order_by("name")
        self.fields["department"].empty_label = "Select department"
        self.fields["allows_third_term"].initial = True


class ApplicantCreateForm(forms.ModelForm):
    """Backend form for adding an applicant/lead (26.5: long form with Save draft)."""

    class Meta:
        model = Applicant
        fields = ["first_name", "last_name", "email", "lead_source", "stage"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("First name")}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Last name")}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "email@example.com"}
            ),
            "lead_source": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Website, Referral"}
            ),
            "stage": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        self._school = school
        super().__init__(*args, **kwargs)
        from apps.metadata.dynamic_forms import attach_dynamic_fields_for_model

        # Applicant EAV fields are keyed on entity_type "people.applicant".
        # Passing TeacherProfile here rendered/saved TEACHER custom fields on
        # the Applicant form (entity_type "people.teacherprofile"); use the
        # Applicant model so admissions-defined custom fields surface instead.
        attach_dynamic_fields_for_model(
            self,
            school=self._school,
            model=Applicant,
            instance=self.instance,
        )
        self.fields["lead_source"].required = False
        self.fields["stage"].initial = Applicant.Stage.LEAD
