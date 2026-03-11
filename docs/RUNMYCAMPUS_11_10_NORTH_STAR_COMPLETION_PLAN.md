# RunMyCampus 11/10 North-Star Completion Plan

This is the canonical implementation plan for the current platform-hardening and platform-productization workstream.

## Authoritative target

- Working repo: `beta/school-management-system`
- Goal: move RunMyCampus from transitional multi-tenant platform to 9.5+/10 across architecture, runtime, security, UX, onboarding, marketplace, packs, and control plane
- Rule: no deferred placeholders, no half-complete migrations, no permanent dual-path legacy ownership

## Active execution phases

### Phase 1. Hard freeze, ownership map, deletion rules
- Freeze new tenant-facing business logic in `siteconfig`
- Inventory `SiteSettings`, `get_solo()`, `except Exception`, `cursor.execute()`, `csrf_exempt`, `AllowAny`, `print()`, `gilead` residue, management commands, and outdated docs
- Assign each legacy config behavior to one bounded-context owner or delete it

### Phase 2. Security, hygiene, and trust hardening
- Remove client-facing AI secret exposure
- Review all public/exempt endpoints
- Reduce blanket exception handling in sensitive modules
- Audit non-migration raw SQL
- Remove runtime-visible Gilead residue
- Replace `print()` with structured logging and correct outdated documentation

### Phase 3. Make runtime the only legal tenant behavior engine
- Standardize runtime precedence
- Route tenant behavior through runtime resolvers
- Expand runtime inspection
- Enforce control-plane vs application-plane boundaries
- Add CI/lint gates against legacy regressions

### Phase 4. Complete the core toolsets
- Theme & Experience
- Feature Control
- Report Library
- Document Library
- Design Studio
- Live Previews
- Workflows
- AI and API usage
- System Configuration / SiteSettings

### Phase 5. Productization and market-gap closure
- Setup Studio as the mandatory onboarding spine
- Premium marketplace listing/install model
- First-party ecosystem seeding
- Distinct role homes and dashboards
- Stronger family/mobile and district control plane
- Proof-rich marketing front

### Phase 6. Verification, release gates, and re-audit
- Test gates
- Operational gates
- Codebase gates
- Re-score all platform areas to 9.5+/10
- Final benchmark delta report

## Operational sources of truth

The implementation is being driven alongside these generated and audited artifacts:

- `docs/generated/platform_inventory.md`
- `docs/generated/platform_inventory.json`
- `apps/siteconfig/domain_ownership.py`
- `docs/security/SITESETTINGS_INVENTORY.md`
- `docs/SITECONFIG_OWNERSHIP_MIGRATION.md`
- `docs/SITECONFIG_DECOMPOSITION_PLAN.md`
- `scripts/generate_platform_inventory.py`
- `scripts/lint_tenant_settings.py`
- `scripts/lint_csrf_exempt_usage.py`
- `scripts/lint_allow_any_usage.py`
- `scripts/lint_gilead_residue.py`

## Current execution note

This file is the canonical named plan. Progress is implemented directly in code plus the inventories and audit artifacts listed above.
