from decimal import Decimal

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
    reorder_threshold = models.PositiveIntegerField(
        default=0,
        help_text="Low-stock reorder level; an alert fires when quantity "
        "falls to or below this. 0 disables the alert for this item.",
    )
    last_low_stock_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when a low-stock alert was sent for the current "
        "low-stock episode; cleared when stock is replenished above the "
        "reorder level. Guarantees the alert fires once per episode.",
    )
    low_stock_notification_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_inventoryitem"
        ordering = ["name"]
        verbose_name = "Inventory item"
        verbose_name_plural = "Inventory items"

    def __str__(self):
        return f"{self.name} ({self.quantity})"

    @property
    def is_low(self) -> bool:
        """True when a positive reorder level is set and stock is at/below it."""
        threshold = self.reorder_threshold or 0
        return threshold > 0 and (self.quantity or 0) <= threshold


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
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="WGS84 latitude; enables offline route optimisation.",
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="WGS84 longitude; enables offline route optimisation.",
    )
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


class BusBoardingEvent(models.Model):
    """Non-phone fleet monitor: a passive RFID/NFC/QR tap as a student boards or
    alights a bus (Wave D — logistics). Append-only event log; idempotent per tap
    so a re-read or offline replay never double-records. A best-effort parent
    notification fires on create.
    """

    class Direction(models.TextChoices):
        BOARD = "board", "Boarded"
        ALIGHT = "alight", "Alighted"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="bus_boarding_events"
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="bus_boarding_events",
    )
    route = models.ForeignKey(
        "schoolops.Route",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="boarding_events",
    )
    bus = models.ForeignKey(
        "schoolops.Bus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="boarding_events",
    )
    direction = models.CharField(
        max_length=8, choices=Direction.choices, default=Direction.BOARD
    )
    capture_method = models.CharField(
        max_length=16, default="rfid", help_text="rfid / nfc / qr / manual"
    )
    device_id = models.CharField(max_length=64, blank=True)
    occurred_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=128, blank=True, db_index=True)
    parent_notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_busboardingevent"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["school", "occurred_at"]),
        ]

    def __str__(self):
        return f"{self.student_id} {self.direction} @ {self.occurred_at}"


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


class SubstituteCover(models.Model):
    """
    Wave 15: tenant substitute / cover assignment (ops module).
    Records who is absent and optional covering teacher for a given date.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="substitute_covers",
    )
    work_date = models.DateField(db_index=True)
    absent_teacher = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="substitute_cover_absences",
    )
    covering_teacher = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_cover_assignments",
    )
    period_label = models.CharField(
        max_length=80,
        blank=True,
        help_text="e.g. Period 3, Full day",
    )
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_substitutecover"
        ordering = ["-work_date", "-created_at"]
        indexes = [
            models.Index(fields=["school", "work_date"]),
        ]

    def __str__(self):
        return f"{self.work_date} absent={self.absent_teacher_id}"


class SubstituteMarketShift(models.Model):
    """Durable record of an opened substitute shift in the market.

    DB is source of truth; the cache layer is an optional speed fence.
    The UUID pk doubles as ``shift_id`` in WS payloads.
    """

    import uuid as _uuid_mod

    STATUS_OPEN = "open"
    STATUS_CLAIMED = "claimed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid_mod.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="substitute_market_shifts",
    )
    absent_teacher = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="substitute_market_absences",
    )
    work_date = models.DateField()
    period_label = models.CharField(max_length=80, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True
    )
    claimed_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_market_claims",
    )
    cover = models.ForeignKey(
        "schoolops.SubstituteCover",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_shift",
    )
    notify_attempted = models.PositiveIntegerField(default=0)
    notify_accepted = models.PositiveIntegerField(default=0)
    notify_used_override = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_substitutemarketshift"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status", "work_date"]),
        ]

    def __str__(self):
        return f"{self.work_date} shift={self.pk} status={self.status}"


class VisitorCheckIn(models.Model):
    """
    Wave 16: front-desk visitor log (ops module).
    Check-in / check-out lines per school for reception workflows.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="visitor_checkins",
    )
    visitor_name = models.CharField(max_length=255)
    host_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Person or office being visited",
    )
    purpose = models.CharField(max_length=255, blank=True)
    badge_number = models.CharField(max_length=64, blank=True)
    checked_in_at = models.DateTimeField(auto_now_add=True, db_index=True)
    checked_out_at = models.DateTimeField(null=True, blank=True, db_index=True)
    recorded_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitor_checkins_recorded",
    )
    # Idempotency anchor for offline check-ins replayed via the OfflineAction
    # field_capture rail — a replay (or two devices) can't double-log a visitor.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_visitorcheckin"
        ordering = ["-checked_in_at"]
        indexes = [
            models.Index(fields=["school", "checked_out_at"]),
        ]
        constraints = [
            # DB-enforced offline idempotency: a replay / two devices cannot
            # double-log the same check-in. Partial so blank (online) rows are
            # exempt. The offline writer catches the IntegrityError and returns
            # the existing row as a dedup hit.
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_visitorcheckin_school_offline_id",
            ),
        ]

    def __str__(self):
        return f"{self.visitor_name} @ {self.checked_in_at}"

    @property
    def is_on_site(self) -> bool:
        return self.checked_out_at is None


