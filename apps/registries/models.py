from django.db import models


class CountryRegistry(models.Model):
    code = models.CharField(
        max_length=2,
        primary_key=True,
        help_text="Canonical ISO 3166-1 alpha-2 country code.",
    )
    alpha3_code = models.CharField(
        max_length=3,
        blank=True,
        db_index=True,
        help_text="Compatibility alpha-3 code used by older RegionConfig flows.",
    )
    name = models.CharField(max_length=120)
    default_language = models.CharField(max_length=16, default="en")
    default_currency = models.CharField(max_length=3, default="USD")
    default_timezone = models.CharField(max_length=64, default="UTC")
    labels = models.JSONField(
        default=dict,
        blank=True,
        help_text="Country-specific display labels and terminology overrides.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Registry-driven configuration such as academic/compliance defaults.",
    )
    default_calendar_family = models.CharField(
        max_length=48, blank=True, help_text="Default calendar system code."
    )
    default_terminology_pack = models.CharField(
        max_length=48, blank=True, help_text="Default terminology pack code."
    )
    writing_direction = models.CharField(
        max_length=8, default="ltr", blank=True, help_text="ltr or rtl."
    )
    cockpit_override_payload = models.JSONField(
        blank=True,
        default=dict,
        help_text=(
            "Operator-edited overlay applied on top of the in-memory country "
            "seed pack at the service hot path (Wave 8 v3.62.8). Shape "
            "mirrors the country pack: calendar_systems / school_types / "
            "education_levels / terminology / languages. Lists override "
            "wholesale; dicts merge one level deep. Empty dict = no override."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Country registry entry"
        verbose_name_plural = "Country registry"

    def __str__(self):
        return f"{self.name} ({self.code})"


class SubdivisionRegistry(models.Model):
    country = models.ForeignKey(
        CountryRegistry,
        on_delete=models.CASCADE,
        related_name="subdivisions",
    )
    code = models.CharField(
        max_length=32,
        help_text="Canonical subdivision code, preferably ISO 3166-2.",
    )
    name = models.CharField(max_length=160)
    subdivision_type = models.CharField(
        max_length=40,
        default="state",
        help_text="Subdivision type such as state, province, region, territory.",
    )
    labels = models.JSONField(
        default=dict,
        blank=True,
        help_text="Country or locale-specific display label overrides.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_id", "name"]
        unique_together = [("country", "code")]
        verbose_name = "Subdivision registry entry"
        verbose_name_plural = "Subdivision registry"

    def __str__(self):
        return f"{self.name} ({self.country_id}-{self.code})"


class EducationLevelRegistry(models.Model):
    code = models.CharField(max_length=32, primary_key=True)
    global_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    country_labels = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map of country code -> localized label.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "global_name"]
        verbose_name = "Education level registry entry"
        verbose_name_plural = "Education level registry"

    def __str__(self):
        return self.global_name


class EducationSystemTypeRegistry(models.Model):
    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    country_labels = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map of country code -> localized label.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Education system type registry entry"
        verbose_name_plural = "Education system type registry"

    def __str__(self):
        return self.name


# ---------- Section 20.6: Additional control-plane registries ----------


class TimeZoneRegistry(models.Model):
    """Section 20.1/20.6: Canonical timezone list for school/region selection."""

    code = models.CharField(
        max_length=64,
        primary_key=True,
        help_text="IANA timezone identifier (e.g. Africa/Douala).",
    )
    name = models.CharField(max_length=120)
    utc_offset = models.CharField(max_length=16, blank=True, help_text="e.g. +01:00")
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Time zone registry entry"
        verbose_name_plural = "Time zone registry"

    def __str__(self):
        return f"{self.name} ({self.code})"


class CurrencyRegistry(models.Model):
    """Section 20.1/20.6: Canonical currency list for billing and display."""

    code = models.CharField(
        max_length=3, primary_key=True, help_text="ISO 4217 alpha-3 (e.g. USD, XAF)."
    )
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=16, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    thousands_separator_style = models.CharField(
        max_length=16, blank=True, help_text="e.g. comma, space, none."
    )
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Currency registry entry"
        verbose_name_plural = "Currency registry"

    def __str__(self):
        return f"{self.name} ({self.code})"


class LocaleRegistry(models.Model):
    """Section 20.1/20.6: Locale for number/date formatting and RTL."""

    code = models.CharField(
        max_length=24, primary_key=True, help_text="e.g. en_US, fr_CM."
    )
    name = models.CharField(max_length=80)
    date_format = models.CharField(max_length=32, default="%Y-%m-%d", blank=True)
    time_format = models.CharField(max_length=32, default="%H:%M", blank=True)
    number_format = models.CharField(
        max_length=32, blank=True, help_text="Decimal/thousand separators."
    )
    first_day_of_week = models.PositiveSmallIntegerField(
        default=0, help_text="0=Monday, 6=Sunday."
    )
    is_rtl = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Locale registry entry"
        verbose_name_plural = "Locale registry"

    def __str__(self):
        return f"{self.name} ({self.code})"


class CalendarSystemRegistry(models.Model):
    """Section 20.1/20.6: Academic calendar presets (term count, start month, etc.)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    term_count_per_year = models.PositiveSmallIntegerField(default=3)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="e.g. default_start_month, holiday_strategy.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Calendar system registry entry"
        verbose_name_plural = "Calendar system registry"

    def __str__(self):
        return self.name


class InstitutionTypeRegistry(models.Model):
    """Section 20.2/20.4/20.6: Institution types (general, trade, technical, STEM, religious, international, etc.)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    country_labels = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Institution type registry entry"
        verbose_name_plural = "Institution type registry"

    def __str__(self):
        return self.name


class AcademicTerminologyRegistry(models.Model):
    """Section 20.2/20.6: Terminology packs (e.g. Principal vs Proviseur, Grade vs Class)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    terminology = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map of term key -> display string (e.g. student_id_label, principal_title).",
    )
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Academic terminology registry entry"
        verbose_name_plural = "Academic terminology registry"

    def __str__(self):
        return self.name


class DocumentTypeRegistry(models.Model):
    """Admission/compliance document categories (e.g. Birth Certificate, National ID, Passport)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=48, blank=True, help_text="e.g. identity, academic, health."
    )
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Document type registry entry"
        verbose_name_plural = "Document type registry"

    def __str__(self):
        return self.name


class FeeCategoryRegistry(models.Model):
    """Finance billing categories (e.g. Tuition, Application Fee, Transport, Lab Fee)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=48, blank=True)
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Fee category registry entry"
        verbose_name_plural = "Fee category registry"

    def __str__(self):
        return self.name


class GradeScaleRegistry(models.Model):
    """Grading families and scale templates (e.g. 0-20, 0-100, 4.0 GPA, letter grades)."""

    code = models.CharField(max_length=48, primary_key=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    family = models.CharField(
        max_length=48, blank=True, help_text="e.g. numeric, letter, gpa, competency."
    )
    range_definition = models.JSONField(
        default=dict,
        blank=True,
        help_text="Min/max, pass threshold, scale steps.",
    )
    country_code = models.CharField(max_length=2, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Grade scale registry entry"
        verbose_name_plural = "Grade scale registry"

    def __str__(self):
        return self.name


from .tenant_registry_models import TenantAttendanceCode, TenantFeeTypeEntry  # noqa: E402,F401
