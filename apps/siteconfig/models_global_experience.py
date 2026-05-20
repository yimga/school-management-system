from __future__ import annotations

from decimal import Decimal
import uuid

from django.apps import apps as django_apps
from django.conf import settings
from django.db import models

from apps.siteconfig.global_catalog import GlobalGeoCatalog


class DesignTemplate(models.Model):
    """
    Design Studio: JSON layout blueprint for report cards, certificates, etc.
    One document type first (e.g. certificate or report_card); hydrate with data and render to PDF.
    """

    class DocumentType(models.TextChoices):
        REPORT_CARD = "report_card", "Report card"
        CERTIFICATE = "certificate", "Certificate"
        INVOICE = "invoice", "Invoice"
        ID_CARD = "id_card", "ID card"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="design_templates",
    )
    name = models.CharField(max_length=120, help_text="Template name")
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.CERTIFICATE,
    )
    layout = models.JSONField(
        default=dict,
        blank=True,
        help_text="Layout blueprint: widgets, positions, placeholders e.g. {{student_name}}",
    )
    is_default = models.BooleanField(
        default=False, help_text="Use as default for this document type"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["school", "document_type", "name"]
        unique_together = [("school", "document_type", "name")]
        verbose_name = "Design template"
        verbose_name_plural = "Design templates"

    def __str__(self):
        return f"{self.school.name}: {self.get_document_type_display()} - {self.name}"


class BrandProfile(models.Model):
    """
    Canonical tenant brand hub. All runtime tenant branding should resolve through this model.
    Legacy BrandSettings and School branding fields remain migration inputs and compatibility fallbacks.
    """

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="brand_profile",
    )
    logo_url = models.URLField(blank=True, help_text="Primary tenant logo URL.")
    logo_dark_url = models.URLField(
        blank=True, help_text="Optional dark-surface logo URL."
    )
    favicon_url = models.URLField(blank=True, help_text="Optional tenant favicon URL.")
    tagline = models.CharField(max_length=255, blank=True)
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    secondary_color = models.CharField(max_length=20, blank=True, default="")
    accent_color = models.CharField(max_length=20, default="#198754")
    font_family = models.CharField(max_length=160, blank=True)
    login_background_url = models.URLField(blank=True)
    portal_visual = models.CharField(max_length=120, blank=True)
    email_template = models.CharField(max_length=120, blank=True)
    pdf_template = models.CharField(max_length=120, blank=True)
    certificate_template = models.CharField(max_length=120, blank=True)
    tokens = models.JSONField(
        default=dict,
        blank=True,
        help_text="Theme tokens used across login, portal, reports, and emails.",
    )
    templates = models.JSONField(
        default=dict,
        blank=True,
        help_text="Template and layout bindings for branded surfaces.",
    )
    assets = models.JSONField(
        default=dict,
        blank=True,
        help_text="Versioned asset references and brand media metadata.",
    )
    custom_css = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand profile"
        verbose_name_plural = "Brand profiles"

    def __str__(self):
        return f"Brand profile: {self.school.name}"


class BrandSettings(models.Model):
    """
    Explicit branding per tenant (logo, colors, custom_css).
    When present, use instead of School.logo_url, primary_color, accent_color for white-label.
    """

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="brand_settings",
    )
    logo_url = models.URLField(blank=True, help_text="URL to tenant logo")
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    custom_css = models.TextField(
        blank=True, help_text="Optional custom CSS for tenant"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand settings"
        verbose_name_plural = "Brand settings"

    def __str__(self):
        return f"Brand: {self.school.name}"


class GradingScaleConfig(models.Model):
    """Define grading scales per region."""

    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.CASCADE,
        related_name="grading_scales",
        related_query_name="gradingscaleconfig",
        help_text="Region this scale applies to",
    )
    scale_type = models.CharField(
        max_length=20,
        help_text="Scale identifier (0-20, 0-100, 0-10, a-f, gpa)",
    )
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    display_format = models.CharField(
        max_length=50,
        help_text="Format string for display (e.g., '{score:.0f}/20', '{score:.1f}%')",
    )
    grade_a_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_b_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_c_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_d_min = models.DecimalField(max_digits=5, decimal_places=2)
    grade_f_min = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("region", "scale_type")
        ordering = ["region", "scale_type"]

    def __str__(self):
        return f"{self.region.name} - {self.scale_type}"

    def get_letter_grade(self, score):
        score = Decimal(str(score))
        if score >= self.grade_a_min:
            return "A"
        if score >= self.grade_b_min:
            return "B"
        if score >= self.grade_c_min:
            return "C"
        if score >= self.grade_d_min:
            return "D"
        return "F"