class MaintenanceRequest(models.Model):
    """
    Wave 17: facilities / maintenance ticket (ops module).
    Lightweight work-request log until full CMMS depth.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        CLOSED = "closed", "Closed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="maintenance_requests",
    )
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    reported_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests_reported",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_maintenancerequest"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class PosSaleLine(models.Model):
    """
    Wave 18: lightweight POS / till line (ops stub).
    Not a full retail module — quick sale log for canteen or events.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        MOBILE = "mobile", "Mobile money"
        ACCOUNT = "account", "On account"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="pos_sale_lines",
    )
    item_label = models.CharField(max_length=255)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Sales tax / VAT rate snapshot for this line (0–100).",
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Tax amount charged on this line at sale time.",
    )
    notes = models.CharField(max_length=255, blank=True)
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="pos_sale_lines",
        help_text="Student charged (cashless campus POS); null for anonymous cash sales.",
    )
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="Client-supplied key; a repeated key returns the prior sale (no double-charge).",
    )
    inventory_item = models.ForeignKey(
        "schoolops.InventoryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_sale_lines",
        help_text="Optional link to stock line when Inventory module is enabled.",
    )
    recorded_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_sale_lines_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_possaleline"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item_label} x{self.quantity}"

    @property
    def line_total(self):
        return (self.unit_price or Decimal("0")) * Decimal(self.quantity or 0)

    @property
    def grand_total(self):
        """Line net (pre-tax) + stored tax snapshot."""
        return self.line_total + (self.tax_amount or Decimal("0"))


# ---------------------------------------------------------------------------
# v3.29.0 — First-class per-student assignment models. These promote the
# three v3.28 landers (transport / hostel / cafeteria) off the
# ``apps.metadata.DynamicFieldValue`` fallback they used while no
# schoolops-side join row existed. The landers now write to these models
# when both ends of the join resolve and gracefully fall back to
# DynamicFieldValue when the catalog side hasn't landed yet (out-of-order
# bundle). The v3.29.0 migration is pure ``CreateModel`` — no live-model
# imports — and the registry docstring update is in
# ``apps/migration_cloud/landers/__init__.py``.
# ---------------------------------------------------------------------------


_TRANSPORT_ASSIGNMENT_STATUS_CHOICES = (
    ("active", "Active"),
    ("paused", "Paused"),
    ("ended", "Ended"),
)

_HOSTEL_ASSIGNMENT_STATUS_CHOICES = (
    ("active", "Active"),
    ("checked_out", "Checked Out"),
    ("ended", "Ended"),
)

_MEAL_PLAN_BALANCE_STATUS_CHOICES = (
    ("active", "Active"),
    ("suspended", "Suspended"),
    ("closed", "Closed"),
)


