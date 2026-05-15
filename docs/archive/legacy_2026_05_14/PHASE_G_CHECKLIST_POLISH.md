# Phase G Plan Checklist (optional / polish)

## Done

- **SyncConflict model:** `apps.siteconfig.models.SyncConflict`; created when delta-sync detects server-newer conflict. Admin: list, filter by school, actions "Resolve (server)", "Resolve (client)", "Discard".
- **Delta sync:** `apps.api.sync_services` and `sync_delta_api` create SyncConflict and return conflicts in API response.
- **Tests:** `apps.api.tests.test_delta_sync_phase_g` — conflict creation and tenant isolation.

## Optional / deferred

- **Sync Center UI:** Dedicated portal or admin view listing SyncConflict with side-by-side (server vs client) and resolve buttons. Currently resolvable via Django admin actions.
- **Frontend useOfflineSync / IndexedDB:** Offline queue and tenant-scoped sync hook for mobile/PWA; deferred.
- **Integration tests:** Run `python manage.py test apps.api.tests.test_delta_sync_phase_g` in CI to keep Phase G coverage.
