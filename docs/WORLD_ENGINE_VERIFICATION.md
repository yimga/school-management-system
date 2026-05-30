# World Engine Verification Checklist

Status for each item from the World Engine execution directive (§11 and §9). Update when completed.

| §11 Item | Status | Notes |
|----------|--------|--------|
| Proven-First (django-tenants, OIDC, Celery+Redis, i18n) | Done | In use; no custom multi-tenancy. |
| Branding (base.html PUBLIC_BRAND_MODE, footer RunMyCampus, platform-only footer, branding_metadata) | Done | base.html, dashboard_footer, TENANT_BRANDING_CSS_VARS. |
| Security (ImpossibleTravel → AccountLockdown) | Done | Middleware + check_impossible_travel; lockdown_user_account. |
| Data Sovereignty (regional_cluster, db_alias, multi-DB router, read replica, mega-schools) | Done | School.regional_cluster, dedicated_db_alias; TenantDatabaseRouter; DATABASE_READ_REPLICA_ALIAS. |
| Workflow (WorkflowConfig JSON, dynamic wizards, tenant-reorderable steps) | Done | WorkflowConfig, WorkflowWizardView, workflow_key steps. |
| AI (Ollama workflow clues by country, GlobalSyllabus) | Done | get_workflow_clues, GlobalSyllabus; OllamaInferenceService per plan. |
| Aesthetic (Super Admin Obsidian #0B0E14, Tenant light + brand) | Done | backend_base.html, TENANT_FORCE_LIGHT_THEME, TENANT_BRANDING_CSS_VARS. |
| Celery (high-concurrency pool, chunking, Redis broker) | Done | process_bulk_grades, emergency_broadcast_fanout; WORLD_ENGINE_SCALE_OPERATIONS. |
| KEDA | Doc | Documented in WORLD_ENGINE_SCALE_OPERATIONS. |
| Cache (tenant_id/schema_name in tenant-scoped keys; audit) | Done | get_tenant_cache_prefix, tenant_cache_key; audit in Part F. |
| Error pages (403/404/500 manager = platform branding) | Done | Handlers pass request; base.html PUBLIC_BRAND_MODE. |
| CDN | Doc | WORLD_ENGINE_SCALE_OPERATIONS. |
| WebSocket (Redis Pub/Sub) | Doc | WORLD_ENGINE_SCALE_OPERATIONS; Channels optional. |
| i18n (makemessages; wrap hardcoded strings) | Done | `sync_i18n_catalog --compile` (polib, no gettext required); CI: `verify_world_engine_i18n_ci.py` + `scan_locale_coverage.py --compare`; pre-deploy: `verify_i18n_catalog_fresh.py`. |
| Scale & HA (10M students, 6 continents) | Verify | Ongoing; architecture and ops doc. |

## Cache key audit (tenant-scoped vs global)

- **Tenant-scoped:** Use `get_tenant_cache_prefix(request)` or `tenant_cache_key(base_key, request)`. Applied in: evals (caching, ranking), dashboard (admin_context), portal (services, views_ai_copilot, views badge_verify), reports (services, bi_services), compliance (views_dashboard, access_control, alerts, signals), observability (views weather + AI copilot metrics, admin_extras), accounts (BACKEND_STATUS_FRAGMENT, security_health), siteconfig (feature_control), finance (offline idempotency). AI copilot usage metrics and access_rules_version are now tenant-scoped.
- **Global (intentional):** score_convert (evals/grading), site_settings_v1 (maintenance_mode), geoip/region_config, observability health test key, IP-based rate limits that do not store tenant data.
- **Ref:** `docs/architecture/cache_keys.md` for full table.

## i18n (locale and messages)

- **Locale path:** `locale/` (LOCALE_PATHS in settings). Create `locale/<lang>/LC_MESSAGES/` for each language.
- **Extract strings:** `python manage.py makemessages -l en` (requires GNU gettext: `msguniq`, `xgettext`). Add `-a` to update existing .po.
- **Compile:** `python manage.py sync_i18n_catalog --compile` (polib `.mo`, no msgfmt) or `python manage.py compilemessages` when GNU gettext is installed.
- **CI:** `python scripts/verify_world_engine_i18n_ci.py` → **WORLD_ENGINE_I18N_CI_PASS** (architectural-boundaries job `world-engine-i18n-ci` + smoke pre-deploy gate); `scan_locale_coverage.py --compare` for per-locale regression.

## Tests (World Engine Completion + Sovereign AI plan)

- **JIT / broadcast / syllabus:** `apps.siteconfig.tests.test_world_engine_jit_broadcast_syllabus` (grant/revoke consent, emergency_broadcast_fanout, national_syllabus_sync).
- **Switch-to-tenant consent:** `apps.schools.tests.test_world_engine_switch_tenant_consent` (redirect when consent missing; success when granted).
- **AI provider:** `apps.portal.tests.test_ai_provider` (delegation to OllamaInferenceService, metadata).
- **Manifest and modules:** `apps.siteconfig.tests.test_module_manifest` (get_manifest, get_school_type_config with inheritance, get_tenant_modules with school_type).
- **Run plan-related tests:** `python manage.py test apps.portal.tests.test_ai_provider apps.siteconfig.tests.test_world_engine_jit_broadcast_syllabus apps.schools.tests.test_world_engine_switch_tenant_consent apps.siteconfig.tests.test_module_manifest -v 2`

## Optionals (implemented)

- **Channels (WebSocket AI chat):** If `channels` and `channels_redis` are installed (`pip install channels channels-redis`), they are auto-added to `INSTALLED_APPS` and `ASGI_APPLICATION` / `CHANNEL_LAYERS` are set. Run with `daphne config.asgi:application` or `uvicorn config.asgi:application` for `ws/ai/chat/`. Without the packages, the app runs on WSGI only.
- **RegionalAIConfig.preferred_model_id:** Optional override in Django admin; when set, the inference service uses it instead of AIModelRegistry/default_model for that region.
- **PGVector extension:** Migration `siteconfig.0123_enable_pgvector_extension` runs `CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL only (no-op on SQLite). Requires pgvector installed on the server (e.g. `apt install postgresql-16-pgvector`). See [SOVEREIGN_STACK.md](SOVEREIGN_STACK.md#enabling-pgvector).
