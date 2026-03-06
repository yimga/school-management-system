# App install lifecycle

This document describes the full install lifecycle for marketplace apps in RunMyCampus: request → approval → schema patch → widget registration → audit. It ties to the data model (`MarketplaceApp`, `AppInstallation`, `AppAuditLog`) and the install pipeline in `apps.marketplace.services`.

## Overview

1. **Request install** – A school (or admin) requests an app from the marketplace. The app is represented by a `MarketplaceApp` with a manifest (widgets, optional `migrations_app` / `schema_patch_app`).
2. **Approval** – An admin approves the install. The platform calls `install_app(school, app, installed_by=..., config=..., run_schema_patches=True)`.
3. **Schema patch (if allowed)** – If the app manifest specifies a Django app label for migrations/schema patches, and the platform allows it (e.g. `MARKETPLACE_SCHEMA_PATCH_APPS`), migrations for that app are run in the current connection context (tenant schema in schema-per-tenant mode; single schema with RLS otherwise). This is done by `run_schema_patches_for_installation(installation)`.
4. **Register widgets** – The installation record stores `widget_config` from the app manifest. The portal uses `get_installed_widgets(school)` and only surfaces widgets for installations with `status=ACTIVE`.
5. **Audit** – Every install, uninstall, and suspend is recorded in `AppAuditLog` with `action`, `payload`, and `actor`.

## Data model

- **MarketplaceApp** – Listing (slug, manifest, publisher). Manifest can include `widgets`, `migrations_app`, `schema_patch_app`.
- **AppInstallation** – Per-school install: `school`, `app`, `status` (ACTIVE, UNINSTALLED, SUSPENDED), `config`, `widget_config`, `installed_by`.
- **AppAuditLog** – Immutable log: `installation`, `school`, `app`, `action` (install | uninstall | suspend), `payload`, `actor`.

## Services

- `install_app(school, app, *, installed_by=None, config=None, run_schema_patches=True)` – Creates or reactivates `AppInstallation`, optionally runs schema patches, logs install.
- `uninstall_app(school, app, *, uninstalled_by=None)` – Sets status to UNINSTALLED, logs uninstall.
- `suspend_app(school, app, *, suspended_by=None, reason="")` – Kill switch: sets status to SUSPENDED, logs suspend; widgets and capabilities are no longer served.

## Sandbox and CSP

Third-party app previews run in an **app sandbox**: an iframe with CSP and `sandbox` attribute to restrict script and origin. The developer portal links to the sandbox view; full policy is documented where the sandbox is rendered.

## Related

- Developer portal: `/developer-portal/` (Section 6)
- Marketplace models: `apps.marketplace.models`
- Install pipeline: `apps.marketplace.services`
