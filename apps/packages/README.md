# apps/packages

> The pack engine: validate, preview-diff, apply, rollback, and promote
> versioned bundles of platform configuration for a tenant or the platform.

**Tenancy:** SHARED (public schema; installs are scoped by an explicit `school` reference)
**Scale:** 5 models · 8 migrations · 4 test modules · ~3.3k LOC

## What this app owns

Packages is how configuration ships. A *package* is a versioned bundle —
blueprint, workflow, dashboard, policy, theme, document pack, or experience pack
— that can be applied to a tenant or to the platform, previewed before it lands,
and rolled back after. This app owns the engine (`engine.py`: `validate_package`,
`preview_diff`, `apply_package`, `rollback`, `promote_package`), the persistence
for what is installed where, and the audit trail of every apply and rollback.

It is deliberately a **generic lifecycle other apps borrow rather than
reimplement**. `apps.brand_experience` routes its entire ExperienceTemplate
marketplace through these calls; `tenant_pack_install.py` records DocumentPack /
ExperiencePack usage as `InstalledPackage` rows purely so tenants get rollback
parity with everything else. If a domain grows its own install/rollback code, the
bug is in that domain.

The engine's most important contract is its **apply outcome**. `apply_package`
returns an explicit `apply_state`: `not_attempted` (preview or compatibility
failed before any DB work), `committed` (the single `transaction.atomic` block
succeeded), or `rolled_back` (a failure inside the block; ORM writes *and*
metadata registration inside it reverted). The ledger semantics are documented in
`docs/package_engine_ledger.md`; the canonical package format lives in
`docs/architecture/PACKAGE_FORMAT.md`.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `InstalledPackage` | `packages_installedpackage` | What is installed where. Carries `package_id`, `package_type`, `version`, `scope`, and a **nullable** `school` FK — null means a platform/global install. |
| `PackageVersion` | `packages_packageversion` | Known version metadata: `dependencies`, `compatibility` (platform/region constraints), and `payload_sections`. |
| `PackageChangeLog` | `packages_packagechangelog` | Audit trail for apply/rollback: actor, package, tenant, mode (sandbox/test/production), token, `reconciliation_status`. |
| `ExperiencePack` | `packages_experiencepack` | Theme + layout + dashboard visual + communication style as one packageable unit. Runtime-only theme resolution; supports compare/rollback. |
| `DocumentPack` | `packages_documentpack` | Document library pack with lifecycle states (draft → review → approved → archived) and a `retention_rule` for auto-archival/expiry. |

All five declared models are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `engine` | `PackageEngine` — the lifecycle. Everything else delegates here. |
| Module | `tenant_pack_install` | `record_document_pack_usage` / experience-pack equivalent; idempotent per school + code + version |
| Module | `first_party_package_payloads` | `FIRST_PARTY_APP_DEFINITIONS` — 27 legacy first-party package IDs |
| Mgmt command | `seed_first_party_apps` | Seeds the 27 first-party IDs |
| Mgmt command | `seed_marketplace_catalog_packages` | Seeds the marketplace catalog (distinct set — see below) |
| Mgmt command | `seed_phase9_first_party_packages` | Phase 9 first-party seed |
| Mgmt command | `seed_ultra_high_end_experience_packs` | Experience-pack seed |

No `urls.py`, no views, and no celery tasks — this app is a library plus seeds.
Its surfaces are reached through the callers that embed the engine (the
brand_experience marketplace, `platform_runtime.views_administration.pack_*`).

**Two seed sets, not one:** `first_party_package_payloads` builds payloads for
the **27 legacy `seed_first_party_apps` package IDs**, which satisfy the
`MARKETPLACE_SEED_TARGETS` first-party-apps inventory minimums. These are
*distinct* from the marketplace catalog slugs (73 rows via
`seed_marketplace_catalog_packages`). Conflating them is easy and wrong.

## Before you change this

- **`PackageChangeLog.school_id` is a raw `UUIDField`, not a ForeignKey.** There
  is no referential integrity, no cascade, and no `select_related` — deleting a
  school leaves its changelog rows behind (arguably correct for an audit trail,
  but know that it is the actual behavior). Do not assume `changelog.school`
  exists; it does not.
- **`InstalledPackage.school` is nullable and null means *global*.** A queryset
  that forgets to filter by school returns other tenants' installs *and* platform
  installs. `null=True` here is load-bearing semantics, not laxity — never
  "tighten" it to non-null without answering what a platform-scope install becomes.
- **`apply_state` is the return contract — read it, do not infer from exceptions.**
  A `rolled_back` apply may still write a `PackageChangeLog` row with
  `reconciliation_status=failed` in a *separate* atomic block, precisely so the
  failure is visible after the main block reverts. So "a changelog row exists"
  does **not** mean "the package applied". Check `apply_state`.
- **The engine's exception tuples are typed on purpose.**
  `_PACKAGE_APPLY_FAILURE_ERRORS` and `_CHANGELOG_SECONDARY_ERRORS` are explicit
  so that a genuine bug is not swallowed as "apply failed". Do not widen either to
  a bare `except Exception` — that is the failure mode they were written against.
- **`tenant_pack_install` must stay idempotent** (per school + pack code +
  version). It exists so tenant pack usage gets rollback parity; a
  double-recorded install breaks the rollback lineage.
- **Reconciliation status is part of the contract**, set on both
  `InstalledPackage` and `PackageChangeLog` (`reconciled`, `rolled_back`,
  `promoted`). For lineage visibility call
  `apps.metadata.services.get_package_lineage_registry(package_id=...)` rather
  than reassembling history from raw rows.
- If you change the package format, `docs/architecture/PACKAGE_FORMAT.md` is
  canonical and both `validate_package` and the seed payload builders read against
  it. Changing one without the others produces packages that seed but will not
  validate.
