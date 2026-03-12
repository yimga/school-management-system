# RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md
The one canonical execution ledger for taking RunMyCampus to north-star platform status
Rule of use
This file replaces parallel plan files.

Do not create overlapping strategy docs that drift from this one.

Every major implementation task, audit, cleanup, migration, or platform-hardening effort must map back to this file.

Every item must be marked as:

DONE
PARTIAL
NOT DONE
DEPRECATED / REPLACED
BLOCKED
No fake completion language. No vague “in progress” without concrete next action. No claiming 9.5/10 or 11/10 until the scoring gates at the end are satisfied.

0. Truth statement
RunMyCampus is no longer a single-school Gilead application.

RunMyCampus is now a real multi-tenant platform in transition.

That transition is visible in:

runtime direction
metadata direction
marketplace and package direction
blueprints / policies / workflow packs / dashboard packs
setup studio direction
global registries direction
role-home and control-plane direction
But the platform is not yet complete.

It is currently strongest in architectural ambition and weakest in:

siteconfig / SiteSettings gravity
settings-to-runtime migration completeness
security hardening
package engine maturity
full Studio OS productization
marketplace trust/product depth
Gilead residue removal
visual authority of the marketing front
1. Current score and target
Current score
Overall platform score: 7.3/10
Required score
Minimum acceptable delivery score: 9.5/10
North-star excellence target: 11/10
Meaning
RunMyCampus is currently:

serious
broad
strategically strong
architecturally promising
RunMyCampus is not yet:

fully hardened
fully simplified
fully runtime-governed
fully metadata-governed
fully low-click
fully premium across all surfaces
2. Non-negotiable blocker list
2.1 siteconfig / SiteSettings overhaul
Status: PARTIAL

Problem
too much tenant behavior still depends on SiteSettings
too many settings-like concerns remain in one mega-domain
config still acts as behavior truth too often
old and new ownership patterns still coexist
Required fix
freeze new tenant-facing logic in siteconfig
inventory every SiteSettings usage
classify each usage:
platform default only
brand/experience
runtime/blueprint
policy/rules
plans/entitlements
registries/localization
integrations/marketplace
metadata governance
delete/deprecate
move real ownership out of siteconfig
shrink SiteSettings to platform-safe defaults only
prohibit direct singleton/global tenant-behavior reads in new code
Completion criteria
tenant-facing behavior no longer depends on giant singleton config
all config domains have bounded consoles
migrated legacy paths are deleted, not just tolerated
2.2 Gilead residue purge
Status: PARTIAL

Problem
Gilead references still exist in:

code
docs
seeded defaults
theme/style/report artifacts
headers / labels
historical migrations
Required fix
search all gilead / Gilead references
classify each hit:
historical migration only
docs/archive only
runtime/config risk
UI/branding risk
remove all platform-visible/default-facing Gilead naming
reseed neutral / RunMyCampus-native defaults
Completion criteria
no runtime or UI-facing Gilead references remain
historical references are isolated to archive/migration-only contexts
2.3 AI/provider secret hardening
Status: PARTIAL / HIGH RISK

Problem
provider secret references still exist too close to template/client surfaces
AI integration is not yet guaranteed to be backend-only and governed
Required fix
no provider secrets in templates
no provider secrets in client JS
backend-only AI gateway
capability flags to UI, not secrets
rotate potentially exposed keys
audit every AI/copilot/template/JS path
Completion criteria
zero provider secret reaches browser-facing code
all AI requests flow through internal AI gateway
all AI actions are permissioned and auditable
2.4 Security hardening
Status: PARTIAL

Problem
public and exempt endpoint surface still too broad
raw SQL count still high
broad exception swallowing still too high
trust tooling is still incomplete
Required fix
review every csrf_exempt
review every AllowAny
audit raw SQL
reduce broad except Exception
strengthen auth, signature validation, replay protection, rate limiting, audit logging
Completion criteria
every public/exempt endpoint is justified and defended
raw SQL is classified and wrapped/reduced
critical paths do not hide unexpected failures behind blanket catches
3. Architecture law
3.1 Bounded contexts are real, not symbolic
Status: PARTIAL

