from decimal import Decimal
from django.contrib import admin, messages

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from config.admin import admin_site
from apps.portal.models import PendingGuardianInvite
from apps.finance.models import ReferralReward
from apps.siteconfig.models import SiteSettings
from .models import (
    TeacherProfile,
    StudentProfile,
    StudentGuardian,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
)


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 1
    autocomplete_fields = ("guardian_user",)
    fields = (
        "guardian_user",
        "relationship",
        "phone",
        "email",
        "whatsapp_number",
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


@admin_site.register(TeacherProfile)
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
    list_filter = ("department", "default_dashboard_view", "allow_leave_approvals", "allow_finance_panel")
    list_per_page = 50  # PERFORMANCE: Add pagination


@admin_site.register(StudentProfile)
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
    list_per_page = 50  # PERFORMANCE: Add pagination
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

    actions = ("create_guardian_invites", "issue_referral_rewards")

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

    def issue_referral_rewards(self, request, queryset):
        site = SiteSettings.get_solo()
        amount = site.referral_bonus_amount or Decimal("0.00")
        created = 0
        for student in queryset:
            guardian = student.guardian_links.first()
            if not guardian:
                continue
            reward, new = ReferralReward.objects.get_or_create(
                student=student,
                guardian=guardian,
                defaults={
                    "amount": amount,
                    "description": "Referral reward issued via admin action.",
                    "awarded_by": request.user,
                },
            )
            if new:
                created += 1
        if created:
            self.message_user(
                request,
                _(f"Issued {created} referral reward(s)."),
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _("No reward created (no guardians or rewards already exist)."),
                level=messages.WARNING,
            )

    issue_referral_rewards.short_description = _("Issue referral rewards")


@admin_site.register(StudentGuardian)
class StudentGuardianAdmin(ModelAdmin):
    list_display = (
        "guardian_user",
        "student",
        "relationship",
        "phone",
        "email",
        "whatsapp_number",
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
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("guardian_user__username", "guardian_user__email", "student__student_code", "student__last_name")


@admin_site.register(TeacherPayRecord)
class TeacherPayRecordAdmin(ModelAdmin):
    list_display = ("teacher", "record_type", "amount", "effective_date", "created_by", "created_at")
    list_filter = ("record_type", "effective_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher", "created_by")


@admin_site.register(TeacherLeaveRequest)
class TeacherLeaveRequestAdmin(ModelAdmin):
    list_display = ("teacher", "start_date", "end_date", "status", "approver", "decided_at")
    list_filter = ("status", "start_date", "end_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher", "approver")


@admin_site.register(TeacherAttendance)
class TeacherAttendanceAdmin(ModelAdmin):
    list_display = ("teacher", "date", "status", "check_in", "check_out")
    list_filter = ("status", "date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher",)
