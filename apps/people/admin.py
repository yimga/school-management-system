from decimal import Decimal
from django.contrib import admin, messages
from django.db.models import Q
from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from apps.portal.models import PendingGuardianInvite
from apps.finance.models import ReferralReward
from apps.siteconfig.models import SiteSettings
from config.admin import register_tenant_admin
from .models import (
    TeacherProfile,
    InformationTag,
    StudentProfile,
    StudentGuardian,
    StudentResourceReturn,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
    BadgeType,
    Badge,
    BadgeScanEvent,
    EmployerProfile,
    TenantAuditLog,
    Applicant,
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
        (
            "Custom attributes (Phase C)",
            {
                "fields": ("custom_attributes",),
                "description": _("Key/value pairs for school-defined custom fields. Define keys in School → Settings → custom_field_definitions.staff (e.g. [{\"key\": \"certifications\", \"label\": \"Certifications\", \"type\": \"text\"}])."),
            },
        ),
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
        (
            "Custom attributes (Phase C)",
            {
                "fields": ("custom_attributes",),
                "description": _("Key/value pairs for school-defined custom fields. Define keys in School → Settings → custom_field_definitions.students (e.g. [{\"key\": \"blood_group\", \"label\": \"Blood Group\", \"type\": \"text\"}])."),
            },
        ),
        (
            "Information tags",
            {
                "fields": ("tags",),
                "description": _("School-defined tags (e.g. Scholarship, Early Bird, Allergy). Used by the AI Nuance Engine for discounts and workflows. Manage tags in Site Settings → Tag Manager."),
            },
        ),
        ("Flags", {"fields": ("is_active", "uses_transport")}),
    )

    filter_horizontal = ("tags",)
    actions = ("create_guardian_invites", "issue_referral_rewards")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tags":
            from .models import InformationTag
            obj = kwargs.get("obj")
            school_id = (obj.school_id if obj else None) or request.session.get("school_id")
            if school_id:
                kwargs["queryset"] = InformationTag.objects.filter(school_id=school_id, is_active=True).order_by("sort_order", "name")
            else:
                kwargs["queryset"] = InformationTag.objects.filter(is_active=True).order_by("school", "sort_order", "name")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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
        from apps.platform_runtime.helpers import get_effective_site_settings
        site = get_effective_site_settings(request=request)
        amount = (getattr(site, "referral_bonus_amount", None) or Decimal("0.00")) if site else Decimal("0.00")
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
        from apps.platform_runtime.helpers import get_effective_flags_for_school
        school = getattr(getattr(obj, "student", None), "school", None)
        flags = get_effective_flags_for_school(school) or {}
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


class InformationTagAdmin(ModelAdmin):
    list_display = ("name", "school", "category", "is_private", "is_critical", "is_active", "sort_order")
    list_filter = ("category", "is_private", "is_critical", "is_active")
    search_fields = ("name", "description")
    raw_id_fields = ("school",)
    ordering = ("school", "sort_order", "name")


# Register all models with custom admin site
register_tenant_admin(InformationTag, InformationTagAdmin)
register_tenant_admin(TeacherProfile, TeacherProfileAdmin)
register_tenant_admin(StudentProfile, StudentProfileAdmin)
register_tenant_admin(StudentGuardian, StudentGuardianAdmin)
register_tenant_admin(TeacherPayRecord, TeacherPayRecordAdmin)
register_tenant_admin(TeacherLeaveRequest, TeacherLeaveRequestAdmin)
register_tenant_admin(TeacherAttendance, TeacherAttendanceAdmin)


class StudentResourceReturnAdmin(ModelAdmin):
    list_display = ("student", "academic_year", "item_label", "returned_at", "updated_at")
    list_filter = ("academic_year", "item_label")
    search_fields = ("student__first_name", "student__last_name", "item_label")
    raw_id_fields = ("student",)
    date_hierarchy = "returned_at"


register_tenant_admin(StudentResourceReturn, StudentResourceReturnAdmin)


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


register_tenant_admin(BadgeType, BadgeTypeAdmin)
register_tenant_admin(Badge, BadgeAdmin)
register_tenant_admin(BadgeScanEvent, BadgeScanEventAdmin)


class EmployerProfileAdmin(ModelAdmin):
    list_display = ("user", "company_name", "school", "is_active", "updated_at")
    list_filter = ("is_active", "school")
    search_fields = ("company_name", "user__username")
    raw_id_fields = ("user", "school")


register_tenant_admin(EmployerProfile, EmployerProfileAdmin)


class TenantAuditLogAdmin(ModelAdmin):
    list_display = ("table_name", "record_id", "action", "changed_by", "changed_at")
    list_filter = ("action", "table_name")
    search_fields = ("table_name", "record_id", "correlation_id")
    readonly_fields = (
        "table_name", "record_id", "action", "old_values", "new_values",
        "changed_by", "changed_at", "correlation_id", "request_meta",
    )
    ordering = ["-changed_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


register_tenant_admin(TenantAuditLog, TenantAuditLogAdmin)


class ApplicantAdmin(ModelAdmin):
    list_display = ("last_name", "first_name", "email", "stage", "lead_source", "school", "created_at")
    list_filter = ("stage", "school")
    search_fields = ("first_name", "last_name", "email", "lead_source")
    raw_id_fields = ("school", "assigned_recruiter")
    ordering = ["-created_at"]


register_tenant_admin(Applicant, ApplicantAdmin)

