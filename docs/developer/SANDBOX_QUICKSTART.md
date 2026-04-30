# Local sandbox quickstart (developers)

This is the **minimum** path to run a tenant-backed API surface locally for integration work. It is **not** a hosted “developer sandbox” product; it replaces the older “one-click external sandbox” placeholder with **repeatable commands** you can script in CI later.

## Prerequisites

- Python env with repo dependencies installed (see root `README` / `requirements`).
- SQLite or your configured `DATABASE_URL` for development.

## Create or refresh a demo tenant

Use the management command with a **school slug** (required):

```bash
python manage.py ensure_demo_environment --school-slug=demo-school
```

Use another slug for a second dev tenant:

```bash
python manage.py ensure_demo_environment --school-slug=my-dev-school
```

Certification references: `apps/schools/tests/test_ensure_demo_environment_command.py`, `apps/schools/tests/test_growth_funnel.py` (cron wrapper).

## Tenant JavaScript client (ESM)

The minimal SDK lives under `sdk/js/`:

- `sdk/js/runmycampus-client.mjs`
- `sdk/js/package.json` (`@runmycampus/sdk-client`)

Point `baseUrl` at your local tenant host and supply auth tokens from your OAuth/API flow (`docs/developer/API_USAGE.md`).

## Automated E2E bar (still open)

A **single CI flow** covering register app → OAuth token → tenant install → webhook receive remains tracked in `docs/generated/system_closure_map.json` under **developer_platform → missing_pieces**. This document closes only the **documentation / provisioning** slice.

## Authority

Single execution source of truth: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` (§11.4 batch **1139**).
