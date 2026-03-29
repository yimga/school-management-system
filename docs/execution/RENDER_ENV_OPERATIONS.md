# Render Environment Operations (portable contract)

This document defines how env vars are handled so platform migration stays simple:

- Codebase owns **env key names + validation rules**
- Platform (Render/k8s/etc.) owns **secret values**
- No live secrets are committed to git

## 1) Baseline keys for Render web service

| Key | Purpose | Keep in Render | Notes |
|---|---|---|---|
| `DATABASE_URL` | Primary DB connection | Yes | Required on web/worker/beat |
| `SECRET_KEY` | Django crypto/signing | Yes (secret) | Rotate if exposed |
| `ALLOWED_HOSTS` | Host allowlist | Yes | Include root + wildcard + onrender |
| `CSRF_TRUSTED_ORIGINS` | CSRF origin allowlist | Yes | Include all HTTPS app hosts |
| `MULTI_TENANT_BASE_DOMAIN` | Tenant routing base | Yes | `runmycampus.com` in prod |
| `USE_DJANGO_TENANTS` | Tenant mode switch | Yes | `1` in deployed env |
| `DEBUG` | Debug mode | Yes | `0` in deployed env |
| `COLLABORA_BASE_URL` | Collabora endpoint URL | Yes | Required when Collabora enabled |
| `WOPI_SHARED_SECRET` | WOPI signing secret | Yes (secret) | Required when Collabora enabled |

## 2) Variables from current Render state (classification)

| Key | Status | Action |
|---|---|---|
| `ADMIN_PASSWORD` | Sensitive | Rotate now; avoid sharing in chat/docs |
| `DATABASE_URL` | Sensitive | Rotate DB credential if exposed |
| `SECRET_KEY` | Sensitive | Rotate now |
| `WOPI_SHARED_SECRET` | Sensitive | Rotate now |
| `COLLABORA_BASE_URL` | Correct contract key | Keep as `https://collabora.runmycampus.com` |
| `DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT` | Possibly redundant | Keep only if settings explicitly use them |
| `MTN_MOMO_SECRET` / `ORANGE_MOMO_SECRET` | Placeholder in current state | Replace with real secret or remove until enabled |

## 3) Validation commands

Run locally (with env exported) or in CI:

```bash
python scripts/verify_env_contract.py --profile render-core
python scripts/verify_env_contract.py --profile render-collabora
```

Optional pre-deploy gate wiring:

```bash
RUN_ENV_CONTRACT_GATE=1 RUN_COLLABORA_ENV_CONTRACT_GATE=1 bash scripts/pre_deploy_gate.sh
```

## 4) Collabora URL must not hit the Django app

If `curl -I "$COLLABORA_BASE_URL/hosting/discovery"` redirects to your main site or `school-not-found`, the collabora hostname is still wired to Gunicorn. Point that hostname at the Collabora service instead (see `docs/execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md`). This is an infra routing fix, not an app env var change.

## 5) Portability rule

When migrating platforms, keep the same key names and only remap where values are sourced:

- Render: service env vars / env groups
- Kubernetes: `Secret` + deployment env refs
- Docker Compose: `.env` or compose `environment`
- CI: repository/environment secrets
