# Integrations Marketplace — Operations Handbook

**Audience:** platform operators (super-admins on `manager.runmycampus.com`) and on-call.
**Scope:** runtime operations of the per-tenant connector cascade (OAuth, webhooks, transactional mail, calendar/meeting/chat providers).
**Source of truth date:** 2026-05-16 · maintainer: integrations team.

---

## 1. Architecture in one paragraph

A school connects an external tool through `/integrations/` (per-tenant hub) or `/integrations/?campus=<id>` (per-campus override). A `ServiceIntegration` row is upserted at the (school, campus, connector_slug) scope, holding `config={"access_token": ..., "refresh_token": ..., "webhook_secret": ..., "expires_at": ...}`. The `connector_registry` enumerates supported providers + their OAuth endpoints + default scopes. The 4-step cascade resolver (campus → school → parent_school chain → env) picks which row a runtime caller gets. `PerTenantEmailBackend`, `WhatsAppIntegration`, `ZoomIntegration`, etc. all route through this. The `TenantEmailBindingMiddleware` ensures a request's `request.school` is the tenant the email backend sees.

---

## 2. Required environment variables

Set in the deployment env. The startup advisory at `IntegrationsMarketplaceConfig.ready()` will WARN-log if a production-looking env (DEBUG=False) is missing or malformed.

| Variable | Required | Example | Notes |
|---|---|---|---|
| `OAUTH_CALLBACK_BASE_URL` | prod | `https://app.runmycampus.com` | Must match the redirect URI pasted into every upstream marketplace console. Defaults to `request.get_host()` if unset (fine for dev). |
| `INTEGRATIONS_<UPPER_SLUG>_CLIENT_ID` | per connector | `INTEGRATIONS_ZOOM_CLIENT_ID=...` | One per OAuth connector you've registered with the upstream marketplace. Missing = "platform owner hasn't registered this app" refusal at OAuth-connect time. |
| `INTEGRATIONS_<UPPER_SLUG>_CLIENT_SECRET` | per connector | `INTEGRATIONS_ZOOM_CLIENT_SECRET=...` | Same. |
| `EMAIL_BACKEND` | optional | `apps.integrations_marketplace.email_backend.PerTenantEmailBackend` | Wires the per-tenant cascade for outbound transactional mail. Without this, Django uses the global ANYMAIL block. |

The full per-connector redirect URI list is available at `/integrations/admin/redirect-uris/` (platform-owner only).

---

## 3. First-time wiring of a new upstream provider

Use Zoom as the canonical example. Same flow for Google / Microsoft / Slack / etc.

1. Register the app in the upstream console (Zoom App Marketplace → Create OAuth app).
2. Paste the redirect URI shown in `/integrations/admin/redirect-uris/` (e.g. `https://app.runmycampus.com/integrations/callback/zoom/`).
3. Copy client_id + client_secret into env: `INTEGRATIONS_ZOOM_CLIENT_ID=...`, `INTEGRATIONS_ZOOM_CLIENT_SECRET=...`. Restart workers.
4. (Optional) Set a webhook URL in the upstream app config: `https://app.runmycampus.com/integrations/webhook/zoom/<integration_id>/`. The `<integration_id>` is the ServiceIntegration row pk — the operator will see this once they connect from a tenant. For Zoom, also paste the same `webhook_secret` (auto-rotated per row) into the app config.
5. School admin visits `/integrations/`, clicks "Connect Zoom" → completes OAuth → row is created → operator can confirm via `/integrations/admin/redirect-uris/` or `/integrations/events/`.

---

## 4. Day-2 operations

### 4.1 "School X says their integration broke at midnight"

```bash
# 1. Inspect the row's config — look for `disconnect_reason` or `last_refresh_error`.
python manage.py shell -c "from apps.siteconfig.models_platform_catalog import ServiceIntegration; \
  r = ServiceIntegration.objects.filter(school__name='X', connector_slug='zoom').first(); \
  print(r.is_active, r.config)"

# 2. If `disconnect_reason='invalid_grant'`: the refresh token is revoked. Tell the
#    school admin to reconnect from /integrations/. No platform action needed.
# 3. If `last_refresh_error='transport_error'`: upstream OAuth endpoint was down at
#    refresh time. Re-run refresh now: `python manage.py refresh_oauth_tokens`
# 4. If neither set: HMAC issue on the webhook side. See 4.3.
```

### 4.2 "Webhook events stopped arriving for connector Y"

1. Visit `/integrations/events/?connector=<slug>` as a school admin to see the most recent verified deliveries.
2. If recent rows exist: it's an upstream problem (provider is rate-limiting / paused subscriptions). Check the upstream marketplace dashboard.
3. If no rows for the affected period: the webhook is hitting us and being rejected. Filter `apps/integrations_marketplace/webhooks.py` rejection logs — the `reason` field tells you (`timestamp_outside_window`, `signature_mismatch`, `rate_limited`, etc.).
4. Operator can re-fire a synthetic verified delivery from the hub via the "Test" button — this proves HMAC + handler dispatch are functional in-process.

### 4.3 "Webhook signature_mismatch flood"

Almost always means the `webhook_secret` in the upstream console got out of sync with `config["webhook_secret"]` on our side. Have the school admin disconnect-then-reconnect; that rotates the secret on both sides as part of the OAuth dance (for OAuth connectors) or surfaces a new secret in the hub (for API-key connectors).

### 4.4 "We're getting hammered by an upstream that's stuck in a retry loop"

The receiver has a per-(integration_id, client_ip) rate limit of `WEBHOOK_RATE_LIMIT_PER_MINUTE=120` requests/minute. Exceeding it returns 429 with `Retry-After: 60`. To tighten further for a specific row in an incident, you can:

