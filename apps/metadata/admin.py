"""
Metadata admin: DynamicField (15.2), state machine, catalog, glossary, config audit.
"""

from django.contrib import admin

from config.admin import register_both, register_platform_admin

from .models import (
    EntityState,
    FieldCatalogEntry,
    LayoutDefinition,
    MetadataDependency,
    BusinessGlossaryEntry,
    StateMachineDefinition,
)


class DynamicFieldDefinitionAdmin(admin.ModelAdmin):
    """Canonical DynamicField definitions; registered on tenant + platform in ``metadata.apps``."""

    change_form_template = "admin/metadata/dynamicfielddefinition/change_form.html"
    list_display = (
        "entity_type",
        "field_key",
        "label",
        "data_type",
        "school",
        "is_active",
        "updated_at",
    )
    list_filter = ("entity_type", "data_type", "is_active")
    search_fields = ("entity_type", "field_key", "label")
    list_editable = ("is_active",)
    ordering = ("entity_type", "field_key")
    raw_id_fields = ("school",)


class DynamicFieldValueAdmin(admin.ModelAdmin):
    """Canonical DynamicField values; registered on tenant + platform in ``metadata.apps``."""

    change_form_template = "admin/metadata/dynamicfieldvalue/change_form.html"
    list_display = ("entity_type", "entity_id", "field_key", "school", "updated_at")
    list_filter = ("entity_type",)
    search_fields = ("entity_type", "entity_id", "field_key")
    ordering = ("entity_type", "entity_id", "field_key")
    raw_id_fields = ("school",)


class StateMachineDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "entity_type", "school", "is_active", "updated_at")
    list_filter = ("entity_type", "is_active")
    search_fields = ("code", "name", "entity_type")
    raw_id_fields = ("school",)


class EntityStateAdmin(admin.ModelAdmin):
    list_display = (
        "definition",
        "entity_type",
        "entity_id",
        "current_state",
        "school",
        "updated_at",
    )
    list_filter = ("entity_type", "current_state")
    search_fields = ("entity_type", "entity_id")
    raw_id_fields = ("definition", "school")


class EntityCatalogEntryAdmin(admin.ModelAdmin):
    """Registered on tenant + platform in ``metadata.apps`` (console domain reverses)."""

    list_display = (
        "code",
        "name",
        "owning_app",
        "lifecycle_state",
        "source_pack_id",
        "source_pack_version",
        "model_label",
        "is_core",
        "updated_at",
    )
    list_filter = ("is_core", "owning_app", "lifecycle_state")
    search_fields = ("code", "name", "description")
    ordering = ("code",)


class FieldCatalogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "entity",
        "field_name",
        "label",
        "data_type",
        "is_custom",
        "defined_in_app",
    )
    list_filter = ("data_type", "is_custom")
    search_fields = ("field_name", "label")
    raw_id_fields = ("entity",)
    ordering = ("entity__code", "field_name")


class MetadataDependencyAdmin(admin.ModelAdmin):
    list_display = ("consumer_type", "consumer_code", "field", "created_at")
    list_filter = ("consumer_type",)
    search_fields = ("consumer_code",)
    raw_id_fields = ("field",)
    ordering = ("consumer_type", "consumer_code")


class BusinessGlossaryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "term",
        "locale",
        "entity_code",
        "field_name",
        "is_active",
        "updated_at",
    )
    list_filter = ("locale", "is_active")
    search_fields = ("term", "definition", "entity_code")
    ordering = ("term", "locale")


class ConfigMutationAuditLogAdmin(admin.ModelAdmin):
    """Registered on tenant + platform in ``metadata.apps`` (console domain reverses)."""

    list_display = ("target_type", "scope", "actor_id", "impact_summary", "created_at")
    list_filter = ("scope", "target_type")
    search_fields = ("target_id", "rollback_token", "reason")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


class LayoutDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scope", "school", "is_active", "updated_at")
    list_filter = ("scope", "is_active")
    search_fields = ("code", "name")
    raw_id_fields = ("school",)
    ordering = ("code", "scope")


# A bare @admin.register(Model) lands on Django's DEFAULT admin.site, which
# no urlconf in this repo mounts (config/urls, tenant_urls, manager_urls and
# public_urls were all read). The screen was therefore unreachable from any
# host. Registered explicitly below instead.
#
# apps.metadata is in SHARED_APPS, so one table holds every school's rows.
# The three definitions that carry a concrete `school` column go on BOTH
# sites: TenantAdminSite.register wraps them in _TenantScopedQuerysetMixin,
# so a tenant sees only its own rows, matching how this app's other models
# (DynamicFieldDefinition, DynamicFieldValue, EntityCatalogEntry) are
# already registered on both sites from metadata/apps.py.
register_both(StateMachineDefinition, StateMachineDefinitionAdmin)
register_both(EntityState, EntityStateAdmin)
register_both(LayoutDefinition, LayoutDefinitionAdmin)

# The remaining three have NO school column. On the tenant site an
# unclassified SHARED model with no school column is deliberately
# fail-closed -- _TenantUnclassifiedFailClosedMixin renders .none() and logs
# a warning -- so registering them there would ship three permanently empty
# screens. They are platform catalogs; the operator gets them.
register_platform_admin(FieldCatalogEntry, FieldCatalogEntryAdmin)
register_platform_admin(MetadataDependency, MetadataDependencyAdmin)
register_platform_admin(BusinessGlossaryEntry, BusinessGlossaryEntryAdmin)
