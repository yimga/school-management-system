from django import forms
from django.utils.translation import gettext_lazy as _

from apps.people.models import StudentGuardian, StudentProfile, TeacherLeaveRequest
from apps.siteconfig.models import SiteSettings


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

    def __init__(self, *args, **kwargs):
        self.guardian_user = kwargs.pop("guardian_user", None)
        school_code = kwargs.pop("school_code", None) or SiteSettings.get_solo().school_code
        super().__init__(*args, **kwargs)
        if school_code:
            self.fields["admission_number"].help_text = _(
                f"Format: YY + {school_code} + #### + SPEC + CLASS (no dashes)."
            )

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
