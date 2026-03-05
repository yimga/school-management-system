# Event Outbox & Marketplace MVP (RunMyCampus Blueprint)

## Event Outbox (`apps.events`)

Transactional outbox for domain events: emit from the service layer; a consumer processes the outbox for notifications, automation, and webhooks.

### Emit events

```python
from apps.events.services import emit_event

# After a business operation (in the same transaction):
emit_event(
    "student.enrolled",
    {"student_id": str(student.id), "school_id": str(school.id), "grade_level": "10"},
    school_id=school.id,
    idempotency_key="enroll-123",  # optional, prevents duplicates
)
```

### Process the outbox

- **Management command:** `python manage.py process_event_outbox [--batch 100]`
- **Celery task:** `apps.events.process_event_outbox` (schedule via django_celery_beat)

### Models

- **DomainEvent**: `event_type`, `payload`, `school_id` / `schema_name`, `status`, `idempotency_key`, `retry_count`, `processed_at`, `error_message`

**Webhooks:** When the outbox is processed, matching **WebhookSubscription** rows get **WebhookDelivery** records. Run `python manage.py process_webhook_deliveries [--batch 50]` (or a Celery task) to POST to subscription URLs with HMAC signing and idempotency keys.

---

## Marketplace MVP (`apps.marketplace`)

Installable apps with scopes, widget registry, and audit. Control-plane (shared schema).

### Models

- **MarketplaceApp**: catalog entry; `slug`, `name`, `version`, `manifest` (scopes, widgets, events_consumed, events_emitted)
- **AppScope**: permission scope per app (`scope_code`, description)
- **AppInstallation**: school + app, status (active/suspended/uninstalled), config, widget_config
- **ScopeGrant**: tenant-approved scope per installation (installation + scope + granted_by)
- **AppBillingLedger**: billing line items (school, app, installation, kind, amount, currency, period_start/end)
- **AppAuditLog**: install/uninstall and scope actions
- **AppVersionCompat**: platform/app version compatibility

### Install / uninstall

```python
from apps.marketplace.services import install_app, uninstall_app, get_installed_widgets

# Install
install_app(school, app_slug_or_instance, installed_by=request.user, config={...})

# Uninstall
uninstall_app(school, app_slug_or_instance, uninstalled_by=request.user)

# Grant scopes (tenant-approved; call after install or when admin approves)
from apps.marketplace.services import grant_scopes
grant_scopes(installation, ["read:students", "write:attendance"], granted_by=request.user)

# Widget registry (for dashboard/portal)
widgets = get_installed_widgets(school)
```

### Schema patches on install

When installing an app, the pipeline can run migrations for a Django app if the manifest declares it:

- In **MarketplaceApp.manifest**, set `migrations_app` or `schema_patch_app` to a Django app label (e.g. `"my_addon_app"`).
- `install_app(school, app, run_schema_patches=True)` (default) will call `migrate <app_label>` in the **current connection context** after creating the installation. In schema-per-tenant mode, ensure the tenant schema is active (e.g. call from a request in tenant context or from a task that sets the connection schema). In RLS mode, migrations run in the single schema. Failures are logged; they do not block the install. To skip schema patches, call `install_app(..., run_schema_patches=False)`.

### App manifest

On **MarketplaceApp**, `manifest` can include:

- `scopes`: list of scope codes
- `widgets`: dict or list of widget definitions (id, config)
- `migrations_app` / `schema_patch_app`: optional Django app label to run migrations on install (see above)
- `events_consumed` / `events_emitted`: for future event-driven integrations

---

## Settings

Both apps are in **INSTALLED_APPS** and in **SHARED_APPS** when using schema-per-tenant (`USE_DJANGO_TENANTS=True`), so they live in the control-plane (public/shared) schema.
