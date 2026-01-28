from django import forms
from django.utils.translation import gettext_lazy as _

from apps.people.models import StudentGuardian, StudentProfile, TeacherLeaveRequest
from apps.siteconfig.models import SiteSettings
from apps.academics.models import Term, AcademicYear


class LinkChildForm(forms.Form):
    admission_number = forms.CharField(
        label=_("Admission number"),
        help_text=_("Enter the student's admission number (YY + SCHOOL + #### + SPEC + CLASS)."),
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
        school_code = kwargs.pop("school_code", None) or SiteSettings.get_solo().school_code
        super().__init__(*args, **kwargs)
        # Populate dynamic term choices from active academic year
        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year:
            terms = Term.objects.filter(academic_year=active_year).order_by("start_date")
            self.fields["student_joined_term"].choices = [(t.name, t.label) for t in terms]
        else:
            self.fields["student_joined_term"].choices = []
        if school_code:
            self.fields["admission_number"].help_text = _(
                f"Format: YY + {school_code} + #### + SPEC + CLASS (no dashes)."
            )
        self.fields["referral_code"].help_text = _(
            "Include a referral code if someone shared one with you; this unlocks bonus credits."
        )
        
        # Add Bootstrap classes for wizard styling
        self.fields["admission_number"].widget.attrs.update({
            "class": "form-control form-control-lg",
            "placeholder": "Enter admission number",
            "autofocus": True,
        })
        self.fields["relationship"].widget.attrs.update({
            "class": "form-select form-select-lg",
        })
        self.fields["phone"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "e.g., +237 6XX XXX XXX",
        })
        self.fields["preferred_contact"].widget.attrs.update({
            "class": "form-select",
        })
        self.fields["student_date_of_birth"].widget.attrs.update({
            "class": "form-control",
        })
        self.fields["student_place_of_birth"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "City or town",
        })
        self.fields["student_gender"].widget.attrs.update({
            "class": "form-select",
        })
        self.fields["student_status"].widget.attrs.update({
            "class": "form-select",
        })
        self.fields["student_joined_term"].widget.attrs.update({
            "class": "form-select",
        })
        self.fields["student_joined_date"].widget.attrs.update({
            "class": "form-control",
        })
        self.fields["parent_first_name"].widget.attrs.update({
            "class": "form-control",
        })
        self.fields["parent_last_name"].widget.attrs.update({
            "class": "form-control",
        })
        self.fields["parent_email"].widget.attrs.update({
            "class": "form-control",
            "type": "email",
            "placeholder": "your.email@example.com",
        })
        self.fields["parent_whatsapp"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "e.g., +237 6XX XXX XXX",
        })
        self.fields["parent_address"].widget.attrs.update({
            "class": "form-control",
            "rows": 2,
        })
        self.fields["referral_code"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Optional referral code",
        })

    def clean_admission_number(self):
        admission = self.cleaned_data["admission_number"].strip()
        try:
            student = StudentProfile.objects.select_related("academic_year", "classroom", "specialty").get(
                admission_number__iexact=admission
            )
        except StudentProfile.DoesNotExist:
            raise forms.ValidationError(_("No student found with that admission number."))
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
                raise forms.ValidationError(_("You are already linked to this student."))
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
            preferred_contact=data.get("preferred_contact") or StudentGuardian.PreferredContact.EMAIL,
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
    token = forms.CharField(label=_("Invite code"))

    def __init__(self, *args, **kwargs):
        self.invite = None
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        from .models import PendingGuardianInvite  # local import to avoid circulars

        try:
            invite = PendingGuardianInvite.objects.select_related("student").get(token=token)
        except PendingGuardianInvite.DoesNotExist:
            raise forms.ValidationError(_("Invite not found or already claimed."))
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
            "reason": forms.Textarea(attrs={"rows": 3, "placeholder": "Reason for leave"}),
        }
