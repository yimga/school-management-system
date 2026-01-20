from django.contrib import admin

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from .models import TeacherProfile, StudentProfile, StudentGuardian


class StudentProfileAdminForm(forms.ModelForm):
    """
    Admin form that keeps admission numbers editable but convenient:
    - If blank, auto-generate using the model helper (YY-SCHOOL-####-SPEC-CLASS).
    - If parent_phone is blank, fall back to the first guardian phone on save.
    - Exposes referral_code and parent_phone with clearer help text.
    """

    class Meta:
        model = StudentProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["admission_number"].help_text = _(
            "Format: YY-SCHOOL-####-SPEC-CLASS. Leave blank to auto-generate from year/school code/specialty/class."
        )
        self.fields["parent_phone"].help_text = _(
            "If blank, we’ll reuse the first guardian phone on save."
        )
        if "referral_code" in self.fields:
            self.fields["referral_code"].help_text = _(
                "Auto-generated referral code; editable if you need to override."
            )

    def clean(self):
        cleaned = super().clean()
        # Auto-generate admission if missing but prerequisites are present.
        if not cleaned.get("admission_number"):
            acad = cleaned.get("academic_year")
            spec = cleaned.get("specialty")
            classroom = cleaned.get("classroom")
            if acad and spec and classroom:
                cleaned["admission_number"] = StudentProfile.generate_admission_number(acad, spec, classroom)
                self.cleaned_data["admission_number"] = cleaned["admission_number"]

        # If parent phone missing, reuse guardian phone (if any)
        instance = self.instance
        parent_phone = cleaned.get("parent_phone") or getattr(instance, "parent_phone", "")
        if not parent_phone and instance.pk:
            guardian = instance.guardian_links.first()
            if guardian and guardian.phone:
                cleaned["parent_phone"] = guardian.phone
                self.cleaned_data["parent_phone"] = guardian.phone
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


@admin.register(TeacherProfile)
class TeacherProfileAdmin(ModelAdmin):
    list_display = (
        "user",
        "staff_id",
        "phone",
        "department",
        "position_title",
        "pay_grade",
        "default_dashboard_view",
        "next_pay_date",
        "allow_finance_panel",
        "profile_photo",
    )
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "staff_id")


@admin.register(StudentProfile)
class StudentProfileAdmin(ModelAdmin):
    form = StudentProfileAdminForm
    list_display = (
        "admission_number",
        "student_code",
        "last_name",
        "first_name",
        "academic_year",
        "classroom",
        "specialty",
        "is_active",
        "profile_photo",
        "parent_completeness",
    )
    list_filter = ("academic_year", "classroom", "specialty", "is_active")
    search_fields = ("student_code", "admission_number", "first_name", "last_name")
    readonly_fields = ("parent_completeness",)
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    ("first_name", "last_name", "student_code"),
                    ("admission_number", "academic_year"),
                    ("classroom", "specialty"),
                    ("status", "section"),
                )
            },
        ),
        (
            "Profile",
            {
                "fields": (
                    ("gender", "date_of_birth", "place_of_birth"),
                    ("joined_term", "joined_date"),
                    "profile_photo",
                )
            },
        ),
        (
            "Guardians & contact",
            {
                "fields": (
                    "parent_phone",
                    "referral_code",
                    "parent_completeness",
                )
            },
        ),
        ("Flags", {"fields": ("is_active",)}),
    )


@admin.register(StudentGuardian)
class StudentGuardianAdmin(ModelAdmin):
    list_display = (
        "guardian_user",
        "student",
        "relationship",
        "phone",
        "preferred_contact",
        "receives_email",
        "receives_sms",
        "receives_whatsapp",
        "can_view_results",
        "can_view_finance",
    )
    list_filter = (
        "relationship",
        "preferred_contact",
        "receives_email",
        "receives_sms",
        "receives_whatsapp",
        "can_view_results",
        "can_view_finance",
    )
    search_fields = ("guardian_user__username", "guardian_user__email", "student__student_code", "student__last_name")
