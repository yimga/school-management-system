from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "👤 Accounts & Authentication"

    def ready(self):
        import apps.accounts.signals  # noqa: F401
        import apps.accounts.rebac_signals  # noqa: F401
        import apps.accounts.signals_access  # noqa: F401

        # Keep the stored SUPERADMIN grants agreeing with the resolver that
        # already enforces god-mode, so a code added by a future migration is
        # visible in the RBAC console without anyone remembering to seed it.
        from django.db.models.signals import post_migrate

        from apps.accounts.superadmin_sync import on_post_migrate

        post_migrate.connect(
            on_post_migrate,
            dispatch_uid="accounts.sync_superadmin_role_permissions",
        )
