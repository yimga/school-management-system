import logging
import re

from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import DatabaseError
from django.utils.translation import gettext_lazy as _

from apps.people.models import StudentGuardian, StudentProfile, TeacherLeaveRequest
from apps.siteconfig.config_service import get_effective_site_settings
from .models import (
    LessonPlan,
    LessonPlanAttachment,
    TeacherTrainingEntry,
    AttendanceJustification,
    CahierDeTexteEntry,
)
from apps.academics.models import Term, AcademicYear

logger = logging.getLogger(__name__)
_FORM_POLICY_ERRORS = (ImportError, AttributeError, TypeError, ValueError, KeyError)


def _default_school_code(school=None) -> str:
    raw = (
        (getattr(school, "slug", None) or getattr(school, "name", None) or "")
        .strip()
        .upper()
    )
    if not raw:
        return "SCH"
    parts = [part for part in re.split(r"[^A-Z0-9]+", raw) if part]
    initials = "".join(part[0] for part in parts[:6])
    if initials:
        return initials[:6]
    return "".join(parts)[:6] or "SCH"


class LinkChildForm(forms.Form):
    admission_number = forms.CharField(
        label=_("Admission number"),
        help_text=_("Enter the student's admission number (format depends on school)."),
    )
    relationship = forms.ChoiceField(
        choices=StudentGuardian.Relationship.choices,
        initial=StudentGuardian.Relationship.GUARDIAN,
        label=_("Relationship"),
    )
    phone = forms.CharField(
        required=False,
        label=_("Contact phone"),
        help_text=_("Used for urgent notices if no parent phone is on file."),
    )
    preferred_contact = forms.ChoiceField(
        choices=StudentGuardian.PreferredContact.choices,
        initial=StudentGuardian.PreferredContact.EMAIL,
        label=_("Preferred contact"),
    )
    referral_code = forms.CharField(
        required=False,
        label=_("Referral code"),
        help_text=_("Optional: provide the referral code you received."),
    )
    student_date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Student date of birth"),
    )
    student_place_of_birth = forms.CharField(
        required=False,
        label=_("Place of birth"),
        help_text=_("City or town where the student was born."),
    )
    student_gender = forms.ChoiceField(
        required=False,
        choices=StudentProfile.Gender.choices,
        label=_("Gender"),
    )
    student_status = forms.ChoiceField(
        required=False,
        choices=StudentProfile.Status.choices,
        label=_("Student status"),
    )
    student_joined_term = forms.ChoiceField(
        required=False,
        choices=[],
        label=("Joined term"),
    )
    student_joined_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Joined date"),
    )
    parent_first_name = forms.CharField(
        required=False,
        label=_("Parent first name"),
    )
    parent_last_name = forms.CharField(
        required=False,
        label=_("Parent last name"),
    )
    parent_email = forms.EmailField(
        required=False,
        label=_("Parent email"),
    )
    parent_whatsapp = forms.CharField(
        required=False,
        label=_("Parent WhatsApp"),
    )
    parent_address = forms.CharField(
        required=False,
        label=_("Parent address"),
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    can_view_results = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Allow viewing results"),
    )
    can_view_finance = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Allow viewing finance"),
    )

    ONBOARDING_FIELDS = [
        "student_date_of_birth",
        "student_place_of_birth",
        "student_gender",
        "student_status",
        "student_joined_term",
        "student_joined_date",
        "parent_first_name",
        "parent_last_name",
        "parent_email",
        "parent_whatsapp",
        "parent_address",
        "phone",
        "preferred_contact",
        "referral_code",
    ]

    def __init__(self, *args, **kwargs):
        self.guardian_user = kwargs.pop("guardian_user", None)
        policy = kwargs.pop("policy", None)
        school = kwargs.pop("school", None)
        self.school = school
        school_code = kwargs.pop("school_code", None)
        if not school_code and policy:
            school_code = (policy.get("admissions") or {}).get("school_code")
        if not school_code:
            site = get_effective_site_settings(school=school)
            school_code = (
                _default_school_code(school)
                or getattr(site, "school_code", None)
                or "SCH"
            )
        super().__init__(*args, **kwargs)
        # Populate dynamic term choices from active academic year
        # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year:
            # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
            terms = Term.objects.filter(academic_year=active_year).order_by(
                "start_date"
            )
            self.fields["student_joined_term"].choices = [
                (t.name, t.label) for t in terms
            ]
        else:
            self.fields["student_joined_term"].choices = []
        if school_code:
            self.fields["admission_number"].help_text = _(
                f"Format: YY + {school_code} + #### + SPEC + CLASS (no dashes)."
            )
        # Policy-driven label if provided
        term_label = (policy or {}).get("terminology") or {}
        if term_label.get("admission_number_label"):
            self.fields["admission_number"].label = term_label["admission_number_label"]
        # Section 23.4: policy-driven field visibility, required, picker options
        try:
            from apps.policies.form_policy import apply_form_policy

            apply_form_policy(self, "link_child", policy or {}, school=None)
        except _FORM_POLICY_ERRORS:
            logger.debug("apply_form_policy (link_child) skipped", exc_info=True)
        self.fields["referral_code"].help_text = _(
            "Include a referral code if someone shared one with you; this unlocks bonus credits."
        )

        # Add Bootstrap classes for wizard styling
        self.fields["admission_number"].widget.attrs.update(
            {
                "class": "form-control form-control-lg",
                "placeholder": "Enter admission number",
                "autofocus": True,
            }
        )
        self.fields["relationship"].widget.attrs.update(
            {
                "class": "form-select form-select-lg",
            }
        )
        self.fields["phone"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "e.g., +CC NNN NNN NNNN",
            }
        )
        self.fields["preferred_contact"].widget.attrs.update(
            {
                "class": "form-select",
            }
        )
        self.fields["student_date_of_birth"].widget.attrs.update(
            {
                "class": "form-control",
            }
        )
        self.fields["student_place_of_birth"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "City or town",
            }
        )
        self.fields["student_gender"].widget.attrs.update(
            {
                "class": "form-select",
            }
        )
        self.fields["student_status"].widget.attrs.update(
            {
                "class": "form-select",
            }
        )
        self.fields["student_joined_term"].widget.attrs.update(
            {
                "class": "form-select",
            }
        )
        self.fields["student_joined_date"].widget.attrs.update(
            {
                "class": "form-control",
            }
        )
        self.fields["parent_first_name"].widget.attrs.update(
            {
                "class": "form-control",
            }
        )
        self.fields["parent_last_name"].widget.attrs.update(
            {
                "class": "form-control",
            }
        )
        self.fields["parent_email"].widget.attrs.update(
            {
                "class": "form-control",
                "type": "email",
                "placeholder": "your.email@example.com",
            }
        )
        self.fields["parent_whatsapp"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "e.g., +CC NNN NNN NNNN",
            }
        )
        self.fields["parent_address"].widget.attrs.update(
            {
                "class": "form-control",
                "rows": 2,
            }
        )
        self.fields["referral_code"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Optional referral code",
            }
        )

    def clean_admission_number(self):
        admission = self.cleaned_data["admission_number"].strip()
        try:
            student = StudentProfile.objects.select_related(
                "academic_year", "classroom", "specialty"
            ).get(admission_number__iexact=admission)
        except StudentProfile.DoesNotExist:
            raise forms.ValidationError(
                _("No student found with that admission number.")
            )
        if not student.is_active:
            raise forms.ValidationError(_("This student profile is inactive."))
        self.student = student
        return admission

    def clean(self):
        cleaned = super().clean()
        if getattr(self, "student", None) and self.guardian_user:
            exists = StudentGuardian.objects.filter(
                guardian_user=self.guardian_user,
                student=self.student,
            ).exists()
            if exists:
                raise forms.ValidationError(
                    _("You are already linked to this student.")
                )
        return cleaned

    def save(self) -> StudentGuardian:
        student = self.student
        guardian_user = self.guardian_user
        data = self.cleaned_data

        guardian = StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=student,
            relationship=data["relationship"],
            phone=data.get("phone", ""),
            preferred_contact=data.get("preferred_contact")
            or StudentGuardian.PreferredContact.EMAIL,
            receives_email=True,
            receives_sms=False,
            receives_whatsapp=False,
            can_view_results=data.get("can_view_results", False),
            can_view_finance=data.get("can_view_finance", False),
            email=data.get("parent_email", ""),
            whatsapp_number=data.get("parent_whatsapp", ""),
            address=data.get("parent_address", ""),
        )

        # If student is missing a parent phone, reuse the provided one.
        if not student.parent_phone and guardian.phone:
            student.parent_phone = guardian.phone
            student.save(update_fields=["parent_phone"])

        # If a referral code was provided and student lacks one, set it.
        referral_code = data.get("referral_code", "").strip()
        if referral_code and not student.referral_code:
            student.referral_code = referral_code
            student.save(update_fields=["referral_code"])

        return guardian

    def student_updates(self) -> dict:
        updates = {}
        mapping = {
            "student_date_of_birth": "date_of_birth",
            "student_place_of_birth": "place_of_birth",
            "student_gender": "gender",
            "student_status": "status",
            "student_joined_term": "joined_term",
            "student_joined_date": "joined_date",
        }
        for field, attr in mapping.items():
            value = self.cleaned_data.get(field)
            if value not in (None, "", []):
                updates[attr] = value
        return updates

    def parent_updates(self) -> dict:
        updates = {}
        if self.cleaned_data.get("parent_first_name"):
            updates["first_name"] = self.cleaned_data["parent_first_name"]
        if self.cleaned_data.get("parent_last_name"):
            updates["last_name"] = self.cleaned_data["parent_last_name"]
        if self.cleaned_data.get("parent_email"):
            updates["email"] = self.cleaned_data["parent_email"]
        return updates

    def completeness_score(self) -> int:
        fields = self.ONBOARDING_FIELDS
        if not fields:
            return 0
        filled = 0
        for field in fields:
            value = self.data.get(field, "")
            if isinstance(value, (list, tuple)):
                value = value[0]
            if value and str(value).strip():
                filled += 1
        return int(round((filled / len(fields)) * 100)) if fields else 0