class TransportAssignment(models.Model):
    """A student's join to a transport Route (with stops + effective window).

    v3.29.0 promotion: replaces the ``DynamicFieldValue`` fallback that the
    ``transport_assignment_lander`` used in v3.28. Catalog row lives in
    :class:`Route`; this row says "this student rides that route".
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="transport_assignments",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="transport_assignments",
    )
    route = models.ForeignKey(
        "schoolops.Route",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    pickup_stop = models.CharField(max_length=128, blank=True)
    dropoff_stop = models.CharField(max_length=128, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=_TRANSPORT_ASSIGNMENT_STATUS_CHOICES,
        default="active",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_transportassignment"
        ordering = ["-effective_from", "-created_at"]
        unique_together = [("student", "route", "effective_from")]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["route", "effective_from"]),
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        return f"{self.student_id} -> {self.route_id} ({self.status})"


class HostelAssignment(models.Model):
    """A student's join to a HostelRoom (with bed label + effective window).

    v3.29.0 promotion: replaces the ``DynamicFieldValue`` fallback that the
    ``hostel_assignment_lander`` used in v3.28. Catalog rows live in
    :class:`Hostel` + :class:`HostelRoom`.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="hostel_assignments",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="hostel_assignments",
    )
    room = models.ForeignKey(
        "schoolops.HostelRoom",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    bed_label = models.CharField(
        max_length=32,
        blank=True,
        help_text='e.g. "Bed 1", "Top Bunk"',
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=_HOSTEL_ASSIGNMENT_STATUS_CHOICES,
        default="active",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_hostelassignment"
        ordering = ["-effective_from", "-created_at"]
        unique_together = [("student", "room", "effective_from")]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["room", "status"]),
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        return f"{self.student_id} -> {self.room_id} ({self.status})"


class MealPlanBalance(models.Model):
    """A student's running cafeteria balance for a meal plan (or generic credit).

    v3.29.0 promotion: replaces the ``DynamicFieldValue`` fallback that the
    ``cafeteria_assignment_lander`` used in v3.28. ``meal_plan`` is nullable
    — a null value represents a generic / uncategorized canteen credit. All
    money fields are :class:`Decimal` to satisfy ``scan_money_float``.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="meal_plan_balances",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="meal_plan_balances",
    )
    meal_plan = models.ForeignKey(
        "schoolops.CanteenMeal",
        on_delete=models.PROTECT,
        related_name="balances",
        null=True,
        blank=True,
        help_text="Null = generic / uncategorized canteen credit.",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO 4217 currency code.",
    )
    last_topup_at = models.DateTimeField(null=True, blank=True)
    last_topup_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    low_balance_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("5.00"),
    )
    status = models.CharField(
        max_length=16,
        choices=_MEAL_PLAN_BALANCE_STATUS_CHOICES,
        default="active",
    )
    # v3.32.0 — low-balance notification tracking (Agent 4 wave). The signal
    # at :mod:`apps.schoolops.signals` reads these to enforce a 7-day
    # cooldown between repeat notifications; the Celery sweep at
    # :func:`apps.schoolops.tasks.sweep_low_meal_plan_balances` uses them
    # to find rows the signal missed (e.g. low at app-startup time).
    last_low_balance_notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent low-balance notification "
                  "delivery; used by the cooldown gate.",
    )
    low_balance_notification_count = models.PositiveIntegerField(
        default=0,
        help_text="Lifetime count of low-balance notifications dispatched "
                  "for this row (analytics + spam-detection).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schools_mealplanbalance"
        ordering = ["-updated_at"]
        unique_together = [("student", "meal_plan")]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self):
        plan_token = self.meal_plan_id if self.meal_plan_id else "generic"
        return f"{self.student_id} / {plan_token}: {self.balance} {self.currency}"

    @property
    def is_low(self) -> bool:
        """True when balance has dropped to or below the configured threshold."""
        bal = self.balance if self.balance is not None else Decimal("0")
        thr = (
            self.low_balance_threshold
            if self.low_balance_threshold is not None
            else Decimal("0")
        )
        return bal <= thr


# v3.57.x Wave 8 Agent C — re-export append-only email delivery event log
# so external callers can write ``from apps.schoolops.models import
# EmailDeliveryEvent`` without knowing the sub-module layout. The model
# itself lives in :mod:`apps.schoolops.models_email_delivery`.
from apps.schoolops.models_email_delivery import (  # noqa: E402  re-export at module tail
    EmailDeliveryEvent,
    EmailDeliveryEventReadOnlyError,
)
from apps.schoolops.models_email_suppression import (  # noqa: E402
    SuppressedRecipient,
    SuppressionReason,
)
from apps.schoolops.models_email_deadletter import (  # noqa: E402
    DeadLetterStatus,
    EmailDeadLetter,
)
from apps.schoolops.models_micro_friction import (  # noqa: E402
    LostBelongingsCustodyEventRecord,
    LostBelongingsTagRecord,
    SubstituteHandoverPacketRecord,
)
from apps.schoolops.models_resource_booking import (  # noqa: E402
    BookableResource,
    ResourceBooking,
)
from apps.schoolops.models_inventory_movement import InventoryMovement  # noqa: E402

__all__ = [
    "EmailDeliveryEvent",
    "EmailDeliveryEventReadOnlyError",
    "SuppressedRecipient",
    "SuppressionReason",
    "DeadLetterStatus",
    "EmailDeadLetter",
    "LostBelongingsCustodyEventRecord",
    "LostBelongingsTagRecord",
    "SubstituteHandoverPacketRecord",
    "BookableResource",
    "ResourceBooking",
    "InventoryMovement",
]
