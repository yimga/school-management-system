# Documentation governance plan

**Goal:** Reduce root-level doc sprawl, single source of truth, easier onboarding.

**Rules:**

1. **Root:** Keep only README.md, CONTRIBUTING (if any), and a minimal root set. No product/ops runbooks at root.
2. **Archive:** Move obsolete or historical docs to `docs/archive/`. Name with date or version if needed.
3. **Living docs by domain:**
   - `docs/platform/` — platform architecture, runtime, multitenancy, resolver.
   - `docs/ops/` — deployment, env vars, health, runbooks.
   - `docs/marketplace/` — marketplace, blueprints, packs, policies.
   - `docs/migration/` — data migration, tenant migration, cutover.
   - `docs/ui/` — UX standards, page archetypes, design tokens.
   - `docs/security/` — CSRF audit, raw SQL audit, subprocess audit, secret handling.
4. **No duplicate “how to run” or “how to deploy”:** One canonical place per topic; link from README.
5. **Stale check:** Periodically review docs in these folders; archive or update.

**Immediate actions:** Move root-level markdown files (except README and a short list) into the structure above; add this plan to `docs/` and link from README.