Required bounded contexts
Identity & Access
People & Relationships
Admissions
Academics
Finance
Communications
Runtime & Metadata
Marketplace
Migration Cloud
Analytics & Intelligence
Control Plane
Brand & Experience
Plans & Entitlements
Global Registries & Localization
Studio OS
Required fix
move real ownership into the correct app/domain
delete legacy paths after migration
enforce import/dependency boundaries in CI
document source-of-truth ownership per domain
Completion criteria
bounded contexts are operationally real
old mega-domains are shrinking, not coexisting indefinitely
3.2 Runtime is the law
Status: PARTIAL

Required fix
all tenant-facing behavior resolves through runtime
standardize precedence:
platform default
registry/regional default
blueprint default
policy bundle
entitlement constraint
tenant override
sandbox/staged override
add runtime contract tests
add runtime inspector UI
eliminate direct global fallback logic in tenant paths
Completion criteria
runtime is the only legal tenant-behavior engine
precedence is explicit, tested, and observable
3.3 Metadata is first-class
Status: PARTIAL

Required fix
Complete metadata catalog coverage for:

entities
fields
relationships
layouts
dashboards
workflows
APIs
reports
templates
packs
glossary
governance metadata
Required lineage
For any important object/field, the platform must answer:

what workflows use this?
what dashboards use this?
what reports use this?
what APIs expose this?
what templates render this?
what packs introduced this?
what breaks if it changes?
Completion criteria
metadata is searchable, governed, previewable, diffable, auditable, and package-aware
4. Studio OS blueprint
4.1 Replace fragmented tools with one operating shell
Status: NOT DONE

Current fragmented tools to absorb
customizer
theme colors
feature control panel
report library
document library
design studio
workflow hub
setup simulator fragments
site settings / system config sprawl
New model
Build RunMyCampus Studio OS with five work modes:

Experience Studio
Automation Studio
Output Studio
Launch Studio
Control Studio
All inside one shared shell.

4.2 Shared Studio OS shell
Status: NOT DONE

Shared shell must provide
global search
command palette
unified left rail
unified preview engine
unified publish / rollback engine
unified activity / audit feed
unified recommendation layer
unified role/device preview switcher
unified design system
Completion criteria
users no longer bounce between disconnected admin tools to complete one goal
4.3 Experience Studio
Status: NOT DONE

Purpose
Shape:

school branding
theme tokens
shell layouts
parent/teacher/student/admin experiences
dashboard visuals
public-site visuals
communication style
Must absorb
customizer
theme colors
palette studio
branding pages
experience preview surfaces
Must support
ExperiencePack
role/device preview
compare
publish / rollback
website import
AI recommendations
neutral reseeded themes
Completion criteria
theming/experience is runtime-governed, packageable, previewable, publishable, rollbackable
4.4 Automation Studio
Status: NOT DONE

Purpose
Design and govern workflows and automations.

Must absorb
workflow hub
workflow preview fragments
approval/workflow admin fragments
Must support
visual builder
natural-language workflow generation
simulation engine
conflict detection
staged activation
replay / rollback
workflow health analytics
Completion criteria
workflows are easy to create, easy to understand, safe to activate, and easy to audit
4.5 Output Studio
Status: NOT DONE

Purpose
Own:

report packs
document packs
report templates
certificates
IDs
invoices
forms
policy outputs
district/compliance outputs
Must absorb
report library
document library
document rendering logic
report-card builder
output-related template surfaces
Must support
sample-data preview
brand inheritance
lifecycle/retention settings
signature integration
dependency graph
publish / rollback
ReportPack
DocumentPack
Completion criteria
outputs are governed, branded, package-driven, previewable, and lifecycle-aware
4.6 Launch Studio
Status: PARTIAL

Purpose
Take a school from signup to go-live in minimal clicks.

Must support
create school
choose plan
recommend blueprint
import branding
choose starter stack
choose migration path
preview by role
launch checklist
setup health score
launch confidence summary
Completion criteria
onboarding is guided, visual, role-aware, and confidence-building
4.7 Control Studio
Status: NOT DONE

Purpose
Govern:

runtime
capabilities
entitlements
policies
integrations
packs
registries
metadata governance
audit surfaces
Must absorb
feature control panel
plan/capability fragments
runtime/blueprint config fragments
integration governance fragments
system config sprawl
Must support
diff current vs proposed
why enabled / source tracing
blast radius / impact summary
rollback
staged rollout
AI cleanup suggestions
Completion criteria
system governance becomes low-click, explainable, and safe
5. Toolset overhaul ledger
5.1 Theme & Experience
Status: PARTIAL Score: 6.9/10

Required fix
move ownership into brand_experience
create ExperiencePack
unify theme/layout/portal/dashboard visual system
add role/device preview everywhere
add compare/publish/rollback
purge Gilead theme/style defaults
Target
11/10 experience platform, not a settings page with colors

5.2 Feature Control
Status: PARTIAL Score: 6.5/10

Required fix
replace long-lived toggles with capability management
capability registry with owner/expiry/source/scope
connect to runtime, entitlements, packs, rollout policy
show “why enabled?” in runtime inspector
Target
11/10 capability governance, not toggle chaos

5.3 Report Library
Status: PARTIAL Score: 7.1/10

Required fix
convert into report platform
add ReportPack
sample-data preview
policy/registry compatibility
style inheritance/versioning
report dependency graph
Target
11/10 report platform, not passive report list

5.4 Document Library
Status: PARTIAL Score: 6.9/10

Required fix
convert into Document & Compliance Content Platform
document lifecycle states
retention/archive policies
role-aware access
signature workflows
search/indexing
document packs
Target
11/10 content operating system, not file manager

5.5 Design Studio
Status: PARTIAL Score: 6.8/10

Required fix
Split into:

Document Design Studio
Experience Design Studio
Add:

layout builder
block/section system
responsive preview
versioning
inheritance
publish / rollback
Target
11/10 creative-operational design system

5.6 Live Previews
Status: PARTIAL Score: 7.4/10

Required fix
standardize previews for:
themes
blueprints
policies
dashboard packs
workflow packs
migration mapping
outputs
setup state
before/after
role/device switcher
impact summary
dependency warnings
Target
11/10 preview platform, not scattered preview islands

5.7 Workflows
Status: PARTIAL Score: 7.3/10

Required fix
simulation engine
visual builder
AI workflow generation
dependency graph
conflict detection
staged activation
replay/rollback
health analytics
Target
11/10 automation OS

5.8 AI and API usage
Status: PARTIAL Score: 6.4/10

Required fix
backend AI gateway
no provider secrets in browser
AI permissions and audit
AI for setup/workflow/migration/policy/search/support
API Center becomes integration governance console
contract testing across API/runtime/packages/events
Target
11/10 AI operating layer + API governance layer

5.9 System Configuration / SiteSettings
Status: PARTIAL Score: 5.0/10

Required fix
total decomposition into bounded consoles
reclassify every settings field and usage
move tenant behavior out of SiteSettings
add preview/diff/rollback and impact summaries
remove Gilead defaults from settings-driven surfaces
Target
11/10 elegant control plane, not settings landfill

6. App-by-app execution ledger
6.1 siteconfig
Status: PARTIAL Current: 5.0/10 Target: 10+/10

Must do
freeze expansion
inventory all settings usage
migrate ownership out
delete legacy behavior paths
reduce raw SQL
reduce broad exceptions
remove Gilead residue
replace giant admin surfaces with bounded consoles
6.2 platform_runtime
Status: PARTIAL Current: 8.1/10 Target: 10+/10

Must do
enforce runtime everywhere
add contract tests
add runtime tracing
add runtime inspector
eliminate settings/fallback bypasses
6.3 metadata
Status: PARTIAL Current: 7.5/10 Target: 10+/10

Must do
complete metadata catalog
add lineage
add glossary completeness
add pack provenance
add governance lifecycle and search
6.4 packages
Status: PARTIAL Current: 6.8/10 Target: 10+/10

Must do
dependency validation
compatibility checks
impact preview
sandbox apply
staged rollout
environment promotion
rollback reconciliation
failure handling
6.5 setup_studio
Status: PARTIAL Current: 6.5/10 Target: 10+/10