- Drop the integration to `is_active=False` from Django admin (the receiver short-circuits with 404 to inactive rows — upstreams give up).
- Or raise an infra-level firewall block.

### 4.5 "I need to retire / rotate a connector's platform credentials"

1. Rotate the upstream marketplace client_secret.
2. Update `INTEGRATIONS_<UPPER_SLUG>_CLIENT_SECRET` in env.
3. Restart workers.
4. The existing per-school access_tokens keep working until their next refresh. The next refresh will use the new platform secret and continue to mint new access_tokens against the same per-school refresh_token. No tenant-side reconnection required (this is what platform-level OAuth credentials are FOR).

---

## 5. Observability

### 5.1 What we emit

| Source | Mechanism | Signal |
|---|---|---|
| `refresh_due_oauth_tokens` (every 5 min via Celery beat) | Sentry transaction `integrations_marketplace.refresh_due_oauth_tokens`, op `task.hot_path` | Per-status counter tags (`refresh.refreshed`, `refresh.transport_error`, `refresh.deactivated_invalid_grant`, ...). Txn status flips to `internal_error` if any alert-worthy status fired. |
| Webhook handlers (per inbound) | `compliance.AuditLog` row + `signals.webhook_received` Django signal | Per-tenant log queryable at `/integrations/events/`. Other apps can `@receiver(webhook_received)` to react. |
| Webhook receiver rejections | `logger.warning(...)` with reason | Search worker logs for `Webhook rejected:` to triage. |
| Boot-time advisory | `logger.warning(...)` for missing/malformed `OAUTH_CALLBACK_BASE_URL` | Visible in worker / web container logs at start. |

### 5.2 Suggested Sentry alert rules

Create these in the Sentry UI (rules-as-code is a separate project):

1. **Refresh storm**: alert when `refresh.deactivated_invalid_grant > 5 in 1 hour`. Likely a tenant's whole org consent was revoked.
2. **Refresh transport flap**: alert when `refresh.transport_error > 20 in 30 min`. Upstream provider outage.
3. **Webhook handler crash**: alert on any event tagged `connector=<slug>` from the `apps.integrations_marketplace.webhook_handlers` logger at ERROR level.

### 5.3 Suggested ops dashboards

The cross-school rollup at `/manager/integrations-rollup/` shows tenant adoption per provider. Use it to size who's affected when triaging a connector outage.

---

## 6. Per-tenant configuration knobs

These live on each `ServiceIntegration.config` JSONField; operators rarely touch them, but tenants can.

| Key | Type | Purpose |
|---|---|---|
| `access_token` | str | OAuth bearer. Managed by the OAuth dance + refresh worker. |
| `refresh_token` | str | OAuth refresh. Managed by the OAuth dance. |
| `expires_at` | float (epoch) | When the access_token expires. Refresh worker decides "due" by this. |
| `webhook_secret` | str | Shared HMAC secret with the upstream provider. Auto-generated; operator-visible in the hub. |
| `scopes_override` | list[str] | v2.79 — tenant-narrowed OAuth scope set. Subset-only (server re-validates; widening attempts are rejected with a warning). UI at `/integrations/scopes/<slug>/`. |
| `disconnect_reason` | str | Set by the refresh worker on `invalid_grant`. The hub shows "Reconnect required" when this is non-empty. |
| `last_refresh_error` | str | Diagnostic from the most recent refresh attempt. |

---

## 7. Migrations

| Migration | What it does | Applied? |
|---|---|---|
| `siteconfig/0175_serviceintegration_campus_and_connector_slug` | Adds `campus` FK + `connector_slug` to ServiceIntegration. Required for the cascade resolver. | Dev: ✅. Each production tenant requires `migrate_schemas --schema=<tenant>` (or whatever the deploy pattern is). Tracked separately. |

To verify a tenant's state:
```bash
python manage.py showmigrations siteconfig | tail -10
```

---

## 8. Brand assets

The hub renders connector marks using a category-level SVG sprite at `static/sprites/integrations.svg` (Bootstrap Icons MIT). Operators wishing to swap in real provider logos:

1. Obtain the SVG from the upstream press kit + confirm redistribution rights.
2. Add a `<symbol id="integration-<slug>">` entry to `static/sprites/integrations.svg`. The template `_brand_mark.html` will pick up the slug-specific symbol via the same `<use>` ref (browser falls back to the category symbol when the slug-specific one is missing).
3. No code change required.

---

## 9. Test artifacts

- `apps/integrations_marketplace/tests/test_webhooks.py` — HMAC verifier + Slack scheme + handler registry
- `apps/integrations_marketplace/tests/test_token_refresh.py` — refresh state machine
- `apps/integrations_marketplace/tests/test_email_backend_v2_79.py` — Anymail key translation + tenant context manager
- `apps/integrations_marketplace/tests/test_communication_bridge.py` — WhatsApp + Zoom tenant pickup
- `apps/integrations_marketplace/tests/test_v2_79_followups.py` — all 7 v2.79 follow-up items
- `apps/integrations_marketplace/tests/test_celery_tenant_binding.py` — Celery signal binding + middleware-ordering backstop
- `apps/integrations_marketplace/tests/test_webhook_signal_and_events.py` — `webhook_received` Django signal + delivery-log view
- `apps/integrations_marketplace/tests/test_v2_94_residuals.py` — rate-limit + test-webhook view + scope-override form + manager rollup

Run the full marketplace SimpleTestCase suite:
```bash
python manage.py test apps.integrations_marketplace.tests --keepdb
```