class WeatherLocation(models.Model):
    """
    Configurable weather locations for the header/context strip.
    Lets operators choose country -> city without hardcoding coordinates in templates.
    """

    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.CASCADE,
        related_name="weather_locations",
    )
    city = models.CharField(max_length=120)
    label = models.CharField(max_length=180, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    timezone = models.CharField(max_length=64, default="UTC")
    catalog_source_id = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Stable geonames (or catalog) identifier for API lookups.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region__name", "sort_order", "city"]

    def __str__(self):
        return self.display_label

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        return f"{self.city}, {self.region.name}"

    def to_weather_flags(self) -> dict:
        return {
            "header_weather_country_code": self.region_id,
            "header_weather_city": self.city,
            "header_weather_label": self.display_label,
            "header_weather_latitude": self.latitude,
            "header_weather_longitude": self.longitude,
            "header_weather_timezone": self.timezone or self.region.timezone or "UTC",
        }

    @classmethod
    def _seed_rows(cls) -> list[dict]:
        return [
            {
                "country_code": "GLOBAL",
                "country_name": "Global Default",
                "city": "UTC",
                "label": "Global Default (UTC)",
                "latitude": 0.0,
                "longitude": 0.0,
                "timezone": "UTC",
                "sort_order": 0,
            },
            {
                "country_code": "CMR",
                "country_name": "Cameroon",
                "city": "Buea",
                "label": "Buea, Cameroon",
                "latitude": 4.1527,
                "longitude": 9.2410,
                "timezone": "Africa/Douala",
                "sort_order": 10,
            },
            {
                "country_code": "CMR",
                "country_name": "Cameroon",
                "city": "Douala",
                "label": "Douala, Cameroon",
                "latitude": 4.0511,
                "longitude": 9.7679,
                "timezone": "Africa/Douala",
                "sort_order": 20,
            },
            {
                "country_code": "USA",
                "country_name": "United States",
                "city": "New York",
                "label": "New York, United States",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timezone": "America/New_York",
                "sort_order": 10,
            },
            {
                "country_code": "USA",
                "country_name": "United States",
                "city": "Los Angeles",
                "label": "Los Angeles, United States",
                "latitude": 34.0522,
                "longitude": -118.2437,
                "timezone": "America/Los_Angeles",
                "sort_order": 20,
            },
            {
                "country_code": "GBR",
                "country_name": "United Kingdom",
                "city": "London",
                "label": "London, United Kingdom",
                "latitude": 51.5072,
                "longitude": -0.1276,
                "timezone": "Europe/London",
                "sort_order": 10,
            },
            {
                "country_code": "NGA",
                "country_name": "Nigeria",
                "city": "Lagos",
                "label": "Lagos, Nigeria",
                "latitude": 6.5244,
                "longitude": 3.3792,
                "timezone": "Africa/Lagos",
                "sort_order": 10,
            },
            {
                "country_code": "KEN",
                "country_name": "Kenya",
                "city": "Nairobi",
                "label": "Nairobi, Kenya",
                "latitude": -1.2864,
                "longitude": 36.8172,
                "timezone": "Africa/Nairobi",
                "sort_order": 10,
            },
            {
                "country_code": "FRA",
                "country_name": "France",
                "city": "Paris",
                "label": "Paris, France",
                "latitude": 48.8566,
                "longitude": 2.3522,
                "timezone": "Europe/Paris",
                "sort_order": 10,
            },
        ]

    @classmethod
    def sync_from_global_catalog(cls, *, batch_size: int = 2000) -> dict[str, int]:
        """
        Persist the full geonames city catalog (and all ISO countries) into RegionConfig
        + WeatherLocation so header-weather works even when in-process geonamescache
        is unavailable on a given worker.
        """
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        if not GlobalGeoCatalog.has_live_catalog():
            return {"countries": 0, "cities_created": 0, "cities_updated": 0, "skipped": True}

        region_model = django_apps.get_model("siteconfig", "RegionConfig")
        countries_created = 0
        for country in GlobalGeoCatalog.list_countries():
            code = country["code"]
            defaults = GlobalGeoCatalog.country_defaults(code)
            _, created = region_model.objects.get_or_create(
                code=code,
                defaults={
                    "name": defaults["country_name"] or code,
                    "default_language": defaults["default_language"] or "en",
                    "timezone": defaults["timezone"] or "UTC",
                    "date_format": "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": defaults["currency"] or "USD",
                    "academic_year_start_month": 9,
                    "term_count_per_year": 3,
                },
            )
            if created:
                countries_created += 1

        country_index, _, _ = GlobalGeoCatalog._build_city_indexes()
        for code in country_index.keys():
            defaults = GlobalGeoCatalog.country_defaults(code)
            _, was_created = region_model.objects.get_or_create(
                code=code,
                defaults={
                    "name": defaults["country_name"] or code,
                    "default_language": defaults["default_language"] or "en",
                    "timezone": defaults["timezone"] or "UTC",
                    "date_format": "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": defaults["currency"] or "USD",
                    "academic_year_start_month": 9,
                    "term_count_per_year": 3,
                },
            )
            if was_created:
                countries_created += 1
        created = 0
        updated = 0
        pending_create: list[WeatherLocation] = []
        existing_by_source = {
            row.catalog_source_id: row
            for row in cls.objects.filter(catalog_source_id__isnull=False).only(
                "pk",
                "catalog_source_id",
                "latitude",
                "longitude",
                "timezone",
                "label",
                "is_active",
            )
        }

        def flush_create() -> None:
            nonlocal created
            if not pending_create:
                return
            cls.objects.bulk_create(
                pending_create, batch_size=batch_size, ignore_conflicts=True
            )
            created += len(pending_create)
            pending_create.clear()

        for _code, rows in country_index.items():
            for row in rows:
                source_id = str(row.get("id") or "").strip()
                if not source_id:
                    continue
                region_id = str(row.get("country_code") or "").upper()
                if not region_id:
                    continue
                city_name = str(row.get("city") or "").strip()
                if not city_name:
                    continue
                payload = {
                    "label": str(row.get("label") or city_name),
                    "latitude": float(row.get("latitude") or 0.0),
                    "longitude": float(row.get("longitude") or 0.0),
                    "timezone": str(row.get("timezone") or "UTC"),
                    "is_active": True,
                }
                existing = existing_by_source.get(source_id)
                if existing is None:
                    pending_create.append(
                        cls(
                            region_id=region_id,
                            city=city_name,
                            catalog_source_id=source_id,
                            sort_order=0,
                            **payload,
                        )
                    )
                    if len(pending_create) >= batch_size:
                        flush_create()
                    continue
                changed_fields = []
                for field, value in payload.items():
                    if getattr(existing, field) != value:
                        changed_fields.append(field)
                if changed_fields:
                    cls.objects.filter(pk=existing.pk).update(**payload)
                    updated += 1
        flush_create()
        GlobalGeoCatalog.clear_caches()
        return {
            "countries": countries_created,
            "cities_created": created,
            "cities_updated": updated,
            "skipped": False,
        }

    @classmethod
    def ensure_seed_data(cls) -> None:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        if GlobalGeoCatalog.has_persisted_catalog():
            return
        if cls.objects.exists():
            return
        # Full worldwide catalog is seeded only via manage.py seed_global_weather_locations
        # (or seed_global_data --with-weather-locations). Never sync 30k+ rows on a web request.
        region_model = django_apps.get_model("siteconfig", "RegionConfig")
        for row in cls._seed_rows():
            country_defaults = GlobalGeoCatalog.country_defaults(row["country_code"])
            region, _ = region_model.objects.get_or_create(
                code=row["country_code"],
                defaults={
                    "name": row["country_name"],
                    "default_language": country_defaults.get("default_language")
                    or "en",
                    "timezone": row["timezone"]
                    or country_defaults.get("timezone")
                    or "UTC",
                    "date_format": "YYYY-MM-DD"
                    if row["country_code"] == "GLOBAL"
                    else "DD/MM/YYYY",
                    "grading_scale": "0-100",
                    "default_currency": country_defaults.get("currency") or "USD",
                    "academic_year_start_month": 9,
                    "term_count_per_year": 3,
                },
            )
            cls.objects.get_or_create(
                region=region,
                city=row["city"],
                defaults={
                    "label": row["label"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "timezone": row["timezone"],
                    "sort_order": row["sort_order"],
                },
            )

    @classmethod
    def get_default(cls):
        cls.ensure_seed_data()
        preferred_timezone = getattr(settings, "TIME_ZONE", "UTC") or "UTC"
        location = (
            cls.objects.select_related("region")
            .filter(is_active=True, timezone=preferred_timezone)
            .order_by("sort_order", "city")
            .first()
        )
        if location:
            return location
        return (
            cls.objects.select_related("region")
            .filter(is_active=True)
            .order_by("sort_order", "city")
            .first()
        )


class RegionalPitch(models.Model):
    """Per-country marketing copy and SEO for the public landing."""

    country_code = models.CharField(
        max_length=2,
        unique=True,
        db_index=True,
        help_text="ISO 3166-1 alpha-2 (e.g. CM, CA).",
    )
    headline = models.CharField(max_length=200)
    subheadline = models.CharField(max_length=400, blank=True)
    features = models.JSONField(
        default=list,
        blank=True,
        help_text="List of feature strings or {title, description} dicts.",
    )
    visual_variant = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional: hero image or layout variant key.",
    )
    seo_title = models.CharField(max_length=120, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_code"]
        verbose_name = "Regional pitch"
        verbose_name_plural = "Regional pitches"

    def __str__(self):
        return f"{self.country_code}: {self.headline}"


class GlobalBrandRegistry(models.Model):
    """
    Canonical per-country brand and academic defaults used for marketing,
    localization, compliance, and UI behavior defaults.
    """

    iso_code = models.CharField(
        max_length=2,
        primary_key=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. CM, CA, BR).",
    )
    country_name = models.CharField(max_length=120)
    primary_language = models.CharField(
        max_length=16,
        default="en",
        help_text="Primary language code for this country profile (e.g. en, fr, ar).",
    )
    academic_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="ISCED levels, term structure, grading defaults, and education nuances.",
    )
    labels_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Terminology map (student, teacher, principal, etc.) for UI hydration.",
    )
    compliance_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Data residency and privacy-law defaults for this country.",
    )
    seo_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Marketing SEO defaults (headlines, summaries, proof points, metadata).",
    )
    ui_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="UI defaults such as date format, number separators, RTL, and locale hints.",
    )
    currency_code = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    source_name = models.CharField(
        max_length=64,
        blank=True,
        default="global_catalog",
        help_text="Data source name (e.g. global_catalog, unesco_uis, manual).",
    )
    source_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["iso_code"]
        verbose_name = "Global brand registry"
        verbose_name_plural = "Global brand registry"

    def __str__(self):
        return f"{self.iso_code} - {self.country_name}"


