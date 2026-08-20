from django.contrib import admin

from config.admin import tenant_admin_site

from .models import (
    Bus,
    BiometricAttendanceLog,
    BiometricDevice,
    CanteenMeal,
    Campus,
    HealthRecord,
    Hostel,
    HostelAssignment,
    HostelRoom,
    ImmunizationRecord,
    InventoryItem,
    LibraryItem,
    LibraryLoan,
    LostBelongingsCustodyEventRecord,
    LostBelongingsTagRecord,
    MealPlanBalance,
    PurchaseOrder,
    PurchaseOrderLine,
    Route,
    Stop,
    SubstituteHandoverPacketRecord,
    SupplyRequirement,
    TransportAssignment,
    VaccineRequirement,
    Vendor,
    VendorProduct,
)


@admin.register(Campus, site=tenant_admin_site)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "school", "is_active", "created_at")
    list_filter = ("is_active", "school")
    search_fields = ("name", "code", "school__name")
    raw_id_fields = ("school",)


@admin.register(InventoryItem, site=tenant_admin_site)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "quantity", "location")
    list_filter = ("school",)
    search_fields = ("name", "location")


class TransportAssignmentInline(admin.TabularInline):
    model = TransportAssignment
    extra = 0
    fields = (
        "student", "pickup_stop", "dropoff_stop",
        "effective_from", "effective_to", "status",
    )
    raw_id_fields = ("student",)
    show_change_link = True


@admin.register(Route, site=tenant_admin_site)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_active")
    list_filter = ("school", "is_active")
    inlines = [TransportAssignmentInline]


@admin.register(Stop, site=tenant_admin_site)
class StopAdmin(admin.ModelAdmin):
    list_display = ("name", "route", "sequence")
    list_filter = ("route__school",)


@admin.register(Bus, site=tenant_admin_site)
class BusAdmin(admin.ModelAdmin):
    list_display = ("identifier", "school", "route", "is_active")
    list_filter = ("school", "is_active")


@admin.register(Hostel, site=tenant_admin_site)
class HostelAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "capacity", "is_active", "created_at")
    list_filter = ("school", "is_active")
    search_fields = ("name", "school__name")
    raw_id_fields = ("school",)


class HostelAssignmentInline(admin.TabularInline):
    model = HostelAssignment
    extra = 0
    fields = (
        "student", "bed_label",
        "effective_from", "effective_to", "status",
    )
    raw_id_fields = ("student",)
    show_change_link = True


@admin.register(HostelRoom, site=tenant_admin_site)
class HostelRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "hostel", "capacity")
    list_filter = ("hostel__school",)
    raw_id_fields = ("hostel",)
    inlines = [HostelAssignmentInline]


class MealPlanBalanceInline(admin.TabularInline):
    model = MealPlanBalance
    extra = 0
    fields = (
        "student", "balance", "currency",
        "low_balance_threshold", "status",
    )
    raw_id_fields = ("student",)
    show_change_link = True


@admin.register(CanteenMeal, site=tenant_admin_site)
class CanteenMealAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "price", "is_active", "created_at")
    list_filter = ("school", "is_active")
    search_fields = ("name", "school__name")
    raw_id_fields = ("school",)
    inlines = [MealPlanBalanceInline]


@admin.register(HealthRecord, site=tenant_admin_site)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "record_type", "school", "recorded_at", "confidential")
    list_filter = ("school", "record_type", "confidential")
    search_fields = ("student__first_name", "student__last_name", "notes")
    raw_id_fields = ("school", "student", "recorded_by")


@admin.register(VaccineRequirement, site=tenant_admin_site)
class VaccineRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "vaccine",
        "school",
        "doses_required",
        "min_age_years",
        "max_age_years",
        "is_active",
        "updated_at",
    )
    list_filter = ("school", "is_active")
    search_fields = ("vaccine", "school__name", "notes")
    raw_id_fields = ("school",)


@admin.register(ImmunizationRecord, site=tenant_admin_site)
class ImmunizationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "vaccine",
        "dose_number",
        "school",
        "date_administered",
        "exemption_type",
        "created_at",
    )
    list_filter = ("school", "vaccine", "exemption_type")
    search_fields = (
        "student__first_name",
        "student__last_name",
        "student__student_code",
        "vaccine",
        "notes",
    )
    raw_id_fields = ("school", "student", "verified_by")
    date_hierarchy = "date_administered"


@admin.register(BiometricDevice, site=tenant_admin_site)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "school",
        "device_id",
        "location",
        "is_active",
        "created_at",
    )
    list_filter = ("school", "is_active")
    search_fields = ("name", "device_id", "school__name")
    raw_id_fields = ("school",)


@admin.register(BiometricAttendanceLog, site=tenant_admin_site)
class BiometricAttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("device", "student", "user", "timestamp")
    list_filter = ("device__school",)
    raw_id_fields = ("device", "student", "user")


@admin.register(LibraryItem, site=tenant_admin_site)
class LibraryItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "author",
        "school",
        "item_type",
        "copies_total",
        "is_active",
        "created_at",
    )
    list_filter = ("school", "item_type", "is_active")
    search_fields = ("title", "author", "isbn", "school__name")
    raw_id_fields = ("school",)


@admin.register(LibraryLoan, site=tenant_admin_site)
class LibraryLoanAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "borrower",
        "school",
        "checked_out_at",
        "due_at",
        "returned_at",
    )
    list_filter = ("school",)
    raw_id_fields = ("school", "item", "borrower")
    date_hierarchy = "checked_out_at"


