"""
Metadata engine: custom fields without DDL (JSONB/EAV style).
DynamicFieldDefinition defines allowed keys per entity type; DynamicFieldValue stores values.
"""
from django.db import models


class DynamicFieldDefinition(models.Model):
    """
    Defines a custom field that can be attached to an entity type (e.g. student, invoice).
    No DDL change on core models; values stored in DynamicFieldValue.
    """

    entity_type = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Entity type, e.g. student, invoice, classroom.",
    )
    field_key = models.CharField(max_length=120, help_text="Unique key within entity_type, e.g. preferred_name.")
    label = models.CharField(max_length=255, blank=True)
    data_type = models.CharField(
        max_length=20,
        default="string",
        choices=[
            ("string", "String"),
            ("number", "Number"),
            ("boolean", "Boolean"),
            ("json", "JSON"),
            ("date", "Date"),
        ],
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Null = platform-wide definition.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Dynamic Field Definition"
        verbose_name_plural = "Dynamic Field Definitions"
        unique_together = [["entity_type", "field_key", "school"]]
        ordering = ["entity_type", "field_key"]

    def __str__(self):
        return f"{self.entity_type}.{self.field_key}"


class DynamicFieldValue(models.Model):
    """
    Stores a single custom field value for an entity (no DDL on core models).
    entity_id is the PK of the target entity; entity_type must match DynamicFieldDefinition.
    """

    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True, help_text="Target entity PK (e.g. student id).")
    field_key = models.CharField(max_length=120)
    value_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stored value (string as {\"v\": \"...\"}, number as {\"v\": 1}, etc.).",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Dynamic Field Value"
        verbose_name_plural = "Dynamic Field Values"
        unique_together = [["school", "entity_type", "entity_id", "field_key"]]
        ordering = ["entity_type", "entity_id", "field_key"]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id}.{self.field_key}"


class StateMachineDefinition(models.Model):
    """
    Minimal state machine definition (versioned, tenant-configurable).
    states: list of state codes; transitions: list of {from_state, to_state, event}.
    """
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=80, db_index=True, help_text="e.g. admission, invoice, discipline_case.")
    states = models.JSONField(default=list, help_text="List of state codes, e.g. [\"draft\", \"submitted\", \"closed\"].")
    transitions = models.JSONField(
        default=list,
        help_text="List of {from_state, to_state, event}.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "State Machine Definition"
        verbose_name_plural = "State Machine Definitions"
        ordering = ["code"]

    def __str__(self):
        return f"{self.name} [{self.code}]"


class EntityState(models.Model):
    """Current state of an entity in a state machine."""
    definition = models.ForeignKey(
        StateMachineDefinition,
        on_delete=models.CASCADE,
        related_name="entity_states",
    )
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="+")
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    current_state = models.CharField(max_length=80)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Entity State"
        verbose_name_plural = "Entity States"
        unique_together = [["definition", "school", "entity_type", "entity_id"]]
        ordering = ["entity_type", "entity_id"]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} -> {self.current_state}"