Must do
full Launch Studio flow
setup health score
recommendation engine
role preview
website import
starter stack selection
migration path chooser
6.6 brand_experience
Status: PARTIAL Current: 6.8/10 Target: 10+/10

Must do
absorb real ownership from siteconfig
add ExperiencePack
add previews, compare, rollback
add responsive and role previews
purge Gilead theme defaults
6.7 runtime_blueprints
Status: PARTIAL Current: 6.8/10 Target: 10+/10

Must do
make real owner of blueprint behavior
connect with setup, registries, plans, policies, runtime
support preview, compare, sandbox, versioning
6.8 plans_entitlements
Status: PARTIAL Current: 6.7/10 Target: 10+/10

Must do
hard entitlement registry
explicit runtime consumption
why-enabled UI
marketplace/install compatibility
upgrade/downgrade clarity
6.9 global_registries
Status: PARTIAL Current: 7.6/10 Target: 10+/10

Must do
make central to:
setup recommendations
report packs
policy compatibility
migration mapping
localization
terminology
improve registry UI and runtime visibility
6.10 marketplace
Status: PARTIAL Current: 7.3/10 Target: 10+/10

Must do
richer listing metadata
screenshots/previews
trust/compliance markers
plan/region compatibility
scopes/permissions
sandbox install
rollback expectations
seed more first-party catalog content
6.11 policies
Status: PARTIAL Current: 7.0/10 Target: 10+/10

Must do
policy diff engine
impact preview
sandbox apply
rollback
policy dependency graph
registry/report/workflow integration
6.12 schools
Status: PARTIAL Current: 7.4/10 Target: 10+/10

Must do
split giant views
reduce raw SQL
harden public/control-plane routes
clarify school vs platform control-plane logic
improve services/orchestration
6.13 accounts
Status: PARTIAL Current: 6.9/10 Target: 10+/10

Must do
split giant views
move role-home and recommendation logic to services
improve onboarding/setup integration
clean up role/identity routing
6.14 portal
Status: PARTIAL Current: 6.9/10 Target: 10+/10

Must do
separate parent/teacher/student concerns
connect to Experience Studio
improve document/action/communication flow
standardize page archetypes
6.15 finance
Status: PARTIAL Current: 6.6/10 Target: 10+/10

Must do
split by subdomain
reduce raw SQL
deepen workflows and family finance UX
improve financial analytics and mobile readiness
6.16 academics
Status: PARTIAL Current: 7.7/10 Target: 10+/10

Must do
deepen tests
tighten registries/policies/runtime integration
improve canonical academic graph
improve packageability of academic outputs
6.17 people
Status: PARTIAL Current: 7.1/10 Target: 10+/10

Must do
sharpen one-person / relationship graph
improve deduplication/identity resolution
strengthen guardian/student/staff relationship modeling
connect to 360 surfaces
6.18 student360 / people360
Status: PARTIAL Current: 6.2/10 Target: 10+/10

Must do
full canonical 360 view
role-specific 360 variants
integrate academics, attendance, finance, communication, intervention, documents, risk
6.19 reports
Status: PARTIAL Current: 7.1/10 Target: 10+/10

Must do
report packs
dependency mapping
sample-data previews
branding/policy/registry integration
rollout/versioning
6.20 automation
Status: PARTIAL Current: 6.9/10 Target: 10+/10

Must do
orchestration layer
migration lifecycle workbench
retries/compensation/SLA
better simulation
run confidence metrics
6.21 communication
Status: PARTIAL Current: 7.3/10 Target: 10+/10

Must do
unify parent/student/staff communication
communication packs
deeper workflow/branding integration
delivery analytics and segmentation
6.22 analytics
Status: PARTIAL Current: 7.1/10 Target: 10+/10

Must do
tenant maturity score
health score
risk analytics
benchmark analytics
pack/workflow recommendation logic
action-oriented analytics
6.23 observability
Status: PARTIAL Current: 6.7/10 Target: 10+/10

Must do
request/runtime/workflow/package/migration tracing
tenant health dashboards
structured logging
alerting on silent degradation
6.24 api / apicenter / interop
Status: PARTIAL Current: 6.0–6.2/10 Target: 10+/10

Must do
classify endpoints
harden auth/signatures/rate limiting
reduce public/exempt exposure
API Center as integration governance
interop validation workbench
contract tests
7. Marketplace and ecosystem seeding
Status: PARTIAL

Minimum seeding targets
25+ first-party apps
25+ blueprint packs
30+ workflow packs
20+ dashboard packs
15+ policy bundles
theme/experience packs
setup/onboarding packs
migration packs by vendor and region
report/document packs
role-home packs
Completion criteria
marketplace looks alive, trustworthy, and installable
listings have previews, compatibility, scopes, trust signals, and rollback expectations
8. UX, dashboards, and marketing
8.1 Role-home engine
Status: PARTIAL

Must build
Role-native homes for:

principal
teacher
parent
student
admissions
finance
district/group
support/implementation
platform ops
Must support
next-best-actions
urgent issues
key metrics
recent activity
calm visual hierarchy
8.2 Contextual action engine
Status: NOT DONE

Must build
replace generic quick actions
role-aware, state-aware, urgency-aware actions
one clear primary action per screen
8.3 Page archetype enforcement
Status: PARTIAL

Every page must fit
Role Home
Setup Studio
Decision Console
Operational Workbench
Catalog / Marketplace
Record Detail
8.4 Marketing front
Status: PARTIAL Current: 6.9/10

Must do
proof-rich product visuals
AI-generated hero assets and motion
migration diagrams
ecosystem/control-plane diagrams
role-home previews
setup-studio visuals
stronger comparison/replacement messaging
better institution-type and region pages
Completion criteria
website looks like platform software, not just an ambitious SaaS landing site
9. Docs truth audit
Status: PARTIAL

Problem
Docs still show partial or not-yet-complete items.

Required fix
audit docs folder
map each plan/audit item to:
DONE
PARTIAL
NOT DONE
DEPRECATED / REPLACED
BLOCKED
no contradictory “all done” language
one canonical completion source of truth only
Must explicitly reconcile
docs completion audit files
docs roadmap implemented-vs-not files
current platform reality
10. Code hygiene and ops
Status: PARTIAL

Required fix
reduce print()
replace with structured logging
inventory and prune management commands
clean repo root/docs clutter
classify subprocess usage
improve lint/CI gates
enforce deprecation policy
Completion criteria
no major hygiene debt remains as a visible platform pattern
11. Execution order
Phase A — red-alert hardening
AI secret exposure removal
public/exempt endpoint review
raw SQL audit
exception reduction in sensitive domains
Gilead purge
Phase B — siteconfig and settings dismantling
settings usage inventory
ownership reassignment
shrink SiteSettings
build bounded consoles
delete old behavior paths
Phase C — runtime/metadata law
make runtime absolute
complete metadata catalog
add lineage and runtime inspector
add contract tests
Phase D — Studio OS
shared shell
Experience Studio
Launch Studio
Automation Studio
Output Studio
Control Studio
retire old tool identities
Phase E — ecosystem productization
deepen package engine
seed packs/apps
improve marketplace trust/install UX
package reports/documents/themes/setup flows
Phase F — UX and marketing authority
role-home engine
contextual actions
page archetypes
proof-rich marketing visuals and comparison pages
Phase G — docs truth reconciliation
align docs with reality
close or reclassify all outstanding roadmap items
keep one canonical completion ledger only
12. Final scoring gate
The platform does not qualify as 9.5+/10 until all are true:

siteconfig is materially decomposed
SiteSettings no longer acts as tenant-behavior truth
runtime is the only legal behavior engine
AI secrets are safe
public surfaces are hardened
Gilead residue is gone from live/default-facing surfaces
Studio OS replaces fragmented tools
package engine is production-grade
marketplace/packs are deeply productized
docs truth audit no longer exposes unresolved contradictions
marketing front visually proves platform-grade seriousness
13. Final statement
RunMyCampus is no longer a single-school product.

RunMyCampus is a serious multi-tenant platform in transition.

To become the north star — the Shopify / Salesforce / AWS / Amazon Marketplace of education — the next phase must be:

more subtractive
more disciplined
more runtime-governed
more metadata-governed
more secure
more low-click
more visually undeniable
more honest in completion tracking
This file is the canonical execution ledger until those conditions are met.