class ClaimInviteForm(forms.Form):
    token = forms.CharField(
        label=_("Invite code"),
        help_text=_("Enter the 6-digit code from the school email or SMS."),
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. ABC123", "autocomplete": "one-time-code"}
        ),
    )

    def __init__(self, *args, **kwargs):
        self.invite = None
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        if not token:
            raise forms.ValidationError(
                _("Please enter the invite code from the school email or SMS.")
            )
        from .models import PendingGuardianInvite  # local import to avoid circulars

        try:
            invite = PendingGuardianInvite.objects.select_related("student").get(
                token=token
            )
        except PendingGuardianInvite.DoesNotExist:
            raise forms.ValidationError(
                _(
                    "That code wasn't found or has already been used. Please check the code from the school email or SMS, or contact the school for a new invite."
                )
            )
        if invite.is_claimed:
            raise forms.ValidationError(_("This invite has already been claimed."))
        self.invite = invite
        return token


class TeacherLeaveForm(forms.ModelForm):
    class Meta:
        model = TeacherLeaveRequest
        fields = ("start_date", "end_date", "reason")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Reason for leave"}
            ),
        }


class TeacherOnboardingForm(forms.Form):
    """Multi-step form for teacher onboarding"""

    # Step 1: Basic Information
    email = forms.EmailField(
        label=_("Email address"),
        help_text=_("Used for login and notifications"),
    )
    first_name = forms.CharField(
        label=_("First name"),
        max_length=150,
    )
    last_name = forms.CharField(
        label=_("Last name"),
        max_length=150,
    )
    phone = forms.CharField(
        label=_("Phone number"),
        max_length=50,
        help_text=_("e.g., +CC NNN NNN NNNN"),
        required=False,
    )

    # Step 2: Professional Details
    staff_id = forms.CharField(
        label=_("Staff ID"),
        max_length=50,
        required=False,
        help_text=_("Optional: Your employee/staff identification number"),
    )
    position_title = forms.CharField(
        label=_("Position/Title"),
        max_length=120,
        required=False,
        help_text=_("e.g., Mathematics Teacher, Head of Department"),
    )
    department = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("Department"),
        help_text=_("Select your department"),
    )

    # Step 3: Preferences
    payment_method = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Preferred payment method"),
        help_text=_("How you prefer to receive salary payments"),
    )
    default_dashboard_view = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Default dashboard view"),
    )
    # Step 4: Profile photo (used on digital ID)
    profile_photo = forms.ImageField(
        required=False,
        label=_("Profile photo"),
        help_text=_("Photo for your digital ID card. You can update it later."),
    )

    def __init__(self, *args, **kwargs):
        from apps.academics.models import Department
        from apps.people.models import TeacherProfile

        school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)

        # Populate department choices
        self.fields["department"].queryset = (
            Department.objects.filter(school=school).order_by("name")
            if school
            else Department.objects.none()
        )

        # Populate payment method choices
        self.fields["payment_method"].choices = TeacherProfile.PaymentMethod.choices

        # Populate dashboard view choices
        self.fields[
            "default_dashboard_view"
        ].choices = TeacherProfile.DashboardView.choices

        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, forms.EmailInput):
                field.widget.attrs.update({"class": "form-control", "type": "email"})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({"class": "form-select"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-control"})

        # Auto-focus on email
        self.fields["email"].widget.attrs.update({"autofocus": True})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        from apps.accounts.models import User

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("A user with this email already exists."))
        return email


class StudentOnboardingForm(forms.Form):
    """Multi-step form for student pre-registration"""

    # Step 1: Basic Information
    first_name = forms.CharField(
        label=_("First name"),
        max_length=150,
    )
    last_name = forms.CharField(
        label=_("Last name"),
        max_length=150,
    )
    date_of_birth = forms.DateField(
        label=_("Date of birth"),
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    gender = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Gender"),
    )
    place_of_birth = forms.CharField(
        label=_("Place of birth"),
        max_length=100,
        required=False,
    )

    # Step 2: Academic Information
    academic_year = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("Academic year"),
    )
    specialty = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("Specialty"),
    )
    classroom = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("Classroom"),
    )
    admission_number = forms.CharField(
        label=_("Admission number"),
        max_length=50,
        required=False,
        help_text=_("Leave blank for auto-generation, or enter manually"),
    )

    # Step 3: Parent/Guardian Information
    parent_first_name = forms.CharField(
        label=_("Parent/Guardian first name"),
        max_length=150,
        required=False,
    )
    parent_last_name = forms.CharField(
        label=_("Parent/Guardian last name"),
        max_length=150,
        required=False,
    )
    parent_email = forms.EmailField(
        label=_("Parent/Guardian email"),
        required=False,
    )
    parent_phone = forms.CharField(
        label=_("Parent/Guardian phone"),
        max_length=50,
        required=False,
        help_text=_("e.g., +CC NNN NNN NNNN"),
    )
    parent_whatsapp = forms.CharField(
        label=_("Parent/Guardian WhatsApp"),
        max_length=50,
        required=False,
    )

    # Step 4: Payment (Optional)
    payment_method = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Preferred payment method"),
    )
    referral_code = forms.CharField(
        label=_("Referral code"),
        max_length=50,
        required=False,
        help_text=_("Optional: if someone referred you"),
    )
    # Step 5: Profile photo (for digital ID)
    profile_photo = forms.ImageField(
        required=False,
        label=_("Profile photo"),
        help_text=_("Photo for the student's digital ID. Can be updated later."),
    )

    def __init__(self, *args, **kwargs):
        from apps.academics.models import AcademicYear, Specialty, Classroom
        from apps.people.models import StudentProfile

        try:
            from apps.finance.payment_models import PaymentMethod
        except ImportError:
            PaymentMethod = None

        policy = kwargs.pop("policy", None) or {}
        school = kwargs.pop("school", None)
        self._admissions_policy = (
            (policy.get("admissions") or {}) if isinstance(policy, dict) else {}
        )

        super().__init__(*args, **kwargs)
        # Section 23.4: policy-driven field visibility, required, picker options
        try:
            from apps.policies.form_policy import apply_form_policy

            apply_form_policy(self, "student_onboarding", policy, school=school)
        except _FORM_POLICY_ERRORS:
            logger.debug(
                "apply_form_policy (student_onboarding) skipped", exc_info=True
            )
        # Populate academic year choices
        # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
        academic_years = AcademicYear.objects.filter(is_active=True)
        if school is not None:
            academic_years = academic_years.filter(school=school)
        self.fields["academic_year"].queryset = academic_years.order_by("-start_date")

        # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
        # Populate specialty choices
        specialties = Specialty.objects.all()
        if school is not None and hasattr(Specialty, "school_id"):
            specialties = specialties.filter(school=school)
        self.fields["specialty"].queryset = specialties.order_by("name")
# tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context

        # Populate classroom choices
        # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
        classrooms = Classroom.objects.all()
        if school is not None:
            classrooms = classrooms.filter(school=school)
        self.fields["classroom"].queryset = classrooms.order_by("name")

        # Populate gender choices
        self.fields["gender"].choices = StudentProfile.Gender.choices

        # Populate payment method choices
        if PaymentMethod:
            try:
                payment_methods = PaymentMethod.objects.filter(is_active=True).order_by(
                    "name"
                )
                self.fields["payment_method"].choices = [("", "---------")] + [
                    (str(pm.id), pm.name) for pm in payment_methods
                ]
            except (DatabaseError, ObjectDoesNotExist, AttributeError, TypeError):
                # Fallback to text choices if model not available
                from apps.finance.models import PaymentMethod as PaymentMethodChoices

                self.fields["payment_method"].choices = [("", "---------")] + list(
                    PaymentMethodChoices.choices
                )
        else:
            # Use text choices as fallback
            from apps.finance.models import PaymentMethod as PaymentMethodChoices

            self.fields["payment_method"].choices = [("", "---------")] + list(
                PaymentMethodChoices.choices
            )

        # Add Bootstrap classes
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, forms.EmailInput):
                field.widget.attrs.update({"class": "form-control", "type": "email"})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({"class": "form-select"})
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({"class": "form-control"})

        # Auto-focus on first name
        self.fields["first_name"].widget.attrs.update({"autofocus": True})

    def clean_admission_number(self):
        admission = self.cleaned_data.get("admission_number", "").strip()
        if admission:
            from apps.people.models import StudentProfile
            import re

            admissions = self._admissions_policy
            if not admissions:
                site = get_effective_site_settings(school=getattr(self, "school", None))
                admissions = {
                    "admission_number_mode": getattr(
                        site, "admission_number_mode", "AUTO_OR_MANUAL"
                    ),
                    "admission_number_pattern": (
                        getattr(site, "admission_number_pattern", None) or ""
                    )
                    or "",
                    "school_code": getattr(site, "school_code", None)
                    or _default_school_code(None),
                }
            mode = admissions.get("admission_number_mode", "AUTO_OR_MANUAL")
            if mode == "AUTO":
                return ""

            pattern = (admissions.get("admission_number_pattern") or "").strip()
            if pattern and not re.match(pattern, admission):
                # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
                raise forms.ValidationError(
                    _("Admission number does not match the required format.")
                # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
                )

            # tenant-isolation-allow: form-queryset-filtered-in-view-with-school-context
            if StudentProfile.objects.filter(
                admission_number__iexact=admission
            ).exists():
                raise forms.ValidationError(
                    _("This admission number is already in use.")
                )
        return admission


