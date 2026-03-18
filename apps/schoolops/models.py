from django.conf import settings
from django.db import models


_AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "accounts.User")


class Campus(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="campuses",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=32, blank=True, help_text="Short code e.g. MAIN, NORTH"
    )
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_campus"
        ordering = ["school", "name"]
        verbose_name = "Campus"
        verbose_name_plural = "Campuses"

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class InventoryItem(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="inventory_items",
    )
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_inventoryitem"
        ordering = ["name"]
        verbose_name = "Inventory item"
        verbose_name_plural = "Inventory items"

    def __str__(self):
        return f"{self.name} ({self.quantity})"


class Route(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="transport_routes"
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_route"
        ordering = ["name"]
        unique_together = [("school", "name")]

    def __str__(self):
        return self.name


class Stop(models.Model):
    route = models.ForeignKey(
        "schoolops.Route", on_delete=models.CASCADE, related_name="stops"
    )
    name = models.CharField(max_length=120)
    sequence = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_stop"
        ordering = ["route", "sequence"]
        unique_together = [("route", "sequence")]

    def __str__(self):
        return f"{self.route.name}: {self.name}"


class Bus(models.Model):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="buses"
    )
    identifier = models.CharField(max_length=60, help_text="e.g. Bus 01, Plate number")
    route = models.ForeignKey(
        "schoolops.Route",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buses",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_bus"
        ordering = ["identifier"]
        unique_together = [("school", "identifier")]

    def __str__(self):
        return self.identifier


class Hostel(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="hostels",
    )
    name = models.CharField(max_length=120)
    capacity = models.PositiveIntegerField(default=0, help_text="Total bed capacity")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_hostel"
        ordering = ["name"]
        unique_together = [("school", "name")]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class HostelRoom(models.Model):
    hostel = models.ForeignKey(
        "schoolops.Hostel", on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=60)
    capacity = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_hostelroom"
        ordering = ["hostel", "name"]
        unique_together = [("hostel", "name")]

    def __str__(self):
        return f"{self.hostel.name} / {self.name}"


class CanteenMeal(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="canteen_meals",
    )
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_canteenmeal"
        ordering = ["name"]
        unique_together = [("school", "name")]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class HealthRecord(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="health_records",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="health_records",
    )
    record_type = models.CharField(
        max_length=32,
        help_text="e.g. allergy, medication, vaccination, visit",
    )
    notes = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_health_records",
    )
    confidential = models.BooleanField(default=False)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_healthrecord"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.student} - {self.record_type}"


class BiometricDevice(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="biometric_devices",
    )
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=255, blank=True)
    device_id = models.CharField(max_length=64, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_biometricdevice"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.school.name})"


class BiometricAttendanceLog(models.Model):
    device = models.ForeignKey(
        "schoolops.BiometricDevice",
        on_delete=models.CASCADE,
        related_name="attendance_logs",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="biometric_logs",
    )
    user = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="biometric_logs",
    )
    timestamp = models.DateTimeField(db_index=True)
    raw_identifier = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_biometricattendancelog"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.device.name} @ {self.timestamp}"


class LibraryItem(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="library_items",
    )
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    isbn = models.CharField(max_length=32, blank=True, db_index=True)
    item_type = models.CharField(max_length=32, default="book")
    copies_total = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_libraryitem"
        ordering = ["title"]
        unique_together = [("school", "title", "author")]

    def __str__(self):
        author_suffix = f" - {self.author}" if self.author else ""
        return f"{self.title}{author_suffix} ({self.school.name})"


class LibraryLoan(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="library_loans",
    )
    item = models.ForeignKey(
        "schoolops.LibraryItem",
        on_delete=models.CASCADE,
        related_name="loans",
    )
    borrower = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_loans",
    )
    checked_out_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_libraryloan"
        ordering = ["-checked_out_at"]

    def __str__(self):
        return f"{self.item.title} -> {self.borrower} (due {self.due_at})"
