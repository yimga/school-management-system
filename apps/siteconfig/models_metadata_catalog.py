"""
Metadata Catalog domain (plan Workstream B — seven bounded domains).
Siteconfig's dynamic field definitions/values stay on the same db tables while the
canonical metadata catalog continues to live in apps.metadata.
"""

from django.db import models


class DynamicFieldDefinition(models.Model):
    """Defines a custom field for an entity type (e.g. Student, Invoice). No DB schema change per field."""

    class DataType(models.TextChoices):
        TEXT = "TEXT", "Text"
        NUMBER = "NUMBER", "Number"
        DATE = "DATE", "Date"
        BOOLEAN = "BOOLEAN", "Boolean"
        JSON = "JSON", "JSON"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="dynamic_field_definitions",
    )
    entity_type = models.CharField(max_length=64, db_index=True)
    field_key = models.CharField(max_length=128, db_index=True)
    label = models.CharField(max_length=255)
    data_type = models.CharField(
        max_length=16, choices=DataType.choices, default=DataType.TEXT
    )
    required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["school", "entity_type", "field_key"]]
        ordering = ["entity_type", "field_key"]

    def __str__(self):
        return f"{self.entity_type}.{self.field_key}"


class DynamicFieldValue(models.Model):
    """Stores a value for a custom field on a specific entity instance."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="dynamic_field_values"
    )
    entity_type = models.CharField(max_length=64, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    field_key = models.CharField(max_length=128, db_index=True)
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    value_date = models.DateField(null=True, blank=True)
    value_json = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [["school", "entity_type", "object_id", "field_key"]]
        indexes = [models.Index(fields=["school", "entity_type", "object_id"])]

    def __str__(self):
        return f"{self.entity_type}#{self.object_id}.{self.field_key}"


__all__ = ["DynamicFieldDefinition", "DynamicFieldValue"]
