# RunMyCampus: Single-Tenant → Global Multi-Tenant Platform Audit Prompt Pack

**Purpose:** Use these prompts with Cursor/Codex to run a forensic, non-negotiable audit of the platform transition. The system started as a single-school management system for Gilead and is intended to become a global multi-tenant education platform (RunMyCampus) modeled after Shopify, Amazon, and Salesforce.

**How to use:** Run prompts **in order** (1 → 6, then Global Education, then Architecture-Truth). Save each output (e.g. `PLATFORM_TRANSITION_FORENSIC_REPORT.md`, `SUPERADMIN_VS_TENANT_BOUNDARY_REPORT.md`, etc.) and remediate before treating the transition as complete.

---

## CRITICAL ADVICE

The biggest mistake is thinking *"We added tenants"* while the code still thinks *"This is Gilead School."* These prompts force detection of:

- hidden single-school assumptions  
- weak tenant isolation  
- control-plane leaks  
- governance gaps  
- hardcoded workflows  
- UI duplication  
- platform illusions  

---

# PROMPT 1 — PLATFORM TRANSITION FORENSIC AUDIT

```
Review the entire repository to determine whether this codebase has truly transitioned from a single-school system to a multi-tenant global education platform.

The system originally served a single school (Gilead). It is now intended to be a global multi-tenant platform (RunMyCampus) modeled after Shopify, Amazon, and Salesforce.

I want you to inspect every file in the repository and determine:

1. Where the codebase still assumes a single school environment
2. Where tenant isolation may be incomplete
3. Where logic still assumes a default school or organization
4. Where data models still behave as if the platform serves only one institution
5. Where settings, policies, or behavior are global when they should be tenant-scoped
6. Where Gilead-specific assumptions remain embedded in the system

Inspect:

models  
views  
services  
forms  
templates  
static assets  
admin  
middleware  
settings  
tenancy logic  
migrations  
management commands  
registries  
policies  
blueprints  
workflows  
dashboards  
imports  
integrations  
analytics  
search  
navigation  
UI layouts  

For each issue discovered:

Explain why the code still reflects a single-school architecture.

Explain how it must be refactored to support a global multi-tenant platform operating across 195 countries.

Produce:

• single-tenant assumption inventory  
• multi-tenant readiness score  
• refactor priority list
```

---

# PROMPT 2 — SUPERADMIN VS TENANT BOUNDARY AUDIT

```
This is critical.

Shopify, Salesforce, and AWS succeed because control plane vs tenant plane are sacred boundaries.

Audit the entire codebase for the separation between:

CONTROL PLANE (Superadmin platform)
TENANT PLANE (Schools using the platform)

The control plane must operate independently of tenant logic.

Inspect:

superadmin dashboards  
manager.runmycampus.com/super  
admin backoffice  
tenant dashboards  
school-specific logic  
school configuration  
platform governance models  

Identify:

1. Any places where tenant code leaks into the control plane
2. Any places where the control plane directly manipulates tenant data incorrectly
3. Any places where a tenant could accidentally access platform-level capabilities
4. Any places where superadmin code behaves like tenant code
5. Any places where tenant UI and superadmin UI share layouts or components incorrectly
6. Any places where permissions rely on weak role checks instead of strong boundaries

The system must enforce these layers:

Layer 1 — Platform Control Plane (RunMyCampus)  
Layer 2 — Tenant Runtime Plane (schools)  
Layer 3 — User Experience Plane (teachers, parents, students)

Return:

• control-plane architecture review  
• tenant-plane architecture review  
• boundary violation inventory  
• recommended structural corrections
```

---

# PROMPT 3 — TENANT DATA ISOLATION AND SECURITY AUDIT

```
If this fails, the platform dies.

Inspect the repository to determine whether tenant data isolation is fully enforced.

The platform currently uses schema-per-tenant and may also use row-level protections.

Review:

database models  
query patterns  
ORM usage  
middleware  
search_path usage  
tenant detection logic  
API access  
background jobs  
caching  
analytics queries  

Identify:

1. queries that do not filter by tenant
2. services that assume a global dataset
3. analytics that mix tenant data
4. search systems that could leak cross-tenant data
5. background jobs that run without tenant context
6. migration or import paths that bypass tenant isolation
7. reporting tools that aggregate across tenants incorrectly

Explain:

• where isolation is safe  
• where isolation is fragile  
• where isolation is broken  

Produce:

tenant isolation risk map  
security refactor plan
```

