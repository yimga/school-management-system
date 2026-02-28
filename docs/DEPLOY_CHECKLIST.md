# Deploy checklist (Phase Deploy)

Run before and after deployment to ensure health and isolation.

## Environment and feature flags (index)

Use these env vars and flags to control behavior; avoid hardcoding. Document any new ones here.

| Env / flag | Effect | Default / note |
|------------|--------|----------------|
| `DEBUG` | Django debug mode; never True in production | `False` in prod |
| `USE_DJANGO_TENANTS` | Schema-per-tenant (django-tenants). **Default: 1 (on) for PostgreSQL.** Set to 0 to use shared table + RLS. | 1 = schema-per-tenant (default when PostgreSQL), 0 = shared table |
| `DISABLE_USAGE_LIMIT_MIDDLEWARE` | Turn off Plan max_students/max_staff enforcement | Unset = middleware on |
| `ALLOWED_HOSTS` | Comma-separated hosts for the app | Must include subdomains if used |
| `SECRET_KEY` | Django secret; keep out of repo | Required |
| `CADDY_CHECK_ALLOWED_IPS` | Comma-separated IPs allowed to call `/api/caddy-check/`; if set, other IPs get 403 | Unset = all allowed |
| `DISCOVERY_RATE_LIMIT_*` | (Optional) Override discovery POST limit; see apps.schools.section8_views | Default 10 per 15 min per IP |
| (Future) `ENABLE_LTI` | Enable LTI 1.3 endpoints | Off until Section 8 |
| (Future) `WEBHOOK_HMAC_SECRET` | HMAC key for outbound webhooks | Per-school or global |

## Pre-deploy

- **Migrations:** `python manage.py migrate --noinput` (single-schema) or `migrate_schemas --shared` then `migrate_schemas --tenant` (django-tenants). **Migration order:** If adding migrations, set `dependencies` so they run in order (e.g. 0101 depends on 0100); see `apps/siteconfig/migrations/` for latest.
- **Static:** `python manage.py collectstatic --noinput` (verify themes/assets bundled).
- **Deploy check:** `python manage.py check --deploy` (security, DEBUG, cookies).
- **Sequence sync:** If using schema-per-tenant, run sync_tenant_sequences (or equivalent) after migration to avoid ID collisions.

## Pre-merge checklist (per phase or feature branch)

Before merging a branch that completes a phase or significant feature:

1. Run `python manage.py check --deploy`.
2. Run phase- or area-relevant tests (e.g. `pytest apps/schools/tests/test_plan_and_feature_gate.py` for Phase D).
3. Run one Gap Analysis prompt that matches the change (e.g. ghost tenant after adding a new API).
4. If the phase is now complete, update the **Phase status table** in the roadmap and, if applicable, `docs/PLAN_VERIFICATION_AUDIT.md`.

## Post-deploy verification

- **Data isolation:** If multi-tenant, confirm schema_a cannot see schema_b (run isolation test or `db_health_check`).
- **Branding:** Login page and key UI use tenant/school branding (no hardcoded logo/colors).
- **Regional terms:** Onboarding and locale use tenant/region settings (currency, date format).
- **Offline sync (if enabled):** Stress test offline queue and conflict resolution.
- **Brotli/Gzip:** Static and partials served with compression where configured.
- **Backup verification (once per release):** Confirm backup job runs (and optionally run a restore in staging) so backups are proven, not only configured.

## CDN / edge (Plan VII)

- **Cache-control:** Set `Cache-Control` and `Vary` on static/asset views (e.g. `max-age=31536000` for hashed assets, `public` for immutable).
- **Asset versioning:** Use `STATIC_URL` with `?v=` or hashed filenames (e.g. `ManifestStaticFilesStorage`) so CDN and browsers cache by version.
- **Recommended CDN:** Put a CDN (Cloudflare, Render CDN, or Nginx) in front of the app; configure origin to app URL and optional static-only subdomain. Document in hosting/DNS; actual CDN is infra, not repo.

## Optional (Phase 5/6)

- **SSL/DNS:** Wildcard DNS, Caddy or Nginx, Cloudflare for SaaS for static at edge.
- **DB backups:** Daily multi-tenant backups (e.g. per-schema dumps); read replicas where applicable.
- **CI/CD:** Run tests in dummy tenant schema; build image; run migrate_schemas in pipeline before app start.
- **Terraform/IaC:** Global registry and regional cells; release script that runs migrations before app start.

## Rate limiting (when adding public or webhook APIs)

- Plan for **per-tenant** rate limiting (e.g. per-school API or webhook limits) so one school’s script or misconfiguration cannot exhaust connections or CPU for others. Document in Phase D/E or Section 8; implement when adding public or webhook endpoints.

## Integration security checklist (when adding LTI, webhooks, or OAuth)

- No secrets in logs or API responses.
- Outbound webhooks: HMAC or signed JWT; minimal payload; tenant_id in envelope.
- Scoped tokens and strict scope checks (e.g. library module: student_name + grade only, never tuition/medical).
- tenant_id (or school_id) in every request; validate before DB access.
- Audit log every external-tool access to data.

## Quick reference

- Gap analysis: `python manage.py phase_i_gap_analysis`
- DB health: `python manage.py db_health_check`
- Usage limit: Set `DISABLE_USAGE_LIMIT_MIDDLEWARE=1` to turn off plan limits.
- Env index: See "Environment and feature flags" above.
