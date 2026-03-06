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
