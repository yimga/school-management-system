from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Q
from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from apps.portal.models import PendingGuardianInvite
from apps.finance.models import ReferralReward
from apps.siteconfig.models import SiteSettings
from config.admin import admin_site
from .models import (
    TeacherProfile,
    StudentProfile,
    StudentGuardian,
    StudentResourceReturn,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
    BadgeType,
    Badge,
    BadgeScanEvent,
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


class TeacherProfileAdmin(ModelAdmin):
    list_display = (
        "teacher_display_in_list",
        "staff_id",
        "phone",
        "department",
        "position_title",
        "pay_scale",
        "pay_grade",
        "salary_amount",
        "next_pay_date",
    )
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "staff_id")
    list_filter = ("department", "pay_scale", "default_dashboard_view", "allow_leave_approvals", "allow_finance_panel")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    fieldsets = (
        ("Basic Information", {
            "fields": ("user", "staff_id", "phone", "profile_photo", "is_active")
        }),
        ("Position & Department", {
            "fields": ("position_title", "department", "reports_to")
        }),
        ("Compensation", {
            "fields": ("pay_scale", "pay_grade", "salary_amount", "salary_cap", "next_pay_date", "paystub_notes"),
            "description": "Assign a pay scale for structured salary management, or use pay_grade (legacy text field) and salary_amount directly."
        }),
        ("Payment Method", {
            "fields": ("payment_method",)
        }),
        ("Dashboard & Permissions", {
            "fields": (
                "default_dashboard_view",
                "allow_finance_panel",
                "allow_paystub_access",
                "allow_leave_approvals",
                "mark_reminder_opt_in",
            )
        }),
    )
    actions = ["apply_pay_scale_to_teachers"]
    
    def apply_pay_scale_to_teachers(self, request, queryset):
        """Apply pay scale default salary to selected teachers"""
        updated = 0
        for teacher in queryset:
            if teacher.pay_scale and teacher.pay_scale.default_salary:
                if not teacher.salary_amount or request.POST.get('force_update') == 'yes':
                    teacher.salary_amount = teacher.pay_scale.default_salary
                    teacher.pay_grade = teacher.pay_scale.code  # Sync pay_grade with scale code
                    teacher.save(update_fields=['salary_amount', 'pay_grade'])
                    updated += 1
        self.message_user(request, f"Updated {updated} teacher(s) with pay scale default salaries.")
    apply_pay_scale_to_teachers.short_description = "Apply pay scale default salary"

    def teacher_display_in_list(self, obj):
        """Display teacher with photo thumbnail in list view"""
        from django.utils.html import format_html
        
        photo_url = obj.profile_photo.url if obj.profile_photo else None
        user = obj.user
        
        # Build HTML with optional photo
        if photo_url:
            return format_html(
                '<div class="admin-display-user admin-display-user-large">'
                '<img src="{}" class="admin-user-avatar admin-user-avatar-large" />'
                '<div class="admin-user-info">'
                '<div class="admin-user-name">{}</div>'
                '<div class="admin-user-meta">{}</div>'
                '</div>'
                '</div>',
                photo_url,
                user.get_full_name() or user.username,
                user.username
            )
        else:
            initials = f"{user.first_name[0]}{user.last_name[0]}".upper() if user.first_name and user.last_name else user.username[:2].upper()
            return format_html(
                '<div class="admin-display-user admin-display-user-large">'
                '<div class="admin-user-avatar-fallback admin-user-avatar-fallback-large">{}</div>'
                '<div class="admin-user-info">'
                '<div class="admin-user-name">{}</div>'
                '<div class="admin-user-meta">{}</div>'
                '</div>'
                '</div>',
                initials,
                user.get_full_name() or user.username,
                user.username
            )
    teacher_display_in_list.short_description = "Teacher"