class ImpersonationLog(models.Model):
    """Audit log for super-admin tenant impersonation."""

    class Action(models.TextChoices):
        SWITCH = "SWITCH", "Switch to tenant"
        END = "END", "End impersonation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="impersonation_logs",
    )
    peer_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="impersonation_logs_as_peer",
        help_text="Second platform operator recorded for four-eyes impersonation.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="impersonation_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    reason = models.TextField(
        blank=True,
        help_text="Operator justification for impersonation (governance / audit).",
    )
    support_ticket_ref = models.CharField(
        max_length=120,
        blank=True,
        help_text="External ticket or incident reference, if any.",
    )
    read_only = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether the impersonation session was read-only (None = legacy log rows).",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor"]),
            models.Index(fields=["school"]),
            models.Index(fields=["-created_at"]),
        ]
        verbose_name = "Impersonation log"
        verbose_name_plural = "Impersonation logs"

    def __str__(self):
        return f"{self.actor_id} {self.action} {self.school_id} @ {self.created_at}"


class GlobalSyllabus(models.Model):
    """World Engine global syllabus/standards nodes for semantic mapping."""

    code = models.CharField(
        max_length=120, unique=True, help_text="Unique code (e.g. subject-grade-topic)."
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["country_code", "sort_order", "code"]
        verbose_name = "Global syllabus node"
        verbose_name_plural = "Global syllabus nodes"

    def __str__(self):
        return f"{self.code}: {self.name}"


class LearningPassport(models.Model):
    """World Engine learner credential / record."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_passports",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learning_passports",
    )
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    credentials = models.JSONField(
        default=dict,
        blank=True,
        help_text="Achievements, badges, mapped syllabus nodes.",
    )
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("user", "school")]
        verbose_name = "Learning passport"
        verbose_name_plural = "Learning passports"

    def __str__(self):
        return f"Passport {self.user_id} ({self.school_id or 'global'})"
