"""Tenant-admin registration for the athletics module.

Follows the repo idiom (see apps/schoolops/admin.py, apps/school_events/admin.py):
``@admin.register(Model, site=tenant_admin_site)`` on a plain ``admin.ModelAdmin``
with ``raw_id_fields`` for every ForeignKey and ``list_select_related`` covering
the FKs shown in ``list_display`` so the changelist never N+1s.

ParticipationConsent is intentionally NOT registered here — it holds token
hashes (sha256) and immutable consent-proof material; it is managed through the
consent service, not the admin.
"""

from django.contrib import admin

from config.admin import tenant_admin_site

from .models import (
    Club,
    ClubAdvisorAssignment,
    ClubMembership,
    CoachAssignment,
    EligibilityRecord,
    Fixture,
    FixtureResult,
    FixtureTravel,
    FixtureVenueBooking,
    MedicalClearance,
    Season,
    Sport,
    Team,
    TeamKitFee,
    TeamMembership,
)

# Shared student search fields (matches the schoolops admin convention).
_STUDENT_SEARCH = (
    "student__first_name",
    "student__last_name",
    "student__admission_number",
    "student__student_code",
)


@admin.register(Sport, site=tenant_admin_site)
class SportAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "category",
        "gender_category",
        "default_squad_size",
        "is_active",
        "school",
    )
    list_filter = ("category", "gender_category", "is_active", "school")
    search_fields = ("name", "code", "school__name")
    raw_id_fields = ("school",)
    list_select_related = ("school",)


@admin.register(Season, site=tenant_admin_site)
class SeasonAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sport",
        "school",
        "academic_year",
        "start_date",
        "end_date",
        "status",
    )
    list_filter = ("status", "school")
    search_fields = ("name", "sport__name", "school__name")
    raw_id_fields = ("school", "sport", "academic_year")
    list_select_related = ("school", "sport", "academic_year")
    date_hierarchy = "start_date"


@admin.register(Team, site=tenant_admin_site)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sport",
        "season",
        "gender",
        "level",
        "roster_cap",
        "status",
        "school",
    )
    list_filter = ("status", "gender", "school")
    search_fields = ("name", "sport__name", "season__name", "school__name")
    raw_id_fields = ("school", "sport", "season", "home_venue")
    list_select_related = ("school", "sport", "season")


@admin.register(CoachAssignment, site=tenant_admin_site)
class CoachAssignmentAdmin(admin.ModelAdmin):
    list_display = ("coach", "team", "role", "is_active", "school", "created_at")
    list_filter = ("role", "is_active", "school")
    search_fields = (
        "coach__first_name",
        "coach__last_name",
        "coach__email",
        "team__name",
    )
    raw_id_fields = ("school", "team", "coach", "teacher_profile")
    list_select_related = ("school", "team", "coach")


@admin.register(Club, site=tenant_admin_site)
class ClubAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "status",
        "capacity",
        "academic_year",
        "school",
    )
    list_filter = ("category", "status", "school")
    search_fields = ("name", "slug", "school__name")
    raw_id_fields = ("school", "academic_year")
    list_select_related = ("school", "academic_year")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ClubAdvisorAssignment, site=tenant_admin_site)
class ClubAdvisorAssignmentAdmin(admin.ModelAdmin):
    list_display = ("advisor", "club", "role", "is_active", "school", "created_at")
    list_filter = ("role", "is_active", "school")
    search_fields = (
        "advisor__first_name",
        "advisor__last_name",
        "advisor__email",
        "club__name",
    )
    raw_id_fields = ("school", "club", "advisor")
    list_select_related = ("school", "club", "advisor")


@admin.register(ClubMembership, site=tenant_admin_site)
class ClubMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "club",
        "role_title",
        "status",
        "joined_at",
        "school",
    )
    list_filter = ("status", "school")
    search_fields = _STUDENT_SEARCH + ("club__name", "role_title")
    raw_id_fields = ("school", "club", "student")
    list_select_related = ("school", "club", "student")