class StudentProfileAdmin(ModelAdmin):
    form = StudentProfileAdminForm
    inlines = (StudentGuardianInline,)
    list_display = (
        "student_display_in_list",
        "academic_year",
        "classroom",
        "specialty",
        "is_active",
        "uses_transport",
        "parent_completeness",
    )
    list_filter = ("academic_year", "classroom", "specialty", "is_active", "uses_transport")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
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
        ("Flags", {"fields": ("is_active", "uses_transport")}),
    )

    actions = ("create_guardian_invites", "issue_referral_rewards")

    def student_display_in_list(self, obj):
        """Display student with photo thumbnail in list view"""
        from django.utils.html import format_html
        
        photo_url = obj.profile_photo.url if obj.profile_photo else None
        
        # Build HTML with optional photo
        if photo_url:
            return format_html(
                '<div class="admin-display-user admin-display-user-large">'
                '<img src="{}" class="admin-user-avatar admin-user-avatar-large admin-student-avatar" />'
                '<div class="admin-user-info">'
                '<div class="admin-user-name">{}</div>'
                '<div class="admin-user-meta">{}</div>'
                '</div>'
                '</div>',
                photo_url,
                obj.get_full_name(),
                obj.student_code
            )
        else:
            return format_html(
                '<div class="admin-display-user admin-display-user-large">'
                '<div class="admin-user-avatar-fallback admin-user-avatar-fallback-large admin-student-avatar-fallback">{}</div>'
                '<div class="admin-user-info">'
                '<div class="admin-user-name">{}</div>'
                '<div class="admin-user-meta">{}</div>'
                '</div>'
                '</div>',
                obj.first_name[0].upper() if obj.first_name else "S",
                obj.get_full_name(),
                obj.student_code
            )
    student_display_in_list.short_description = "Student"

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


class StudentGuardianAdmin(ModelAdmin):
    list_display = (
        "guardian_display_with_photo",
        "student_display_with_photo",
        "relationship",
        "phone",
        "email",
        "preferred_contact",
        "can_view_results",
        "can_view_finance",
        "finance_access_state",
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
        ("can_view_finance", admin.BooleanFieldListFilter),
    )
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("guardian_user__username", "guardian_user__email", "student__student_code", "student__last_name")
    actions = ("grant_finance_access", "revoke_finance_access")

    def guardian_display_with_photo(self, obj):
        """Display guardian user with optional photo thumbnail"""
        from django.utils.html import format_html
        from django.urls import reverse
        
        guardian = obj.guardian_user
        if not guardian:
            return "—"
        
        # Try to get photo from user profile if it exists
        photo_url = None
        if hasattr(guardian, 'profile') and guardian.profile.profile_photo:
            photo_url = guardian.profile.profile_photo.url
        
        # Build HTML with CSS classes matching sidebar theme
        if photo_url:
            return format_html(
                '<div class="admin-display-user">'
                '<img src="{}" class="admin-user-avatar" />'
                '<span class="admin-user-name">{}</span>'
                '</div>',
                photo_url,
                guardian.get_full_name() or guardian.username
        )
        else:
            return format_html(
                '<div class="admin-display-user">'
                '<div class="admin-user-avatar-fallback">{}</div>'
                '<span class="admin-user-name">{}</span>'
                '</div>',
                guardian.first_name[0].upper() if guardian.first_name else guardian.username[0].upper(),
                guardian.get_full_name() or guardian.username
            )
    guardian_display_with_photo.short_description = "Guardian"

    def finance_access_state(self, obj):
        from apps.siteconfig.models import SiteSettings
        flags = getattr(SiteSettings.get_solo(), "backend_feature_flags", {}) or {}
        require = bool(flags.get("require_guardian_finance_opt_in"))
        if require:
            return "Granted" if obj.can_view_finance else "Blocked (opt-in required)"
        return "Granted (opt-in off)" if obj.can_view_finance else "Allowed (opt-in off)"

    finance_access_state.short_description = "Finance access"

    def student_display_with_photo(self, obj):
        """Display student with optional photo thumbnail"""
        from django.utils.html import format_html
        
        student = obj.student
        if not student:
            return "—"
        
        photo_url = student.profile_photo.url if student.profile_photo else None
        
        # Build HTML with optional photo
        if photo_url:
            return format_html(
                '<div class="admin-display-user">'
                '<img src="{}" class="admin-student-avatar" />'
                '<span class="admin-user-name">{} <span class="admin-user-code">({})</span></span>'
                '</div>',
                photo_url,
                student.get_full_name(),
                student.student_code
            )
        else:
            return format_html(
                '<div class="admin-display-user">'
                '<div class="admin-user-avatar-fallback admin-student-avatar-fallback">{}</div>'
                '<span class="admin-user-name">{} <span class="admin-user-code">({})</span></span>'
                '</div>',
                student.first_name[0].upper() if student.first_name else "S",
                student.get_full_name(),
                student.student_code
            )
    student_display_with_photo.short_description = "Student"

    def grant_finance_access(self, request, queryset):
        updated = queryset.update(can_view_finance=True)
        self.message_user(request, f"Granted finance access to {updated} guardian link(s).")

    grant_finance_access.short_description = "Grant finance access to selected guardians"

    def revoke_finance_access(self, request, queryset):
        updated = queryset.update(can_view_finance=False)
        self.message_user(request, f"Revoked finance access for {updated} guardian link(s).")

    revoke_finance_access.short_description = "Revoke finance access for selected guardians"


