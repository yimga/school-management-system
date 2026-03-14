# RunMyCampus Enterprise Architecture Audit and Cursor Remediation Plan

**Single execution source of truth:** All remediation work is driven by [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Do not create overlapping plan files; map all work back to that ledger.

---

## Scope and method

This is a deep static audit of the latest uploaded zip. It evaluates architecture, multitenancy, security, extensibility, and platform readiness against the bar implied by multi-tenant SaaS leaders and current EdTech competitors.

This is **not** a live-runtime or infrastructure penetration test. It does not prove production compliance with FERPA, HIPAA, SOC 2, or real-world scale. Those require environment, controls, ops evidence, and live testing beyond repository inspection.

## Executive verdict

RunMyCampus has clearly crossed from "single-school product" into a **real multi-tenant platform in transition**.

But it is **not yet enterprise-grade at the level of Shopify / Salesforce / AWS patterns**, and it is **not yet competitively polished enough** to claim superiority over mature incumbents like Infinite Campus, Blackbaud, or PowerSchool.

### Current platform score

**7.3 / 10**

### Current strongest areas
- Platform ambition and breadth
- Runtime and metadata direction
- Marketplace / pack / blueprint direction
- Global registry and localization direction
- Setup/launch and Studio OS potential

### Current weakest areas
- `siteconfig` / `SiteSettings` gravity
- Security hardening and public surface review
- Raw SQL and exception discipline
- Fragmented operator tooling ("studios")
- Under-productized package engine / marketplace trust model
- Residual Gilead naming and legacy defaults
- Docs/plan sprawl and truth mismatch

## Hard findings from the latest zip

Approximate repo-wide signals from the latest static sweep:
- 1751 Python files
- 456 templates
- 787 markdown/docs files
- 585 migrations
- 153 management commands
- 682 `except Exception`
- 92 `get_solo()`
- 368 `SiteSettings` references
- 40 `csrf_exempt`
- 16 `AllowAny`
- 331 `cursor.execute()`
- 25 `subprocess.` usages
- 392 `print()` matches
- 404 `gilead` references
- 19 `GEMINI_API_KEY` references

Largest files remain structurally risky, including `apps/siteconfig/models.py`, `apps/schools/marketing_views.py`, `apps/accounts/views.py`, `apps/schools/super_views.py`, `apps/siteconfig/admin.py`, `apps/portal/views.py`, `apps/evals/views.py`, `apps/finance/views.py`, and `apps/api/views_v1.py`.

---

## Audit findings by dimension

### 1. Multi-tenancy and isolation

**Verdict: promising, not yet "unbreakable."**

The codebase now clearly models tenant-aware concepts and has meaningful runtime/platform structure. But the continued presence of heavy `SiteSettings` usage, singleton patterns, and broad app-local behavior strongly suggests that tenant behavior is still too easy to resolve outside the runtime kernel.

#### What is good
- Multi-tenant intent is real and no longer cosmetic
- Runtime direction is present
- Blueprint/policy/pack concepts exist
- Registry and pack concepts can support tenant-specific variation

#### Critical architecture risks
- `SiteSettings` still acts too often like a behavioral truth source
- Direct global fallback logic still competes with runtime resolution
- Raw SQL volume raises tenant-filtering and leakage risk
- Noisy-neighbor protections and explicit workload isolation are not proven from repo alone

#### Required standard
AWS guidance is explicit that tenant isolation is foundational and that different isolation models trade off cost and risk; this choice must be deliberate, not accidental.

#### Remediation
- Make runtime the **only** legal tenant-behavior engine
- Force every tenant-facing path through runtime resolvers
- Audit every raw SQL call for tenant scoping
- Add tenant-isolation tests for reads, writes, caches, jobs, and background processing
- Add per-tenant rate limits and workload controls for high-cost jobs

### 2. Extensibility and API-first design

**Verdict: strategically strong direction, still immature operationally.**

The platform is moving toward an ecosystem model with apps, packs, blueprints, workflows, dashboards, and policies. That is the right shape.

#### What is good
- Marketplace/app catalog concepts are present
- Package-driven thinking is real
- API center/integration direction exists
- Platform wants a locked core with extensibility at the edges

#### Critical architecture risks
- Marketplace trust model is not yet mature enough
- Package engine still needs dependency checks, staged rollout, and rollback reconciliation
- Public API hardening is not yet strong enough
- API governance and compatibility signaling are not yet platform-grade

#### Required standard
Shopify's extensibility model revolves around structured custom data through metafields and metaobjects, with definitions, validation, and use across admin, API, and storefront. That is the benchmark pattern for "locked core, extensible edge."

PowerSchool's current marketplace language emphasizes secure companion apps, internal APIs, SSO, certification, and ecosystem trust.

#### Remediation
- Build a stronger package engine: dependency graph, impact preview, sandbox apply, staged rollout, reconciliation
- Turn API Center into a real integration governance console
- Add versioned API contracts and webhook contracts
- Expose app scopes, permissions, and trust markers in marketplace listings
- Add sandbox install and rollback expectations to every app/pack listing

### 3. Scalability and resilience

**Verdict: architecture points in the right direction, but operational resilience is not yet demonstrated.**

#### What is good
- Platform decomposition has started
- Shared platform concepts exist
- The product is moving toward layered platform services instead of one-school logic

#### Critical architecture risks
- Giant files imply too much orchestration and decision-making is still concentrated in view/model layers
- High raw SQL count suggests hidden coupling and brittle performance paths
- Heavy management-command count suggests some operations may still rely on scripts instead of governed services
- Async and event-driven rigor are not yet consistently visible enough to trust large-scale workloads

#### Required standard
To resemble AWS-grade resilience, core services must be stateless where possible, expensive work must be asynchronous, and high-cost operations need clear retry, replay, and visibility paths. AWS's own multi-tenant guidance frames these tradeoffs as architectural, not cosmetic.

#### Remediation
- Build explicit orchestration for migrations, pack rollout, heavy reports, and workflow activations
- Add queue-first patterns for long-running operations
- Add tracing for runtime resolution, workflow execution, package apply, migration runs, report generation
- Set performance budgets for role homes, dashboards, and report generation
- Add silent-degradation alerts and platform/tenant health dashboards

### 4. Security and EdTech compliance posture

**Verdict: not yet enterprise-safe enough.**

This repo does not prove FERPA/HIPAA/SOC2 readiness. It shows **some useful building blocks**, but also enough unresolved risk that no serious compliance claim should be made from code alone.

#### What is good
- Role-aware platform intent exists
- Compliance-related docs and domains exist
- Audit concepts exist

#### Critical architecture risks
- `csrf_exempt` and `AllowAny` surface is still too broad
- Provider-secret handling is still too close to client-facing paths
- Broad exception catches reduce observability in security-sensitive paths
- Raw SQL and subprocess usage need structured governance
- Trust center and support impersonation governance are not complete enough

#### Competitor/security benchmark
Blackbaud's current messaging emphasizes role-based access, integrated data, SSO, and standards support such as OneRoster and LTI plus externally validated privacy/security claims.

#### Remediation
- Eliminate provider secrets from templates and client JS entirely
- Build public/exempt endpoint ledger and review every item
- Replace broad exception catches with typed exceptions and structured logs
- Build support/impersonation audit surfaces
- Add trust center surfaces for audit logs, integration scopes, metadata changes, and backup/export controls
- Validate encryption-at-rest/in-transit, secrets management, and audit controls in infrastructure separately from repo

### 5. Interoperability standards

**Verdict: promising but not yet a competitive strength.**

The codebase has interop direction and references, but this is still not a platform moat.

#### Required standard
Blackbaud publicly highlights built-in OneRoster and LTI support. That is the minimum expectation for enterprise-grade school software.

#### Remediation
- Build an interop validation workbench
- Add explicit support maturity matrix for OneRoster, LTI, SAML/SSO, and any Ed-Fi/CEDS aspirations
- Connect interop setup to migration and integration governance
- Add conformance tests and import/export validation tooling

---

## Competitive position summary

### Where incumbents still beat RunMyCampus today
- **Infinite Campus:** district-scale breadth and 1,500+ tool messaging, all-in-one operational story
- **Blackbaud:** private-school polish, 360° student view, integrated SIS/LMS, one-login family/staff/admin experience
- **PowerSchool:** marketplace trust, internal-API story, certification, SSO, companion apps
- **Yadiko / Smart School Manager:** practical convenience messaging around parents, mobile, fees, school website, payroll, and multi-branch operations in their markets

### Where RunMyCampus can beat them
- Faster, smarter setup and migration
- Runtime/metadata-driven flexibility
- Blueprint / workflow / dashboard / policy pack ecosystem
- More elegant and lower-click operator UX
- AI-assisted platform operations and self-improvement
- Stronger global registry model and localization strategy

---

## Cursor / Codex embedded remediation instructions

### Mission
Take the latest codebase from **7.3/10** to **9.5+/10** by addressing the structural issues in the correct order.

### Rule
Do not add new platform breadth before closing the architecture and trust gaps below.

### Phase 1 — red-alert hardening
1. Build `site_settings_usage_inventory.md` and classify every `SiteSettings` usage.
2. Remove all provider-secret exposure from templates/client code.
3. Build `public_endpoint_audit.md` for all `csrf_exempt` and `AllowAny` paths.
4. Build `raw_sql_audit.md` for every `cursor.execute()`.
5. Replace broad `except Exception` in the most sensitive apps first:
   - `apps/api`
   - `apps/schools`
   - `apps/accounts`
   - `apps/finance`
   - `apps/siteconfig`
6. Build `gilead_residue_inventory.md` and purge all UI/default-facing Gilead references.

### Phase 2 — architecture correction
1. Freeze new tenant-facing logic in `siteconfig`.
2. Reassign `siteconfig` ownership into:
   - `brand_experience`
   - `runtime_blueprints`
   - `plans_entitlements`
   - `global_registries`
   - `integrations_marketplace`
   - `policies_rules`
   - `metadata`
   - `packages`
   - `setup_studio`
3. Delete migrated legacy paths instead of keeping permanent shims.
4. Make runtime the only legal source of tenant-facing effective behavior.
5. Add runtime contract tests and a runtime inspector UI.

### Phase 3 — Studio OS rearchitecture
Replace fragmented tools with one shared shell and five work modes:
- Experience Studio
- Automation Studio
- Output Studio
- Launch Studio
- Control Studio

For Studio OS, implement shared systems:
- unified preview engine
- unified publish / rollback engine
- unified activity / audit feed
- unified command/search layer
- unified recommendation engine
- role/device preview switcher

### Phase 4 — package and marketplace productization
1. Deepen package engine with:
   - dependency graph validation
   - compatibility checks
   - impact preview
   - sandbox apply
   - staged rollout
   - environment promotion
   - rollback reconciliation
2. Upgrade marketplace listings to include:
   - screenshots/previews
   - trust markers
   - region/plan compatibility
   - scope/permission visibility
   - sandbox install
   - rollback expectations
3. Seed ecosystem with first-party apps and packs:
   - 25+ apps
   - 25+ blueprint packs
   - 30+ workflow packs
   - 20+ dashboard packs
   - 15+ policy bundles
   - theme/experience packs
   - migration packs

### Phase 5 — low-click UX and role-home engine
1. Build role-native homes for:
   - principal
   - teacher
   - parent
   - student
   - admissions
   - finance
   - district/group
   - support/implementation
   - platform ops
2. Replace generic quick actions with contextual actions:
   - role-aware
   - state-aware
   - urgency-aware
3. Enforce page archetypes:
   - Role Home
   - Setup Studio
   - Decision Console
   - Operational Workbench
   - Catalog / Marketplace
   - Record Detail

### Phase 6 — AI and integration platform
1. Build backend AI gateway.
2. Move all AI features behind permissioned backend services.
3. Use AI only where it reduces labor:
   - setup recommendations
   - workflow generation
   - migration mapping
   - policy explanation
   - semantic retrieval
   - support triage
4. Turn API Center into a real integration governance console.
5. Add API/runtime/package/event contract tests.

### Phase 7 — docs truth and hygiene
1. Audit docs folder and map every roadmap item to:
   - DONE
   - PARTIAL
   - NOT DONE
   - DEPRECATED / REPLACED
   - BLOCKED
2. Remove contradictory "all complete" language.
3. Reduce `print()` calls and replace with structured logging.
4. Inventory/prune management commands.
5. Clean repo/docs root clutter.

---

## Final success gates
Do not claim enterprise-ready / north-star / 9.5+ until all are true:
- `siteconfig` materially decomposed
- `SiteSettings` no longer acts as tenant-behavior truth
- runtime is the only legal behavior engine
- provider secrets never reach browser-facing code
- public/exempt endpoint audit complete
- raw SQL audit complete
- broad exception swallowing materially reduced
- Gilead residue removed from live/default-facing surfaces
- Studio OS replaces fragmented tool pages
- package engine is production-grade
- marketplace/packs are deeply productized
- docs truth audit no longer exposes contradictions
- marketing front visually proves platform seriousness

## Final note
The path to beating incumbents is not more feature sprawl.
It is:
- stronger architecture
- stronger trust
- better setup
- better migration
- better UX
- better ecosystem productization

That is the route from "ambitious platform" to "credible enterprise contender."
