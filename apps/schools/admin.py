from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from config.admin import platform_admin_site, register_tenant_admin

from .models import (
    DonationPledge,
    FundraisingCampaign,
    InKindDonation,
    School,
    SchoolMembership,
    SchoolProvisioningEvent,
    TenantApiUsage,
    TenantQuotaLimit,
)


def _school_has_billing():
    return hasattr(School, "plan") and hasattr(School, "billing_type")


def _theme_branding_fields():
    base = [
        "logo_url",
        "primary_color",
        "accent_color",
        "custom_domain",
        "custom_domain_verified",
    ]
    if hasattr(School, "theme_choice"):
        return ("theme_choice",) + tuple(base)
    return tuple(base)


@admin.register(School, site=platform_admin_site)
class SchoolAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "subdomain",
        *(
            ["plan", "billing_type", "waiver_note_short"]
            if _school_has_billing()
            else []
        ),
        "sub_system",
        "is_active",
        "last_activity",
        "created_at",
    )
    list_filter = ("sub_system", "is_active", "is_approved") + (
        ("plan", "billing_type") if _school_has_billing() else ()
    )
    search_fields = ("name", "slug", "subdomain")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "last_activity",
        "hierarchy_path",
    )
    prepopulated_fields = {"subdomain": ["slug"]}
    raw_id_fields = (("plan",) if hasattr(School, "plan") else ()) + (
        "default_region",
        "subdivision",
        "parent_school",
    )
    filter_horizontal = ("education_levels", "education_system_types")

    def _school_fieldsets():
        location_fields = (
            "country_code",
            "default_region",
            "subdivision",
            "compliance_region",
            "timezone",
            "education_levels",
            "education_system_types",
        )
        location_desc = (
            "Canonical school identity: ISO country code, optional subdivision, and registry-backed "
            "education taxonomy. RegionConfig remains the localization/defaults layer."
        )
        if _school_has_billing():
            return (
                (
                    None,
                    {
                        "fields": (
                            "name",
                            "slug",
                            "subdomain",
                            "sub_system",
                            "is_active",
                        )
                    },
                ),
                (
                    "School location",
                    {"fields": location_fields, "description": location_desc},
                ),
                (
                    "Plan & billing",
                    {
                        "fields": (
                            "plan",
                            "addons",
                            "report_platform_bundle_slug",
                            "billing_type",
                            "trial_end_date",
                            "waiver_note",
                        )
                    },
                ),
                ("Theme & branding", {"fields": _theme_branding_fields()}),
                (
                    "Settings (JSON)",
                    {
                        "fields": ("settings", "features"),
                        "description": 'settings: grading_logic, term_count, custom_field_definitions (Phase C). Example: {"custom_field_definitions": {"students": [{"key": "blood_group", "label": "Blood Group", "type": "text"}], "staff": []}}',
                    },
                ),
                ("Parent school", {"fields": ("parent_school", "hierarchy_path")}),
                ("Metadata", {"fields": ("id", "created_at", "updated_at")}),
            )
        return (
            (
                None,
                {"fields": ("name", "slug", "subdomain", "sub_system", "is_active")},
            ),
            (
                "School location",
                {"fields": location_fields, "description": location_desc},
            ),
            ("Theme & branding", {"fields": _theme_branding_fields()}),
            ("Settings (JSON)", {"fields": ("settings", "features")}),
            ("Parent school", {"fields": ("parent_school", "hierarchy_path")}),
            ("Metadata", {"fields": ("id", "created_at", "updated_at")}),
        )

    fieldsets = _school_fieldsets()

    @admin.display(description="Waiver note")
    def waiver_note_short(self, obj):
        if not getattr(obj, "waiver_note", None):
            return "—"
        note = obj.waiver_note
        return note[:50] + "…" if len(note) > 50 else note

    @admin.action(description="Waive subscription (set COMPLIMENTARY)")
    def waive_subscription(self, request, queryset):
        """Phase E: Redirect to waiver form so user can enter required waiver_note."""
        ids = ",".join(str(q.pk) for q in queryset)
        from django.urls import reverse
        from django.http import HttpResponseRedirect

        url = reverse("admin:schools_school_waive_form") + "?ids=" + ids
        return HttpResponseRedirect(url)

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        if _school_has_billing():
            custom = [
                path(
                    "waive-subscription/",
                    self.admin_site.admin_view(self.waive_subscription_form_view),
                    name="schools_school_waive_form",
                ),
            ]
            return custom + urls
        return urls

    def waive_subscription_form_view(self, request):
        """Phase E: Form to enter waiver_note, then apply COMPLIMENTARY to selected schools."""
        if not _school_has_billing():
            from django.http import HttpResponseNotFound

            return HttpResponseNotFound()
        from django.template.response import TemplateResponse
        from django.shortcuts import redirect
        from django.urls import reverse
        from apps.siteconfig.models import BillingWaiverAuditLog

        ids_str = (request.GET.get("ids") or request.POST.get("ids") or "").strip()
        ids = [x.strip() for x in ids_str.split(",") if x.strip()]
        schools = list(School.objects.filter(pk__in=ids)) if ids else []

        if request.method == "POST":
            note = (request.POST.get("waiver_note") or "").strip()
            if not note:
                messages.error(request, "Waiver note is required for compliance.")
            elif not schools:
                messages.error(request, "No schools selected.")
            else:
                for school in schools:
                    old_bt = school.billing_type
                    old_wn = school.waiver_note or ""
                    school.billing_type = School.BillingType.COMPLIMENTARY
                    school.waiver_note = note
                    school.save(update_fields=["billing_type", "waiver_note"])
                    BillingWaiverAuditLog.objects.create(
                        school=school,
                        changed_by=request.user,
                        old_billing_type=old_bt,
                        new_billing_type=School.BillingType.COMPLIMENTARY,
                        old_waiver_note=old_wn,
                        new_waiver_note=note,
                    )
                messages.success(
                    request,
                    f"Set billing to COMPLIMENTARY for {len(schools)} school(s).",
                )
                return redirect(reverse("admin:schools_school_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Waive subscription",
            "schools": schools,
            "ids": ids_str,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request, "admin/schools/school/waive_subscription_form.html", context
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if _school_has_billing():
            actions["waive_subscription"] = (
                self.waive_subscription,
                "waive_subscription",
                "Waive subscription (set COMPLIMENTARY)",
            )
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def has_delete_permission(self, request, obj=None):
        """Route permanent delete through Tenant 360 offboarding (inventory + schema drop)."""
        return False

    def delete_view(self, request, object_id, extra_context=None):
        school = self.get_object(request, object_id)
        if school is None:
            return super().delete_view(request, object_id, extra_context)
        offboarding_url = reverse("super:tenant_360", args=[school.pk]) + "#offboarding"
        context = {
            **self.admin_site.each_context(request),
            "title": "Delete school",
            "object": school,
            "offboarding_url": offboarding_url,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/schools/school/delete_guided.html",
            context,
        )

    def delete_model(self, request, obj):
        messages.error(
            request,
            "Use Tenant 360 → Offboarding for permanent delete (typed slug + dry-run inventory).",
        )
        return HttpResponseRedirect(
            reverse("admin:schools_school_change", args=[obj.pk])
        )

    def delete_queryset(self, request, queryset):
        messages.error(
            request,
            "Bulk delete disabled. Use the offboarding queue and Tenant 360 per school.",
        )


@admin.register(SchoolMembership, site=platform_admin_site)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_primary", "created_at")
    list_filter = ("role", "school")
    search_fields = ("user__username", "school__name")


@admin.register(TenantQuotaLimit, site=platform_admin_site)
class TenantQuotaLimitAdmin(admin.ModelAdmin):
    list_display = (
        "school",
        "limit_type",
        "limit_value",
        "period_days",
        "is_active",
        "updated_at",
    )
    list_filter = ("limit_type", "is_active", "school")
    search_fields = ("school__name", "limit_type")
    raw_id_fields = ("school",)


@admin.register(TenantApiUsage, site=platform_admin_site)
class TenantApiUsageAdmin(admin.ModelAdmin):
    list_display = ("school", "period_date", "limit_type", "request_count")
    list_filter = ("limit_type", "period_date", "school")
    search_fields = ("school__name", "limit_type")
    raw_id_fields = ("school",)
    readonly_fields = ("school", "period_date", "limit_type", "request_count")


@admin.register(SchoolProvisioningEvent, site=platform_admin_site)
class SchoolProvisioningEventAdmin(admin.ModelAdmin):
    list_display = ("school", "event_type", "status", "created_at", "created_by")
    list_filter = ("event_type", "status", "school")
    search_fields = ("school__name", "event_type", "message")
    readonly_fields = (
        "school",
        "event_type",
        "status",
        "message",
        "payload",
        "created_by",
        "created_at",
    )


class InKindDonationAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "school",
        "donor",
        "category",
        "quantity",
        "status",
        "inventory_item",
        "received_at",
    )
    list_filter = ("school", "status", "category")
    search_fields = ("description", "donor__display_name", "notes")
    raw_id_fields = ("school", "donor", "campaign", "inventory_item")
    readonly_fields = ("inventory_item", "created_at", "updated_at")


class FundraisingCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "school",
        "status",
        "goal_amount",
        "currency",
        "is_public",
        "start_date",
        "end_date",
    )
    list_filter = ("school", "status", "is_public", "currency")
    search_fields = ("name", "description")
    raw_id_fields = ("school", "award_source")
    readonly_fields = ("created_at", "updated_at")


class DonationPledgeAdmin(admin.ModelAdmin):
    list_display = (
        "donor",
        "school",
        "amount",
        "currency",
        "status",
        "fulfilled_amount",
        "due_date",
    )
    list_filter = ("school", "status", "currency")
    search_fields = ("donor__display_name", "notes")
    raw_id_fields = ("school", "donor", "campaign")
    readonly_fields = ("fulfilled_at", "created_at", "updated_at")


register_tenant_admin(InKindDonation, InKindDonationAdmin)
register_tenant_admin(FundraisingCampaign, FundraisingCampaignAdmin)
register_tenant_admin(DonationPledge, DonationPledgeAdmin)