---

# PROMPT 4 — PLATFORM CONFIGURATION VS HARDCODING AUDIT

```
A real platform never hardcodes behavior.

Review the entire codebase to identify where behavior is hardcoded instead of driven by:

policies  
blueprints  
registries  
workflow packs  
dashboard packs  
provider registries  
runtime configuration  

Inspect:

views  
services  
templates  
forms  
admin screens  
dashboards  
navigation  
analytics  
workflows  
reports  
imports  

Find:

hardcoded school types  
hardcoded education levels  
hardcoded grading systems  
hardcoded workflows  
hardcoded UI navigation  
hardcoded sidebar entries  
hardcoded dashboard widgets  
hardcoded provider integrations  
hardcoded country behavior  

For each one:

identify correct configuration layer:
registry  
blueprint  
policy  
runtime  
feature flag  
design system

Return:

hardcoding inventory  
configuration refactor map
```

---

# PROMPT 5 — SUPERADMIN PLATFORM GOVERNANCE AUDIT

```
Your superadmin layer must feel like AWS control plane.

Inspect the superadmin platform implementation.

Focus on:

manager.runmycampus.com/super  
platform governance models  
tenant provisioning  
tenant health  
tenant analytics  
feature flags  
policy governance  
blueprint marketplace  
app marketplace  
migration cloud  
observability systems  

Determine whether the platform actually supports:

tenant lifecycle management  
platform-wide feature toggles  
platform health monitoring  
global analytics  
migration tooling  
marketplace governance  
pack versioning  
regional configuration  

Identify missing control-plane capabilities needed for a platform operating across 195 countries.

Return:

superadmin maturity score  
missing governance capabilities  
control plane architecture recommendations
```

---

# PROMPT 6 — FINAL PLATFORM TRUTH AUDIT

```
This is the brutal truth prompt.

After inspecting the entire repository, determine whether RunMyCampus is currently:

A) a multi-tenant platform
B) a single-school system extended for multiple schools
C) a hybrid transitional architecture

Explain your reasoning using real code evidence.

Answer:

1. what parts already resemble a world-class platform
2. what parts still resemble a normal Django school system
3. what architectural contradictions exist
4. what platform pillars are incomplete
5. what must be rebuilt to reach true platform architecture

Return:

platform maturity rating (0–10)  
top architectural risks  
top platform strengths  
exact roadmap to reach Shopify/Salesforce/AWS-level platform architecture
```

---

# PROMPT 7 — GLOBAL EDUCATION COMPATIBILITY AUDIT

```
Because RunMyCampus is intended to operate in 195 countries, it must support:

different grading systems  
different academic calendars  
different attendance systems  
different regulatory compliance  
different language layouts  
different reporting formats  
different payment systems  

Audit the entire repository for global education compatibility.

Inspect:

grading and assessment logic  
academic year and term logic  
attendance and leave logic  
compliance and reporting logic  
localization and RTL  
report and document formats  
payment and currency logic  
registries and regional config  
blueprints and policies  

Identify:

1. Where the system assumes one grading system, calendar, or regulatory model
2. Where behavior is tied to a single country or region
3. Where reporting or documents are not localizable or configurable
4. Where payment or currency is hardcoded
5. Where registries or blueprints are incomplete for global use

Return:

global education compatibility inventory  
per-domain maturity (grading, calendar, attendance, compliance, reporting, payment, locale)  
refactor map to support 195 countries
```

---

# PROMPT 8 — ARCHITECTURE-TRUTH (RECONSTRUCT FROM CODE)

**Run this after the targeted audits (1–7).** It forces reconstruction of the real system from code, not from hopes, docs, or vibes.

