from django.contrib import admin, messages

from config.admin import tenant_admin_site
from apps.school_events.models import (
    EventRegistration,
    EventSponsor,
    EventSponsorCommitment,
    EventTicketTier,
    EventVenue,
    SchoolEvent,
)
from apps.school_events.services import (
    RegistrationStateError,
    confirm_registration_payment,
    release_reservation,
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
    actions = ("confirm_cash_payment", "release_unpaid_hold")

    @admin.action(description="Confirm cash/manual payment (RESERVED → CONFIRMED)")
    def confirm_cash_payment(self, request, queryset):
        ok = skip = 0
        for registration in queryset:
            try:
                confirm_registration_payment(registration=registration, method="cash")
                ok += 1
            except RegistrationStateError:
                skip += 1
        self.message_user(
            request,
            f"Confirmed {ok} registration(s); skipped {skip}.",
            messages.SUCCESS if ok else messages.WARNING,
        )

    @admin.action(description="Release unpaid RESERVED hold (restore capacity)")
    def release_unpaid_hold(self, request, queryset):
        ok = skip = 0
        for registration in queryset:
            try:
                release_reservation(registration=registration)
                ok += 1
            except RegistrationStateError:
                skip += 1
        self.message_user(
            request,
            f"Released {ok} hold(s); skipped {skip}.",
            messages.SUCCESS if ok else messages.WARNING,
        )