class LessonPlanUploadForm(forms.ModelForm):
    class Meta:
        model = LessonPlan
        fields = ("title", "week_start_date", "file")
        widgets = {
            "week_start_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True


class LessonPlanAttachmentForm(forms.ModelForm):
    """Add a resource file to an existing lesson plan (Wave 6)."""

    class Meta:
        model = LessonPlanAttachment
        fields = ("file", "label")
        widgets = {
            "label": forms.TextInput(
                attrs={"placeholder": _("e.g. Worksheet, Slides")}
            ),
        }


class TeacherTrainingEntryForm(forms.ModelForm):
    class Meta:
        model = TeacherTrainingEntry
        fields = ("title", "date", "description", "document")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "document": forms.FileInput(attrs={"accept": ".pdf,.doc,.docx"}),
        }


class CahierDeTexteEntryForm(forms.ModelForm):
    class Meta:
        model = CahierDeTexteEntry
        fields = (
            "subject_assignment",
            "entry_date",
            "lesson_topic_code",
            "title",
            "objectives",
            "duration_minutes",
            "content_summary",
            "practical_application",
            "integration_activity",
        )
        widgets = {
            "entry_date": forms.DateInput(attrs={"type": "date"}),
            "objectives": forms.Textarea(attrs={"rows": 3}),
            "content_summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("subject_assignment", "entry_date", "title"):
            if name in self.fields:
                self.fields[name].required = True


class AttendanceJustificationForm(forms.ModelForm):
    class Meta:
        model = AttendanceJustification
        fields = ("student", "attendance_date", "reason", "document")
        widgets = {
            "attendance_date": forms.DateInput(attrs={"type": "date"}),
            "document": forms.FileInput(
                attrs={"accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png"}
            ),
        }
