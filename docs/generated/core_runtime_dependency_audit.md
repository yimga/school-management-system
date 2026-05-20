# Core runtime dependency audit

**Generated:** 2026-05-20T01:46:07.329376+00:00

Metadata-only inventory of Django runtime, auth, CORS/CSRF, DRF/JWT, Celery, and Channels.
No secrets, credentials, or tenant-private data.

## Django runtime

- **debug:** `True`
- **running_tests:** `False`
- **use_django_tenants:** `False`
- **tenancy_mode:** `RLS`
- **wsgi_application:** `config.wsgi.application`
- **asgi_application:** `config.asgi.application`

## Auth / MFA

- **password_hashers:** `['django.contrib.auth.hashers.Argon2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher', 'django.contrib.auth.hashers.BCryptSHA256PasswordHasher', 'django.contrib.auth.hashers.ScryptPasswordHasher']`
- **otp_apps:** `['django_otp', 'django_otp.plugins.otp_totp', 'django_otp.plugins.otp_static']`
- **require_mfa_middleware:** `True`
- **manager_cookie_isolation:** `True`

## DRF / JWT

- **default_permission:** `('rest_framework.permissions.IsAuthenticated',)`
- **default_authentication:** `('rest_framework.authentication.SessionAuthentication', 'rest_framework_simplejwt.authentication.JWTAuthentication')`
- **simple_jwt:** `{'ACCESS_TOKEN_LIFETIME': '1:00:00', 'REFRESH_TOKEN_LIFETIME': '7 days, 0:00:00', 'ROTATE_REFRESH_TOKENS': True, 'BLACKLIST_AFTER_ROTATION': True, 'UPDATE_LAST_LOGIN': True}`
- **token_blacklist_installed:** `True`

## CORS / CSRF

- **cors_allowed_origins_count:** `0`
- **cors_origin_regex_count:** `1`
- **cors_allow_credentials:** `False`
- **cors_allow_all_origins:** `False`
- **csrf_trusted_origins_count:** `2`
- **csrf_subdomain_wildcards:** `['https://*.runmycampus.com']`
- **multi_tenant_base_domain:** `runmycampus.com`

## Async (Celery / Channels)

- **redis_url:** `unset`
- **celery_broker:** `unset`
- **celery_result_backend:** `django-db`
- **celery_task_always_eager:** `False`
- **celery_beat_enabled:** `True`
- **celery_beat_schedule_count:** `40`
- **celery_beat_sample:** `['accounts-key-rotation-monthly', 'accounts-sunset-stale-legacy-hashes', 'accounts-verify-audit-chain', 'analytics-at-risk-drift-watchdog', 'analytics-build-student-embeddings', 'analytics-compute-nightly-grade-predictions', 'analytics-compute-nightly-risk', 'analytics-send-risk-digest-daily', 'auto-copy-fee-plans', 'auto-generate-fee-invoices', 'calculate-monthly-revenue-stats', 'check-badge-expiry-alerts', 'compliance-mark-sla-breaches', 'customersuccess-run-auto-ticket-rules', 'expire-past-delegations', 'integrations-fetch-mailboxes', 'integrations-refresh-oauth-tokens', 'integrations-renew-push-subscriptions', 'kudos-perfect-attendance-3d', 'marketplace-health-check', 'marketplace-webhook-deliver-due', 'migration-cloud-smoke-nightly', 'migration-cloud-token-rotation-watchdog', 'migration-cloud-webhook-deliver-due', 'migration-scheduled-parity-tick']`
- **channel_layer_backend:** `channels.layers.InMemoryChannelLayer`
- **shared_task_counts_by_module:** `{'apps/automation/tasks.py': 1, 'apps/events/tasks.py': 2, 'apps/orchestration/tasks.py': 3, 'apps/migration_cloud/tasks_audit.py': 0}`

## Honest limits

- Query counts and sub-millisecond latency are not claimed in this artifact.
- Live Render/Redis/Celery worker health requires EXTERNAL infrastructure proof.
- Ollama/ASGI long-poll throughput is environment-dependent.
