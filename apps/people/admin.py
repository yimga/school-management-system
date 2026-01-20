from django.contrib import admin, messages

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from apps.portal.models import PendingGuardianInvite
from .models import TeacherProfile, StudentProfile, StudentGuardian


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 1
    autocomplete_fields = ("guardian_user",)
    fields = (
        "guardian_user",
        "relationship",
        "phone",
        "address",
        "preferred_contact",
        "receives_email",
        "receives_sms",
        "receives_whatsapp",
        "can_view_results",
        "can_view_finance",
    )


class StudentProfileAdminForm(forms.ModelForm):
    """
    Admin form that keeps admission numbers editable but convenient:
    - If blank, auto-generate using the model helper (YY + SCHOOL + #### + SPEC + CLASS).
    - If parent_phone is blank, fall back to the first guardian phone on save.
    - Exposes referral_code and parent_phone with clearer help text.
    """

    class Meta:
        model = StudentProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["admission_number"].help_text = _(
            "Format: YY + SCHOOL + #### + SPEC + CLASS (no dashes). Leave blank to auto-generate."
        )
        self.fields["parent_phone"].help_text = _(
            "If blank, we'll reuse the first guardian phone on save."
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
    inlines = (StudentGuardianInline,)
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

    actions = ("create_guardian_invites",)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        student = form.instance
        if student and not student.parent_phone:
            guardian = student.guardian_links.exclude(phone="").first()
            if guardian and guardian.phone:
                student.parent_phone = guardian.phone
                student.save(update_fields=["parent_phone"])

    def create_guardian_invites(self, request, queryset):
        created = 0
        for student in queryset:
            PendingGuardianInvite.objects.create(
                student=student,
                invited_phone=student.parent_phone or "",
                relationship=PendingGuardianInvite.Relationship.GUARDIAN,
                preferred_contact=(
                    PendingGuardianInvite.PreferredContact.SMS
                    if student.parent_phone
                    else PendingGuardianInvite.PreferredContact.EMAIL
                ),
                referral_code=student.referral_code or "",
                created_by=request.user,
            )
            created += 1
        self.message_user(
            request,
            _(f"Created {created} guardian invite(s). Parents can claim via the portal."),
            level=messages.SUCCESS,
        )

    create_guardian_invites.short_description = _("Create guardian invites")


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
    autocomplete_fields = ("guardian_user", "student")
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
