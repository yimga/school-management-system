from django.apps import AppConfig


class MetadataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.metadata"
    verbose_name = "Metadata (Custom Fields)"

    def ready(self):
        import apps.metadata.signals  # noqa: F401

        from apps.metadata.admin import (
            ConfigMutationAuditLogAdmin,
            DynamicFieldDefinitionAdmin,
            DynamicFieldValueAdmin,
            EntityCatalogEntryAdmin,
        )
        from apps.metadata.models import (
            ConfigMutationAuditLog,
            DynamicFieldDefinition,
            DynamicFieldValue,
            EntityCatalogEntry,
        )
        from config.admin import register_both

        # Batch 14 Phase 5: canonical DynamicField* admin lives on metadata models (tenant + platform).
        register_both(DynamicFieldDefinition, DynamicFieldDefinitionAdmin)
        register_both(DynamicFieldValue, DynamicFieldValueAdmin)
        # Console domain links reverse tenant admin; default @admin.register only hit django.contrib.admin.site.
        register_both(EntityCatalogEntry, EntityCatalogEntryAdmin)
        register_both(ConfigMutationAuditLog, ConfigMutationAuditLogAdmin)

        from apps.metadata.siteconfig_dynamicfield_bridge import (
            connect_siteconfig_dynamicfield_dual_write,
        )

        connect_siteconfig_dynamicfield_dual_write()
