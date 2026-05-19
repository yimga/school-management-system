from django.apps import AppConfig


class SchoolsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.schools"
    verbose_name = "Schools (Multi-tenant)"

    def ready(self) -> None:
        # Membership audit signals (compliance AuditLog for permission changes).
        from apps.schools import signals_membership_audit  # noqa: F401
        from apps.schools import signals_tenant_cache  # noqa: F401
