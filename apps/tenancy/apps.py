from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"
    verbose_name = "Tenancy (Guardrails & Context)"

    def ready(self) -> None:  # noqa: D401 — Django hook
        # v4.00.5: wire the RLS-JWT auth-handoff lifecycle hooks (mint on login
        # via the middleware response path; clear on logout via signal).
        try:
            from apps.tenancy import signals_rls_jwt  # noqa: F401 — import-for-side-effect
        except ImportError:
            pass
        try:
            from apps.tenancy.boundary_core_guard import integrate_rls_bypass_context

            integrate_rls_bypass_context()
        except ImportError:
            pass
