"""
Metadata admin: DynamicField (15.2) and state machine definitions.
Enables tenant/platform to define and manage custom attributes without DDL.
"""
from django.contrib import admin
from .models import DynamicFieldDefinition, DynamicFieldValue, StateMachineDefinition, EntityState


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