@admin.register(TeamMembership, site=tenant_admin_site)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "team",
        "jersey_number",
        "position",
        "status",
        "joined_at",
        "school",
    )
    list_filter = ("status", "school")
    search_fields = _STUDENT_SEARCH + ("team__name",)
    raw_id_fields = ("school", "team", "student")
    list_select_related = ("school", "team", "student")


@admin.register(MedicalClearance, site=tenant_admin_site)
class MedicalClearanceAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "sport",
        "status",
        "valid_from",
        "valid_until",
        "cleared_by",
        "school",
    )
    list_filter = ("status", "school", "sport")
    search_fields = _STUDENT_SEARCH
    raw_id_fields = ("school", "student", "sport", "cleared_by")
    list_select_related = ("school", "student", "sport", "cleared_by")


@admin.register(EligibilityRecord, site=tenant_admin_site)
class EligibilityRecordAdmin(admin.ModelAdmin):
    list_display = (
        "membership",
        "status",
        "academic_ok",
        "attendance_ok",
        "medical_ok",
        "consent_ok",
        "checked_at",
        "school",
    )
    list_filter = (
        "status",
        "academic_ok",
        "attendance_ok",
        "medical_ok",
        "consent_ok",
        "school",
    )
    search_fields = (
        "membership__student__first_name",
        "membership__student__last_name",
        "reason",
    )
    raw_id_fields = ("school", "membership", "checked_by")
    list_select_related = ("school", "membership", "checked_by")
    readonly_fields = ("checked_at", "snapshot")


@admin.register(Fixture, site=tenant_admin_site)
class FixtureAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "opponent_name",
        "fixture_type",
        "scheduled_start",
        "status",
        "season",
        "school",
    )
    list_filter = ("status", "fixture_type", "school")
    search_fields = ("opponent_name", "team__name", "school__name")
    raw_id_fields = ("school", "team", "season", "opponent_team", "venue", "created_by")
    list_select_related = ("school", "team", "season")
    date_hierarchy = "scheduled_start"


@admin.register(FixtureResult, site=tenant_admin_site)
class FixtureResultAdmin(admin.ModelAdmin):
    list_display = (
        "fixture",
        "home_score",
        "away_score",
        "outcome",
        "is_final",
        "recorded_by",
        "school",
    )
    list_filter = ("outcome", "is_final", "school")
    search_fields = ("fixture__opponent_name", "fixture__team__name")
    raw_id_fields = ("school", "fixture", "recorded_by")
    list_select_related = ("school", "fixture", "recorded_by")


@admin.register(FixtureTravel, site=tenant_admin_site)
class FixtureTravelAdmin(admin.ModelAdmin):
    list_display = (
        "fixture",
        "route",
        "departure_time",
        "return_time",
        "status",
        "school",
    )
    list_filter = ("status", "school")
    search_fields = ("fixture__opponent_name", "pickup_point", "dropoff_point")
    raw_id_fields = ("school", "fixture", "route")
    list_select_related = ("school", "fixture", "route")


@admin.register(TeamKitFee, site=tenant_admin_site)
class TeamKitFeeAdmin(admin.ModelAdmin):
    list_display = ("label", "team", "amount", "is_mandatory", "is_active", "school")
    list_filter = ("is_mandatory", "is_active", "school")
    search_fields = ("label", "team__name", "school__name")
    raw_id_fields = ("school", "team")
    list_select_related = ("school", "team")


@admin.register(FixtureVenueBooking, site=tenant_admin_site)
class FixtureVenueBookingAdmin(admin.ModelAdmin):
    list_display = ("title", "venue", "fixture", "status", "school")
    list_filter = ("status", "school")
    search_fields = ("title", "venue__name", "fixture__opponent_name")
    raw_id_fields = ("school", "venue", "fixture")
    list_select_related = ("school", "venue", "fixture")