class TeacherPayRecordAdmin(ModelAdmin):
    list_display = ("teacher", "record_type", "amount", "effective_date", "created_by", "created_at")
    list_filter = ("record_type", "effective_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher", "created_by")


class TeacherLeaveRequestAdmin(ModelAdmin):
    list_display = ("teacher", "start_date", "end_date", "status", "approver", "decided_at")
    list_filter = ("status", "start_date", "end_date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher", "approver")


class TeacherAttendanceAdmin(ModelAdmin):
    list_display = ("teacher", "date", "status", "check_in", "check_out")
    list_filter = ("status", "date")
    list_per_page = 50  # PERFORMANCE: Add pagination
    show_full_result_count = False
    search_fields = ("teacher__user__username", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    autocomplete_fields = ("teacher",)


# Register all models with custom admin site
admin_site.register(TeacherProfile, TeacherProfileAdmin)
admin_site.register(StudentProfile, StudentProfileAdmin)
admin_site.register(StudentGuardian, StudentGuardianAdmin)
admin_site.register(TeacherPayRecord, TeacherPayRecordAdmin)
admin_site.register(TeacherLeaveRequest, TeacherLeaveRequestAdmin)
admin_site.register(TeacherAttendance, TeacherAttendanceAdmin)


class StudentResourceReturnAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "item_label", "returned_at", "updated_at")
    list_filter = ("academic_year", "item_label")
    search_fields = ("student__first_name", "student__last_name", "item_label")
    raw_id_fields = ("student",)
    date_hierarchy = "returned_at"


admin_site.register(StudentResourceReturn, StudentResourceReturnAdmin)


class BadgeTypeAdmin(ModelAdmin):
    list_display = ("code", "label", "audience", "sort_order", "is_active", "created_at")
    list_editable = ("sort_order", "is_active")
    list_filter = ("audience", "is_active")
    search_fields = ("code", "label")
    ordering = ["audience", "sort_order", "code"]


class BadgeExpiryFilter(admin.SimpleListFilter):
    title = _("expiry")
    parameter_name = "expiry"

    def lookups(self, request, model_admin):
        return [
            ("expired", _("Expired")),
            ("active", _("Active (not expired)")),
        ]

    def queryset(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        if self.value() == "expired":
            return queryset.filter(expiry_at__isnull=False, expiry_at__lte=now)
        if self.value() == "active":
            return queryset.filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=now))
        return queryset


class BadgeAdmin(ModelAdmin):
    list_display = ("badge_type", "user", "student", "issued_at", "expiry_at", "is_physical_printed")
    list_filter = ("badge_type", BadgeExpiryFilter)
    search_fields = ("badge_type__label", "user__username", "student__admission_number")
    raw_id_fields = ("user", "student")
    actions = ["revoke_selected_badges"]

    def revoke_selected_badges(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(expiry_at=timezone.now())
        self.message_user(request, _(f"Revoked {updated} badge(s)."))
    revoke_selected_badges.short_description = _("Revoke selected badges")


class BadgeScanEventAdmin(ModelAdmin):
    list_display = ("verified_at", "token_kind", "user", "student", "verified", "ip_address")
    list_filter = ("token_kind", "verified")
    search_fields = ("user__username", "student__admission_number", "ip_address")
    raw_id_fields = ("badge", "user", "student")
    readonly_fields = ("verified_at", "ip_address", "user_agent")
    date_hierarchy = "verified_at"


admin_site.register(BadgeType, BadgeTypeAdmin)
admin_site.register(Badge, BadgeAdmin)
admin_site.register(BadgeScanEvent, BadgeScanEventAdmin)

