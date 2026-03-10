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
    HostelRoom,
    InventoryItem,
    LibraryItem,
    LibraryLoan,
    Route,
    Stop,
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


@admin.register(Route, site=tenant_admin_site)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "is_active")
    list_filter = ("school", "is_active")


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


@admin.register(HostelRoom, site=tenant_admin_site)
class HostelRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "hostel", "capacity")
    list_filter = ("hostel__school",)
    raw_id_fields = ("hostel",)


@admin.register(CanteenMeal, site=tenant_admin_site)
class CanteenMealAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "price", "is_active", "created_at")
    list_filter = ("school", "is_active")
    search_fields = ("name", "school__name")
    raw_id_fields = ("school",)


@admin.register(HealthRecord, site=tenant_admin_site)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "record_type", "school", "recorded_at", "confidential")
    list_filter = ("school", "record_type", "confidential")
    search_fields = ("student__first_name", "student__last_name", "notes")
    raw_id_fields = ("school", "student", "recorded_by")


@admin.register(BiometricDevice, site=tenant_admin_site)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "device_id", "location", "is_active", "created_at")
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
    list_display = ("title", "author", "school", "item_type", "copies_total", "is_active", "created_at")
    list_filter = ("school", "item_type", "is_active")
    search_fields = ("title", "author", "isbn", "school__name")
    raw_id_fields = ("school",)


@admin.register(LibraryLoan, site=tenant_admin_site)
class LibraryLoanAdmin(admin.ModelAdmin):
    list_display = ("item", "borrower", "school", "checked_out_at", "due_at", "returned_at")
    list_filter = ("school",)
    raw_id_fields = ("school", "item", "borrower")
    date_hierarchy = "checked_out_at"