```
Review the entire RunMyCampus repository and rebuild the true platform architecture from code only.

Context:
This system began as a single-school management system for one tenant (Gilead).
It is now intended to become a global multi-tenant education infrastructure platform modeled after Shopify, Salesforce, Amazon, and AWS.

Your task is to ignore marketing claims, high-level intentions, and optimistic assumptions unless they are proven in code.
Use the repository itself as the source of truth.

Inspect every relevant file in:
- apps
- config
- templates
- static
- frontend
- services
- sdk
- scripts
- docs
- tests
- migrations
- management commands
- middleware
- admin
- APIs
- integrations
- analytics
- observability
- marketplace
- migration tooling
- shell/layout/navigation code

I want you to reconstruct the actual architecture and answer these questions with code-based evidence:

PART 1 — SYSTEM IDENTITY
1. Is this codebase truly a multi-tenant platform, or is it still fundamentally a single-school system extended for multiple schools?
2. What parts of the code still reveal the original single-school/Gilead assumptions?
3. What parts genuinely behave like a governed platform?
4. What architectural contradictions exist between the intended platform model and the actual implementation?

PART 2 — TRUE ARCHITECTURE MAP
Reconstruct the real architecture from code, not theory.
Produce:
- app/module map
- model/domain map
- tenancy model map
- runtime/configuration map
- superadmin/control-plane map
- tenant-plane map
- portal/role-surface map
- workflow/dashboard/pack map
- marketplace/app-extension map
- migration/import map
- provider/integration map
- observability/analytics map
- reporting/document/search map

For each area:
- explain what exists
- explain how it works
- explain what it depends on
- explain what is incomplete
- explain what is duplicated or contradictory

PART 3 — CONTROL PLANE VS TENANT PLANE
Audit the separation between:
- RunMyCampus platform control plane
- internal admin/backoffice plane
- tenant runtime plane
- school user experience plane

Identify:
- shared layouts/components that should not be shared
- permission boundary leaks
- governance functions missing from superadmin
- tenant logic leaking into platform logic
- platform logic leaking into tenant surfaces
- places where the superadmin still behaves like a bigger school dashboard instead of a cloud control plane

PART 4 — TENANCY AND ISOLATION
Audit whether tenancy is truly enforced.
Inspect:
- schema-per-tenant behavior
- any row-level or fallback tenant assumptions
- middleware
- service layer
- queries
- jobs
- reports
- analytics
- imports
- search
- exports

Identify:
- code paths that may bypass tenant isolation
- global queries that should be tenant-scoped
- background jobs running without clear tenant context
- reporting/search/export risks
- mixed tenancy assumptions

PART 5 — CONFIGURATION VS HARDCODING
Find every category of behavior that is still hardcoded instead of flowing through:
- registries
- blueprints
- policy bundles
- workflow packs
- dashboard packs
- provider registry
- runtime
- entitlements/flags

Look for:
- country assumptions
- school-type assumptions
- grading assumptions
- currency/timezone/date assumptions
- navigation/sidebar hardcoding
- dashboard hardcoding
- workflow stage hardcoding
- provider hardcoding
- app visibility hardcoding
- template label hardcoding
- admin/superadmin assumptions hardcoding

For each item:
- classify severity
- explain why it breaks platform scaling
- specify where it belongs instead

PART 6 — PLATFORM LAYERS MATURITY
Assess the actual maturity of these platform layers:
- registries
- blueprint packs
- policy bundles
- workflow packs
- dashboard packs
- runtime
- provider registry
- marketplace
- migration cloud
- observability
- analytics
- search
- document lifecycle
- reporting/export
- metadata/custom fields
- localization/RTL/mobile/low-bandwidth
- developer ecosystem / SDK
- security / permissions / trust boundaries

For each layer:
- rate maturity from 0 to 10
- explain what is real
- explain what is partial
- explain what is hollow or only scaffolded
- explain what must be done next

PART 7 — FRONTEND / UX / SHELL ARCHITECTURE
Audit the visible product across:
- runmycampus.com
- manager.runmycampus.com/super/
- manager.runmycampus.com/admin
- tenant shells
- role shells
- sidebars
- page families
- component consistency
- design token or theme patterns
- mobile/low-bandwidth readiness

Identify:
- where the UI still feels like a school app instead of a platform
- where layouts are duplicated
- where sidebars are not governed
- where pages still look admin-ish or legacy
- where premium product quality is missing
- where the control plane fails to feel like infrastructure

PART 8 — MARKETPLACE / MIGRATION / BLANK SURFACES
Audit whether the following are productized or just scaffolded:
- blueprint marketplace
- policy application flows
- app catalog
- app installation
- migration cloud
- migration connectors
- bootstrap/seed commands
- empty states

Determine:
- which are blank because data is missing
- which are blank because the product surface is incomplete
- which require seeding
- which require governance completion
- which require activation flows
- which require product UX instead of docs/admin dependence

PART 9 — SECURITY / TRUST / COMPLIANCE
Audit:
- authentication
- authorization
- control-plane roles
- tenant roles
- support impersonation
- app scopes
- provider secrets
- export controls
- sensitive-field restrictions
- audit logging
- compliance enforcement

Identify:
- weak trust boundaries
- missing audit guarantees
- support/admin risks
- app/provider security risks
- enterprise-readiness blockers

PART 10 — CLEANUP / DELETION / SIMPLIFICATION
Identify:
- dead code
- duplicate helpers
- duplicate layouts
- obsolete docs
- TODOs
- NotImplementedError stubs
- broad exception anti-patterns
- stale migrations or compatibility hacks
- code that should be deleted instead of extended
- god-app decomposition candidates

PART 11 — FINAL TRUTH
Give a brutally honest final assessment.

Answer:
1. What is the system today, really?
   - true platform
   - transitional hybrid
   - single-school system stretched into multi-school
2. What parts already justify the platform ambition?
3. What parts are still pretending?
4. What are the top 25 issues that must be addressed for this codebase to become the Shopify/Salesforce/AWS of education?
5. What is the exact implementation order to get there without chaos?

Output format:
- Executive summary
- Reconstructed architecture map
- Maturity table by platform layer
- Single-tenant residue inventory
- Superadmin vs tenant boundary violations
- Hardcoding/configuration drift inventory
- Frontend/shell/sidebar/UI debt inventory
- Marketplace/migration/provider/productization findings
- Security/trust findings
- Cleanup/deletion map
- Top 25 must-fix actions
- Exact next-wave execution plan

Rules:
- Use code evidence, not wishful interpretation.
- If docs say a feature exists but code shows it is partial, say it is partial.
- If a surface exists but is empty because nothing is seeded, say so.
- If a layer looks like scaffolding rather than product, say so.
- If the platform still thinks like Gilead in hidden places, identify those places precisely.
- Be blunt, specific, and architecture-aware.
```