# ---------------------------------------------------------------------------
# v3.32.0 — First-class per-student assignment admin (Agent 4 wave).
# Registers list / filter / search pages for the three v3.31 promoted
# join models. Reverse-relation inlines are wired on the parent admins
# (Route / HostelRoom / CanteenMeal) above.
# ---------------------------------------------------------------------------


@admin.register(TransportAssignment, site=tenant_admin_site)
class TransportAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "route", "pickup_stop", "dropoff_stop",
        "effective_from", "effective_to", "status", "school",
    )
    list_filter = ("status", "school", "route")
    search_fields = (
        "student__first_name", "student__last_name",
        "student__admission_number", "student__student_code",
        "route__name", "pickup_stop", "dropoff_stop",
    )
    raw_id_fields = ("student", "route", "school")
    date_hierarchy = "effective_from"


@admin.register(HostelAssignment, site=tenant_admin_site)
class HostelAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "room", "bed_label",
        "effective_from", "effective_to", "status", "school",
    )
    list_filter = ("status", "school", "room__hostel")
    search_fields = (
        "student__first_name", "student__last_name",
        "student__admission_number", "student__student_code",
        "room__name", "bed_label",
    )
    raw_id_fields = ("student", "room", "school")
    date_hierarchy = "effective_from"


@admin.register(MealPlanBalance, site=tenant_admin_site)
class MealPlanBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "meal_plan", "balance", "currency",
        "is_low_display", "low_balance_threshold",
        "last_topup_at", "low_balance_notification_count",
        "last_low_balance_notification_sent_at", "status",
    )
    list_filter = ("status", "school", "meal_plan", "currency")
    search_fields = (
        "student__first_name", "student__last_name",
        "student__admission_number", "student__student_code",
        "meal_plan__name",
    )
    raw_id_fields = ("student", "meal_plan", "school")
    readonly_fields = (
        "last_topup_at", "last_topup_amount",
        "last_low_balance_notification_sent_at",
        "low_balance_notification_count",
    )

    def is_low_display(self, obj):
        return obj.is_low
    is_low_display.boolean = True
    is_low_display.short_description = "Low?"


@admin.register(SubstituteHandoverPacketRecord, site=tenant_admin_site)
class SubstituteHandoverPacketRecordAdmin(admin.ModelAdmin):
    list_display = (
        "packet_id",
        "school",
        "valid_until",
        "medical_iep_gated",
        "source",
        "created_at",
    )
    list_filter = ("source", "medical_iep_gated", "school")
    search_fields = ("packet_id", "teacher_id_hash", "substitute_id_hash")
    readonly_fields = (
        "packet_id",
        "teacher_id_hash",
        "substitute_id_hash",
        "audit_event_id",
        "created_at",
    )
    raw_id_fields = ("school", "created_by")


@admin.register(LostBelongingsTagRecord, site=tenant_admin_site)
class LostBelongingsTagRecordAdmin(admin.ModelAdmin):
    list_display = ("short_code", "label_hint", "school", "status", "created_at")
    list_filter = ("status", "school")
    search_fields = ("short_code", "label_hint", "asset_id")
    readonly_fields = ("tenant_id_hash", "created_at", "recovered_at")
    raw_id_fields = ("school", "created_by")


@admin.register(LostBelongingsCustodyEventRecord, site=tenant_admin_site)
class LostBelongingsCustodyEventRecordAdmin(admin.ModelAdmin):
    list_display = ("event_id", "tag", "actor_kind", "school", "occurred_at")
    list_filter = ("actor_kind", "school")
    search_fields = ("event_id", "notes_redacted")
    readonly_fields = ("event_id", "staff_id_hash", "occurred_at", "created_at")
    raw_id_fields = ("school", "tag")


# --- M33 procurement -------------------------------------------------------
# Without these, a school has no way to create a Vendor, a VendorProduct or a
# SupplyRequirement, so the "generate orders from class configuration" button
# would compute forever over an empty table. Registration is what makes the
# derived-order engine reachable by an actual operator.


@admin.register(Vendor, site=tenant_admin_site)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_certified", "currency", "is_active")
    list_filter = ("is_certified", "is_active", "school")
    search_fields = ("name", "contact_email")
    raw_id_fields = ("school",)


@admin.register(VendorProduct, site=tenant_admin_site)
class VendorProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "vendor", "unit_price", "unit", "is_active")
    list_filter = ("is_active", "school", "vendor")
    search_fields = ("name", "sku")
    raw_id_fields = ("school", "vendor")


@admin.register(SupplyRequirement, site=tenant_admin_site)
class SupplyRequirementAdmin(admin.ModelAdmin):
    """The class configuration that drives every generated order."""

    list_display = ("subject", "product", "quantity_per_student", "school", "is_active")
    list_filter = ("is_active", "school")
    search_fields = ("subject__name", "product__name", "product__sku")
    raw_id_fields = ("school", "subject", "product")


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    raw_id_fields = ("school", "product", "subject_assignment")
    # Totals are computed by procurement_services; editing them by hand would
    # silently desynchronise the order from its own lines.
    readonly_fields = ("line_total",)


@admin.register(PurchaseOrder, site=tenant_admin_site)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "school", "status", "source", "total", "currency", "created_at")
    list_filter = ("status", "source", "school")
    search_fields = ("vendor__name",)
    raw_id_fields = ("school", "vendor")
    readonly_fields = ("subtotal", "tax_amount", "total", "created_at", "updated_at")
    inlines = [PurchaseOrderLineInline]
