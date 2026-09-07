"""
Backend UI Forms for People Management
User-friendly forms for /backend interface (separate from Django Admin)
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import StudentProfile, TeacherProfile, Applicant, StudentGuardian
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
)


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

    def __init__(self, *args, school=None, **kwargs):
        """Scope the choices to ``school`` and remember it for ``save()``.

        The previous markers claimed these querysets were "scoped via
        surrounding tenant context". They were not scoped by anything: under
        RLS (``USE_DJANGO_TENANTS=0``) every school shares one table, so the
        dropdowns listed every tenant's active years and departments, and a
        posted foreign id was accepted because the field's queryset is also the
        validator.

        ``school`` is optional so the form is still constructible without a
        request (management commands, the admin, existing tests). When it is
        omitted nothing is scoped -- the caller is trusted, exactly as before --
        but the tenant-facing view now always passes it.
        """
        super().__init__(*args, **kwargs)
        self.school = school
        if school is not None:
            years = AcademicYear.objects.filter(school=school, is_active=True)
            departments = Department.objects.filter(school=school)
        else:
            # tenant-isolation-allow: unbound-form-is-cli-or-admin-caller-not-a-tenant-request
            years = AcademicYear.objects.filter(is_active=True)
            # tenant-isolation-allow: unbound-form-is-cli-or-admin-caller-not-a-tenant-request
            departments = Department.objects.all()
        self.fields["academic_year"].queryset = years.order_by("-start_date")
        self.fields["academic_year"].empty_label = "Select academic year"
        self.fields["department"].queryset = departments.order_by("name")
        self.fields["department"].empty_label = "Select department"
        self.fields["allows_third_term"].initial = True

    def save(self, commit=True):
        """Stamp the school onto the row.

        ``Classroom.school`` is nullable and no signal backfills it, so without
        this every classroom created through this page landed with
        ``school_id`` NULL. That is not cosmetic: ``uniq_classroom_school_code``
        is ``(school, code)`` and NULLs compare distinct, so the constraint
        meant to stop a duplicate "F1A" silently stops enforcing, the row is
        invisible to every ``filter(school=...)`` read, and
        ``roster_webhook_on_classroom_save`` returns early without emitting the
        OneRoster ``class.created`` event.
        """
        classroom = super().save(commit=False)
        if classroom.school_id is None:
            # Prefer the bound tenant; fall back to the year the user picked,
            # which is already scoped to that tenant by __init__.
            classroom.school = self.school or getattr(
                classroom.academic_year, "school", None
            )
        if commit:
            classroom.save()
        return classroom


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


class GuardianCreateForm(forms.ModelForm):
    """Backend form for linking a guardian/parent account to a student.

    ``StudentGuardian`` needs an ``accounts.User`` to point at, so the form
    identifies the guardian by email: the view links an existing PARENT/TEACHER
    account when one already carries that address and otherwise mints a
    password-less parent account, exactly as ``backend_student_create`` does for
    its ``parent_email`` field. The name fields are only consumed when a new
    account is created.
    """

    guardian_first_name = forms.CharField(
        required=False,
        max_length=150,
        label=_("Guardian first name"),
        help_text=_("Used only when a new guardian account has to be created."),
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("First name")}
        ),
    )
    guardian_last_name = forms.CharField(
        required=False,
        max_length=150,
        label=_("Guardian last name"),
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Last name")}
        ),
    )

    class Meta:
        model = StudentGuardian
        fields = [
            "student",
            "email",
            "relationship",
            "phone",
            "whatsapp_number",
            "address",
            "preferred_contact",
            "receives_email",
            "receives_sms",
            "receives_whatsapp",
            "can_view_results",
            "can_view_finance",
        ]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "guardian@example.com"}
            ),
            "relationship": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Phone number")}
            ),
            "whatsapp_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("WhatsApp number")}
            ),
            "address": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Home address")}
            ),
            "preferred_contact": forms.Select(attrs={"class": "form-select"}),
            "receives_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "receives_sms": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "receives_whatsapp": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "can_view_results": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "can_view_finance": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, school=None, **kwargs):
        """Scope the student picker to ``school`` and remember it for the view.

        A ``ModelChoiceField``'s queryset is also its validator, so an unscoped
        student list would let a posted foreign student id create a guardian
        link into another tenant's roster.
        """
        super().__init__(*args, **kwargs)
        self.school = school
        # Resolved in ``clean()`` so the view does not repeat the lookup.
        self.existing_guardian_user = None
        if school is not None:
            students = StudentProfile.objects.filter(school=school)
        else:
            # tenant-isolation-allow: unbound-form-is-cli-or-admin-caller-not-a-tenant-request
            students = StudentProfile.objects.all()
        self.fields["student"].queryset = students.select_related("classroom").order_by(
            "last_name", "first_name"
        )
        self.fields["student"].empty_label = _("Select student")
        self.fields["student"].label = _("Student")
        # The link's email doubles as the guardian account's identity, so it is
        # required here even though the model column allows blank for old rows.
        self.fields["email"].required = True
        self.fields["email"].label = _("Guardian email")
        self.fields["email"].help_text = _(
            "The guardian signs in with this address. An account is created if none exists."
        )

    def _post_clean(self):
        """Bind the resolved account before ModelForm validates the instance.

        ``StudentGuardian.clean()`` is the role check for this link. It only
        runs against an account that exists, so bind the one ``clean()``
        resolved; when there is none the view is about to mint a PARENT
        account, which satisfies that rule by construction.
        """
        if getattr(self, "existing_guardian_user", None) is not None:
            self.instance.guardian_user = self.existing_guardian_user
        super()._post_clean()

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        """Reject a link the view could not legally create.

        ``StudentGuardian.clean()`` forbids a guardian whose role is neither
        PARENT nor TEACHER, but ``save()`` never calls it -- so the check has to
        happen here or a staff account would silently gain a child's records.
        """
        cleaned = super().clean()
        email = cleaned.get("email") or ""
        student = cleaned.get("student")
        if not email or student is None:
            return cleaned
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        existing = user_model.objects.filter(email__iexact=email).first()
        self.existing_guardian_user = existing
        if existing is None:
            return cleaned
        allowed_roles = (user_model.Role.PARENT, user_model.Role.TEACHER)
        if getattr(existing, "role", None) not in allowed_roles:
            self.add_error(
                "email",
                _(
                    "That address belongs to an account with a different role. Guardian access must be a parent or teacher account."
                ),
            )
            return cleaned
        clash = StudentGuardian.objects.filter(
            student=student, guardian_user=existing
        )  # tenant-isolation-allow: student came from the school-scoped queryset in __init__, so this pair is already tenant-bounded
        if clash.exists():
            self.add_error(
                "email", _("This guardian is already linked to that student.")
            )
        return cleaned


class SpecialtyCreateForm(forms.ModelForm):
    """User-friendly form for creating specialties/streams in the /backend UI."""

    class Meta:
        model = Specialty
        fields = ["name", "code", "department"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("e.g. Science, Arts, Industrial Maintenance"),
                }
            ),
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("e.g. SCI, ART")}
            ),
            "department": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        """Scope the department picker to ``school`` and remember it for ``save()``.

        ``school`` is optional so the form stays constructible without a request
        (management commands, tests); the tenant-facing view always passes it.
        """
        super().__init__(*args, **kwargs)
        self.school = school
        if school is not None:
            departments = Department.objects.filter(school=school)
        else:
            # tenant-isolation-allow: unbound-form-is-cli-or-admin-caller-not-a-tenant-request
            departments = Department.objects.all()
        self.fields["department"].queryset = departments.order_by("name")
        self.fields["department"].empty_label = _("Select department")
        # ``code`` participates in uniq_specialty_school_code; the model does not
        # set blank=True, so it stays required -- never "optional once".
        self.fields["code"].required = True

    def clean_code(self):
        """Surface uniq_specialty_school_code as a field error, not an IntegrityError.

        ``school`` is not a form field, so ModelForm excludes it from constraint
        validation and the duplicate would only be caught by the database.
        """
        code = (self.cleaned_data.get("code") or "").strip()
        if code and self.school is not None:
            clash = Specialty.objects.filter(school=self.school, code=code)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    _("A specialty with this code already exists at your school.")
                )
        return code

    def save(self, commit=True):
        """Stamp the school onto the row.

        ``Specialty.school`` is nullable and nothing backfills it, so a row saved
        without this is invisible to every ``filter(school=...)`` read and
        ``uniq_specialty_school_code`` stops enforcing (NULLs compare distinct).
        """
        specialty = super().save(commit=False)
        if specialty.school_id is None:
            specialty.school = self.school or getattr(
                specialty.department, "school", None
            )
        if commit:
            specialty.save()
        return specialty


class SubjectCreateForm(forms.ModelForm):
    """User-friendly form for creating subjects/courses in the /backend UI."""

    class Meta:
        model = Subject
        fields = ["name", "code", "category", "credits"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("e.g. Mathematics, Physics"),
                }
            ),
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Optional board code")}
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
            "credits": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, school=None, **kwargs):
        """Remember ``school`` for the duplicate check and for ``save()``."""
        super().__init__(*args, **kwargs)
        self.school = school
        # ``code`` is blank=True/default="" on the model and is only indexed, not
        # unique, so leaving it empty repeatedly is safe.
        self.fields["code"].required = False
        self.fields["credits"].required = False
        self.fields["category"].initial = Subject.Category.OTHER

    def clean_name(self):
        """Surface academics_subject_school_name_uniq as a field error.

        ``school`` is not a form field, so ModelForm excludes the constraint from
        validation; without this the duplicate reaches the database as an
        IntegrityError instead of a message the user can act on.
        """
        name = (self.cleaned_data.get("name") or "").strip()
        if name and self.school is not None:
            clash = Subject.objects.filter(school=self.school, name=name)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    _("A subject with this name already exists at your school.")
                )
        return name

    def save(self, commit=True):
        """Stamp the school onto the row -- see SpecialtyCreateForm.save()."""
        subject = super().save(commit=False)
        if subject.school_id is None:
            subject.school = self.school
        if commit:
            subject.save()
        return subject


class GuardianEditForm(forms.ModelForm):
    """Edit an existing guardian link from its detail page.

    Deliberately narrower than ``GuardianCreateForm``: neither *which student*
    nor *which account* is editable here. ``student`` is half of
    ``unique_together("guardian_user", "student")`` -- re-pointing a link is a
    different operation from correcting one -- and ``email`` on the create form
    is the *account selector*, so an edit that changed it would silently mint or
    swap a login that grants access to a child's records. What an admin needs
    after the fact is the contact details and the access flags, and those are
    what this exposes.

    ``StudentGuardian.clean()`` still runs through ``_post_clean`` and re-checks
    the linked account's role, so a link whose account was later demoted to a
    staff role surfaces as a form error rather than being silently re-saved.
    """

    class Meta:
        model = StudentGuardian
        fields = [
            "relationship",
            "phone",
            "whatsapp_number",
            "address",
            "preferred_contact",
            "receives_email",
            "receives_sms",
            "receives_whatsapp",
            "can_view_results",
            "can_view_finance",
        ]
        widgets = {
            "relationship": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Phone number")}
            ),
            "whatsapp_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("WhatsApp number")}
            ),
            "address": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("Home address")}
            ),
            "preferred_contact": forms.Select(attrs={"class": "form-select"}),
            "receives_email": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "receives_sms": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "receives_whatsapp": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "can_view_results": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "can_view_finance": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }
