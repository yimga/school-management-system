"""
Metadata admin: DynamicField (15.2), state machine, catalog, glossary, config audit.
"""
from django.contrib import admin
from .models import (
    ConfigMutationAuditLog,
    DynamicFieldDefinition,
    DynamicFieldValue,
    EntityCatalogEntry,
    EntityState,
    FieldCatalogEntry,
    LayoutDefinition,
    MetadataDependency,
    BusinessGlossaryEntry,
    StateMachineDefinition,
)


@admin.register(DynamicFieldDefinition)
class DynamicFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "field_key", "label", "data_type", "school", "is_active", "updated_at")
    list_filter = ("entity_type", "data_type", "is_active")
    search_fields = ("entity_type", "field_key", "label")
    list_editable = ("is_active",)
    ordering = ("entity_type", "field_key")
    raw_id_fields = ("school",)


@admin.register(DynamicFieldValue)
class DynamicFieldValueAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "field_key", "school", "updated_at")
    list_filter = ("entity_type",)
    search_fields = ("entity_type", "entity_id", "field_key")
    ordering = ("entity_type", "entity_id", "field_key")
    raw_id_fields = ("school",)


@admin.register(StateMachineDefinition)
class StateMachineDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "entity_type", "school", "is_active", "updated_at")
    list_filter = ("entity_type", "is_active")
    search_fields = ("code", "name", "entity_type")
    raw_id_fields = ("school",)


@admin.register(EntityState)
class EntityStateAdmin(admin.ModelAdmin):
    list_display = ("definition", "entity_type", "entity_id", "current_state", "school", "updated_at")
    list_filter = ("entity_type", "current_state")
    search_fields = ("entity_type", "entity_id")
    raw_id_fields = ("definition", "school")


@admin.register(EntityCatalogEntry)
class EntityCatalogEntryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "owning_app", "lifecycle_state", "model_label", "is_core", "updated_at")
    list_filter = ("is_core", "owning_app", "lifecycle_state")
    search_fields = ("code", "name", "description")
    ordering = ("code",)


@admin.register(FieldCatalogEntry)
class FieldCatalogEntryAdmin(admin.ModelAdmin):
    list_display = ("entity", "field_name", "label", "data_type", "is_custom", "defined_in_app")
    list_filter = ("data_type", "is_custom")
    search_fields = ("field_name", "label")
    raw_id_fields = ("entity",)
    ordering = ("entity__code", "field_name")


@admin.register(MetadataDependency)
class MetadataDependencyAdmin(admin.ModelAdmin):
    list_display = ("consumer_type", "consumer_code", "field", "created_at")
    list_filter = ("consumer_type",)
    search_fields = ("consumer_code",)
    raw_id_fields = ("field",)
    ordering = ("consumer_type", "consumer_code")


@admin.register(BusinessGlossaryEntry)
class BusinessGlossaryEntryAdmin(admin.ModelAdmin):
    list_display = ("term", "locale", "entity_code", "field_name", "is_active", "updated_at")
    list_filter = ("locale", "is_active")
    search_fields = ("term", "definition", "entity_code")
    ordering = ("term", "locale")


@admin.register(ConfigMutationAuditLog)
class ConfigMutationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("target_type", "scope", "actor_id", "impact_summary", "created_at")
    list_filter = ("scope", "target_type")
    search_fields = ("target_id", "rollback_token", "reason")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(LayoutDefinition)
class LayoutDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scope", "school", "is_active", "updated_at")
    list_filter = ("scope", "is_active")
    search_fields = ("code", "name")
    raw_id_fields = ("school",)
    ordering = ("code", "scope")
