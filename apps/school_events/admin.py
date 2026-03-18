from django.contrib import admin

from config.admin import tenant_admin_site
from apps.school_events.models import (
    EventRegistration,
    EventSponsor,
    EventSponsorCommitment,
    EventTicketTier,
    EventVenue,
    SchoolEvent,
)


@admin.register(EventVenue, site=tenant_admin_site)
class EventVenueAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "capacity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "school__name", "location")


@admin.register(EventSponsor, site=tenant_admin_site)
class EventSponsorAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "tier", "status")
    list_filter = ("tier", "status")
    search_fields = ("name", "school__name", "contact_name", "contact_email")


class EventTicketTierInline(admin.TabularInline):
    model = EventTicketTier
    extra = 0


class EventSponsorCommitmentInline(admin.TabularInline):
    model = EventSponsorCommitment
    extra = 0


@admin.register(SchoolEvent, site=tenant_admin_site)
class SchoolEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "school",
        "status",
        "start_at",
        "venue",
        "ticketing_enabled",
        "sponsorship_enabled",
    )
    list_filter = ("status", "ticketing_enabled", "sponsorship_enabled", "is_public")
    search_fields = ("title", "school__name", "summary", "description")
    inlines = [EventTicketTierInline, EventSponsorCommitmentInline]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(EventRegistration, site=tenant_admin_site)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "attendee_name",
        "quantity",
        "amount_due",
        "amount_paid",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("event__title", "attendee_name", "attendee_email")