---

## RUN ORDER

| Step | Prompt | Output to save |
|------|--------|----------------|
| 1 | Platform Transition Forensic Audit | e.g. `PLATFORM_TRANSITION_FORENSIC_REPORT.md` |
| 2 | Superadmin vs Tenant Boundary Audit | e.g. `SUPERADMIN_VS_TENANT_BOUNDARY_REPORT.md` |
| 3 | Tenant Data Isolation and Security Audit | e.g. `TENANT_ISOLATION_SECURITY_REPORT.md` |
| 4 | Platform Configuration vs Hardcoding Audit | e.g. `HARDCODING_CONFIGURATION_REPORT.md` |
| 5 | Superadmin Platform Governance Audit | e.g. `SUPERADMIN_GOVERNANCE_REPORT.md` |
| 6 | Final Platform Truth Audit | e.g. `FINAL_PLATFORM_TRUTH_REPORT.md` |
| 7 | Global Education Compatibility Audit | e.g. `GLOBAL_EDUCATION_COMPATIBILITY_REPORT.md` |
| 8 | Architecture-Truth (reconstruct from code) | e.g. `ARCHITECTURE_TRUTH_REPORT.md` |

Run 8 after 1–7 so you get both targeted subsystem findings and one final “tell me the truth about the whole machine” pass.

---

## RELATIONSHIP TO EXISTING REMEDIATION

- **PLATFORM_AUDIT_REMEDIATION_BACKLOG.md** and **PLATFORM_TRANSITION_AUDIT_REPORT.md** record work already done (get_solo, Celery tenant context, Superadmin decorators, ORM/analytics isolation, sidebar/widget docs, governance docs).
- Re-running this prompt pack will surface any **remaining** single-tenant residue, boundary leaks, and gaps. Treat findings as non-negotiable; fix and re-audit until the transition is complete.
