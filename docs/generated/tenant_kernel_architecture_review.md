# Tenant kernel architecture review

**Generated:** 2026-05-20T02:17:46.661657+00:00

## Mode

- **TENANCY_MODE:** `RLS`
- **USE_DJANGO_TENANTS:** `False`
- **DB vendor:** `sqlite`
- **RLS active (engine):** `False`
- **FORCE RLS migration:** `True`

## Proof differences

- **sqlite:** RLS session GUCs are no-ops; isolation relies on queryset scoping + middleware.
- **postgresql_rls:** app.current_school_id + FORCE RLS bind tenant rows when TENANCY_MODE=RLS.
- **postgresql_schema:** django-tenants schema routing when USE_DJANGO_TENANTS=True.
