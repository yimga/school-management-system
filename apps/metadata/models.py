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
    field_key = models.CharField(
        max_length=120, help_text="Unique key within entity_type, e.g. preferred_name."
    )
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
    required = models.BooleanField(
        default=False,
        help_text="When True, runtime may treat the field as mandatory (aligned with siteconfig EAV).",
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
    entity_id = models.CharField(
        max_length=64, db_index=True, help_text="Target entity PK (e.g. student id)."
    )
    field_key = models.CharField(max_length=120)
    value_json = models.JSONField(
        default=dict,
        blank=True,
        help_text='Stored value (string as {"v": "..."}, number as {"v": 1}, etc.).',
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
    entity_type = models.CharField(
        max_length=80,
        db_index=True,
        help_text="e.g. admission, invoice, discipline_case.",
    )
    states = models.JSONField(
        default=list,
        help_text='List of state codes, e.g. ["draft", "submitted", "closed"].',
    )
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
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="+"
    )
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


# Lifecycle states for metadata catalog entries (§3.3 RUNMYCAMPUS).
ENTITY_CATALOG_LIFECYCLE_DRAFT = "draft"
ENTITY_CATALOG_LIFECYCLE_ACTIVE = "active"
ENTITY_CATALOG_LIFECYCLE_DEPRECATED = "deprecated"
ENTITY_CATALOG_LIFECYCLE_CHOICES = [
    (ENTITY_CATALOG_LIFECYCLE_DRAFT, "Draft"),
    (ENTITY_CATALOG_LIFECYCLE_ACTIVE, "Active"),
    (ENTITY_CATALOG_LIFECYCLE_DEPRECATED, "Deprecated"),
]


class EntityCatalogEntry(models.Model):
    """
    Catalog entry for a logical entity in the platform (e.g. student, invoice, attendance_record).
    This is part of the formal Metadata Catalog (see plan Workstream I).
    """

    code = models.CharField(
        max_length=80,
        unique=True,
        help_text="Stable entity code, e.g. student, invoice, attendance_record.",
    )
    name = models.CharField(
        max_length=120,
        help_text="Human-readable name, e.g. Student, Invoice, Attendance Record.",
    )
    description = models.TextField(blank=True)
    owning_app = models.CharField(
        max_length=80,
        blank=True,
        help_text="Optional owning app/domain (e.g. people, finance, academics).",
    )
    model_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional dotted model label (e.g. people.StudentProfile).",
    )
    is_core = models.BooleanField(
        default=True,
        help_text="True if this is a core platform entity; False if defined by a pack or extension.",
    )
    lifecycle_state = models.CharField(
        max_length=20,
        choices=ENTITY_CATALOG_LIFECYCLE_CHOICES,
        default=ENTITY_CATALOG_LIFECYCLE_ACTIVE,
        db_index=True,
        help_text="Catalog lifecycle: draft, active, or deprecated.",
    )
    source_pack_id = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Optional pack identifier (e.g. package slug) if this entry comes from a pack.",
    )
    source_pack_version = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional pack version when source_pack_id is set.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Entity Catalog Entry"
        verbose_name_plural = "Entity Catalog Entries"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code}"


class FieldCatalogEntry(models.Model):
    """
    Catalog entry for a field on an entity (standard or dynamic).
    Backed by either a concrete model field or a DynamicFieldDefinition.
    """

    entity = models.ForeignKey(
        EntityCatalogEntry,
        on_delete=models.CASCADE,
        related_name="fields",
    )
    field_name = models.CharField(
        max_length=120,
        help_text="Internal field name (e.g. first_name, admission_number, custom:preferred_name).",
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable label.",
    )
    data_type = models.CharField(
        max_length=40,
        help_text="Logical data type (e.g. string, number, boolean, date, json).",
    )
    is_custom = models.BooleanField(
        default=False,
        help_text="True if this field is defined via DynamicFieldDefinition / metadata packs.",
    )
    is_required = models.BooleanField(default=False)
    is_indexed = models.BooleanField(default=False)
    defined_in_app = models.CharField(
        max_length=80,
        blank=True,
        help_text="Owning app for the field definition (e.g. people, finance, metadata).",
    )
    source = models.CharField(
        max_length=120,
        blank=True,
        help_text="Where this field came from (e.g. model, dynamic_field, pack:finance_core_v1).",
    )
    # Move 3: sensitivity tier drives field-level RLS / DLP. The PDP compares
    # the requester's clearance against this and either returns the value or
    # redacts it.
    SENSITIVITY_PUBLIC = "public"
    SENSITIVITY_INTERNAL = "internal"
    SENSITIVITY_RESTRICTED = "restricted"
    SENSITIVITY_CONFIDENTIAL = "confidential"
    SENSITIVITY_SECRET = "secret"
    SENSITIVITY_CHOICES = [
        (SENSITIVITY_PUBLIC, "Public"),
        (SENSITIVITY_INTERNAL, "Internal"),
        (SENSITIVITY_RESTRICTED, "Restricted"),
        (SENSITIVITY_CONFIDENTIAL, "Confidential"),
        (SENSITIVITY_SECRET, "Secret / regulated"),
    ]
    sensitivity_tier = models.CharField(
        max_length=20,
        choices=SENSITIVITY_CHOICES,
        default=SENSITIVITY_INTERNAL,
        db_index=True,
        help_text="Move 3: drives field-level RLS at query/serializer/export time.",
    )
    compliance_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags like ['pii','ferpa','gdpr_special'] consumed by DLP rules.",
    )
    dlp_redaction_strategy = models.CharField(
        max_length=20,
        default="null",
        help_text="One of 'null', 'mask', 'hash', 'tokenize'. How to redact when access is denied.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Field Catalog Entry"
        verbose_name_plural = "Field Catalog Entries"
        unique_together = [["entity", "field_name"]]
        ordering = ["entity__code", "field_name"]
        indexes = [
            models.Index(fields=["sensitivity_tier"], name="md_fc_sens_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.entity.code}.{self.field_name}"


class MetadataDependency(models.Model):
    """
    Dependency edge from a metadata consumer (dashboard, workflow, policy, API, template, integration)
    to an entity.field in the catalog. Supports lineage-first rule (see plan Workstream I7).
    """

    CONSUMER_TYPES = [
        ("dashboard", "Dashboard"),
        ("workflow", "Workflow"),
        ("policy", "Policy"),
        ("report", "Report"),
        ("api", "API"),
        ("template", "Template"),
        ("integration", "Integration"),
        ("other", "Other"),
    ]

    consumer_type = models.CharField(
        max_length=40,
        choices=CONSUMER_TYPES,
        help_text="Type of metadata consumer.",
    )
    consumer_code = models.CharField(
        max_length=160,
        help_text="Stable code/identifier for the consumer (e.g. dashboard:principal_home, workflow:fee_reminder).",
    )
    field = models.ForeignKey(
        FieldCatalogEntry,
        on_delete=models.CASCADE,
        related_name="dependencies",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Metadata Dependency"
        verbose_name_plural = "Metadata Dependencies"
        unique_together = [["consumer_type", "consumer_code", "field"]]
        ordering = ["consumer_type", "consumer_code"]

    def __str__(self) -> str:
        return f"{self.consumer_type}:{self.consumer_code} -> {self.field}"


class BusinessGlossaryEntry(models.Model):
    """
    Business-first glossary: education term → technical metadata (plan Workstream I1).
    Maps human terms to entity/field codes for lineage and data dictionary.
    """

    term = models.CharField(
        max_length=160,
        help_text="Business/education term (e.g. Report Card, Transcript, Fee).",
    )
    definition = models.TextField(blank=True)
    entity_code = models.CharField(
        max_length=80,
        blank=True,
        db_index=True,
        help_text="Optional link to EntityCatalogEntry.code.",
    )
    field_name = models.CharField(max_length=120, blank=True)
    locale = models.CharField(max_length=10, default="en")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Business Glossary Entry"
        verbose_name_plural = "Business Glossary Entries"
        ordering = ["term", "locale"]
        unique_together = [["term", "locale"]]

    def __str__(self) -> str:
        return f"{self.term} ({self.locale})"


class ConfigMutationAuditLog(models.Model):
    """
    Audit trail for privileged metadata/config mutations (plan Workstream I4 / §15).
    Who, what, old/new, scope, impact, rollback token.
    """

    SCOPE_CHOICES = [
        ("platform", "Platform"),
        ("region", "Region"),
        ("blueprint", "Blueprint"),
        ("plan", "Plan"),
        ("tenant", "Tenant"),
        ("sandbox", "Sandbox"),
    ]

    actor_id = models.IntegerField(
        null=True, blank=True, help_text="User ID if applicable."
    )
    target_type = models.CharField(
        max_length=80,
        help_text="Config type (e.g. platform tenant settings row, RegionConfig, blueprint, policy_bundle).",
    )
    target_id = models.CharField(max_length=120, blank=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="tenant")
    old_value_json = models.JSONField(default=dict, blank=True)
    new_value_json = models.JSONField(default=dict, blank=True)
    impact_summary = models.CharField(max_length=500, blank=True)
    rollback_token = models.CharField(max_length=64, blank=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Config Mutation Audit Log"
        verbose_name_plural = "Config Mutation Audit Logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.target_type}@{self.scope} {self.created_at}"


class MetadataChangeLog(models.Model):
    """
    Central audit trail for metadata object changes (plan todo 6).
    Captures: actor, object, old/new (summarized), scope, tenants affected, timestamp, reason.
    """

    actor_id = models.IntegerField(null=True, blank=True)
    object_type = models.CharField(
        max_length=80,
        help_text="Metadata type (e.g. EntityCatalogEntry, PolicyBundle).",
    )
    object_id = models.CharField(max_length=120, blank=True, db_index=True)
    scope = models.CharField(
        max_length=20,
        choices=ConfigMutationAuditLog.SCOPE_CHOICES,
        default="tenant",
        db_index=True,
    )
    old_value_summary = models.JSONField(default=dict, blank=True)
    new_value_summary = models.JSONField(default=dict, blank=True)
    tenants_affected = models.JSONField(
        default=list, blank=True, help_text="List of tenant/school IDs if scope allows."
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Metadata Change Log"
        verbose_name_plural = "Metadata Change Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.object_type}@{self.scope} {self.created_at}"


class LayoutDefinition(models.Model):
    """
    Layout/UI as metadata (plan I6). Page or section layout: widget keys, order, options.
    Drives UI composition without code changes.
    """

    code = models.CharField(
        max_length=80,
        db_index=True,
        help_text="e.g. dashboard_principal_home, form_student_edit.",
    )
    name = models.CharField(max_length=120, blank=True)
    scope = models.CharField(
        max_length=20,
        choices=ConfigMutationAuditLog.SCOPE_CHOICES,
        default="tenant",
        db_index=True,
    )
    layout_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structure: sections, widget_keys, order, options (metadata-driven UI).",
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
        verbose_name = "Layout Definition"
        verbose_name_plural = "Layout Definitions"
        ordering = ["code", "scope"]

    def __str__(self) -> str:
        return f"{self.code} ({self.scope})"


from .models_derived_lineage import DerivedValueLineage  # noqa: F401,E402 — registers the record-level lineage model
