# Empty-State Audit (Wave 6.2)

**Purpose:** Each catalog/list surface has a clear empty state: why it is empty and what to do (seed, request access, or link to setup).

## Control-plane surfaces

| Surface | Empty state | Action |
|---------|-------------|--------|
| Blueprint marketplace | "No blueprint packs" | Run `bootstrap_platform_catalog` or seed_blueprint_policy_packs; link to docs. |
| App catalog | "No apps listed" | Seed marketplace apps; link to manager marketplace. |
| Workflow/Dashboard packs | "No packs" | Bootstrap workflow/dashboard packs. |
| Provider registry | "No providers" | seed_provider_registry. |
| Migration profiles | "No connectors" | seed_migration_profiles. |
| Tenant health list | "No tenants" | Provision first school via /super/create/. |

## Tenant surfaces

| Surface | Empty state | Action |
|---------|-------------|--------|
| Students / People / Invoices | "No records" | Add first record; link to Add button or onboarding. |
| Get blueprints | "No blueprints applied" | Link to manager blueprint marketplace or request. |
| Document library | "No documents" | Upload or link to upload. |

## Requirements

1. **Why empty:** Message or copy that explains the state (e.g. "No blueprint packs have been seeded yet").
2. **What to do:** Primary action (Run bootstrap, Add X, Request access, Go to manager).
3. **Avoid:** Relying only on "Go to admin" or "Read the docs" without a direct product action where possible.

## Status

- Control-plane: Bootstrap and seed commands documented; empty states in templates should point to bootstrap or provisioning.
- Tenant: List empty states use partials (empty_state) where refactored; remaining lists to align per ux_rules_audit_26_5.md.
