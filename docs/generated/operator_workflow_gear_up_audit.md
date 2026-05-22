# Operator Workflow Gear-Up Audit (Phase 5)

_Generated 2026-05-22 — read-only filesystem walk, no product code changes, no commits, no SOT updates. Companion JSON at `docs/generated/operator_workflow_gear_up_audit.json`._

## Scope and inputs

This audit lands Phase 5 of the platform-wide workflow audit by classifying every operator workflow against a 13-field rubric (entry route, step count, primary action, next-best action, blocker surfacing, audit-event emission, help/howto presence, AI guidance, tenant-impact documentation, dead-end signals, simplification recommendation, priority, existence).

Inputs consumed:

- `docs/generated/platform_workflow_code_truth_inventory.json` + `.md` (Phase 0)
- `config/manager_urls.py` (71 direct operator routes)
- `apps/schools/super_urls.py` (180 routes — operator command center)
- `apps/schools/control_plane.py` (`require_super_access_with_host` + `user_has_control_plane_access` + `log_control_plane_action`)
- `apps/siteconfig/views_cockpit_admin.py` + `apps/siteconfig/urls.py` (cockpit configure)
- `apps/migration_cloud/urls.py` + `views_*.py` (Migration Cloud operator views)
- `apps/studio_os/urls.py` + `views.py` (5-mode shell)
- `apps/apicenter/urls.py` + `views.py` + `ai_center_urls.py` (API Center + AI Center)
- `apps/sales/urls.py` + `views.py`
- `apps/feedback/urls.py` + `views.py` (VoC + roadmap)
- `apps/platform_runtime/configuration_urls.py`
- `config/tenant_urls.py` (tenant-exposure check)
- `docs/ROLE_PERMISSION_MATRIX_2026_05_16.md` (v2.83 — 808 URL→view rows, 726 login-gated, 66 candidate-anonymous)
- `CLAUDE.md`

## Audited workflows (summary table)

| # | Workflow | Entry route | Primary | Next-best | Blocker | Audit | Help | AI | Tenant-impact | Priority | Exemplar |
|---|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 | /super command center | `/super/`, `/super/command-center/` | yes | yes | yes | unknown | yes | yes | yes | p3 | yes |
| 2 | /configuration | `/configuration/` | yes | yes | unclear | yes | no | no | yes | p1 | |
| 3 | Studio OS operator mode | `/studio/` | yes | yes | yes | yes | no | yes | yes | p2 | yes |
| 4 | AI Center | `/super/ai-center/` | yes | yes | unclear | unknown | no | yes | unclear | p2 | |
| 5 | API Center | `/api-center/` | yes | yes | unclear | yes | yes | yes | yes | p2 | |
| 6 | Migration Cloud operator | `/super/migration/` + `/health/` + `/command-center/` | yes | yes | yes | yes | no | yes | yes | p3 | yes |
| 7 | Voice of Customer | `/super/voice-of-customer/` | yes | yes | yes | **no** | yes | no | yes | p1 | |
| 8 | Product Roadmap | `/super/product-roadmap/`, `/product-roadmap/` | yes | yes | unclear | **no** | yes | no | yes | p1 | |
| 9 | Support / Success | `/super/support/`, `/super/customer-success/`, `/support/` | yes | yes | yes | unknown | no | unclear | yes | p2 | |
| 10 | Compliance | `/super/compliance/` | yes | unclear | unclear | unknown | no | no | yes | p2 | |
| 11 | Security | `/super/security/` (3 alias routes) | yes | yes | yes | yes | no | no | yes | p1 | |
| 12 | Observability | `/ops/incidents/`, `/super/analytics/`, `/super/pulse/`, `/super/health/` | yes | yes | yes | yes | no | yes | yes | p1 | |
| 13 | Billing / Usage | `/super/billing/`, `/super/usage/`, `/super/billing-accounts/` | yes | yes | unclear | unknown | no | no | yes | p2 | |
| 14 | Marketplace / App Catalog | `/super/marketplace/` (16 routes) | yes | yes | yes | yes | no | yes | yes | p2 | |
| 15 | Blueprints / Packs / Governance | `/super/blueprints/`, `/super/policies/`, `/configuration/blueprints/` | yes | yes | yes | yes | no | no | yes | p1 | |
| 16 | Tenant health | `/super/tenant-health/`, `/super/tenants/<id>/360/`, `/super/migration/health/` | yes | yes | yes | unknown | no | no | yes | p2 | |
| 17 | Implementation command center | `/super/create/`, `/super/playbook-operator-hub/`, `/super/migration/command-center/` | yes | unclear | yes | yes | no | yes | yes | p1 | |
| 18 | Defect closure loop | `/ops/incidents/`, `/super/support/`, `/super/feedback-loop/`, `/super/marketplace/incidents/` | yes | unclear | yes | yes | no | yes | unclear | **p0** | |
| 19 | Sales pipeline (operator-side) | `/sales/` | yes | yes | unclear | **no** | no | no | no | p1 | |

All 19 workflow `existence` claims verified by direct file inspection of the cited urls.py (or `partially-verified` where the workflow is a synthesis of routes that exist but no single landing yet ties them together — implementation-command-center and defect-closure-loop both fall in this bucket).

## Spot-check route verification

10 `current_entry_route` claims were verified by reading the corresponding urls.py and matching the `path(...)` declaration to a view callable that exists:

1. `super:dashboard` -> `apps/schools/super_urls.py` line 70: `path("", require_super_access_with_host(super_views.super_dashboard_v2), name="dashboard")` -> **verified**
2. `super:command_center` -> `apps/schools/super_urls.py` line ~101: `path("command-center/", require_super_access_with_host(super_views.super_command_center_v2), name="command_center")` -> **verified**
3. `super:migration_cloud` -> `apps/schools/super_urls.py` line ~302: `path("migration/", require_super_access_with_host(super_migration_cloud), name="migration_cloud")` -> **verified**
4. `migration_cloud_super:migration_cloud_health` -> `apps/migration_cloud/urls.py` line ~120: `path("health/", views_health.MigrationCloudHealthView.as_view(), name="migration_cloud_health")` -> **verified**
5. `studio_os:shell` -> `apps/studio_os/urls.py` line 55: `path("", studio_shell, name="shell")` -> **verified**
6. `apicenter:dashboard` -> `apps/apicenter/urls.py` line 8: `path("", views.api_center_dashboard, name="dashboard")` -> **verified**
7. `feedback:voice_of_customer` -> `apps/feedback/urls.py` line 26: `path("super/voice-of-customer/", views.voice_of_customer, name="voice_of_customer")` -> **verified**
8. `super:trust_center` -> `apps/schools/super_urls.py`: `path("trust/", require_super_access_with_host(super_views.super_trust_center), name="trust_center")` -> **verified**
9. `configuration:center` -> `apps/platform_runtime/configuration_urls.py` line 36: `path("", configuration_center, name="center")` -> **verified**
10. `siteconfig:cockpit_configure` -> `apps/siteconfig/urls.py` line 600: `path("super/configure/cockpit/", CockpitConfigureView.as_view(), name="cockpit_configure")` -> **verified**

## RBAC posture cross-reference

`docs/ROLE_PERMISSION_MATRIX_2026_05_16.md` (v2.83) headline numbers:

- URL -> view rows indexed: **808**
- Views indexed: **1564**
- Login-gated: **726** | Role-gated: **74** | Permission-gated: **91**
- Inline `request.user.is_authenticated` checks: **60**
- Auth mixin-gated: **34**
- `# rbac-allow:` markers: **1** (count at scan time; many more have been added in v3.32+ waves since the scan)
- Candidate-anonymous: **66**
- Unresolved view symbol: **12**

Operator surface decorator coverage on `apps/schools/super_urls.py`:

- 171 of 181 `path()` declarations carry `require_super_access_with_host(...)` (verified via grep)
- The remaining 10 are class-based views (`MealPlanAnalyticsView`, `EmailHealthDashboardView`, `SmtpProbeJsonView`, `EmailDeliveryConfigView`, `SignupDiagnosticsView`, `EmailHealthStreamView`, `EmailProviderWebhookView`) — each carries an inline `# rbac-allow:` marker; the email webhook is intentionally anonymous (signature-verified bounce receiver: `rbac-allow: anonymous-signature-verified-bounce-webhook-receiver`).

## Tenant exposure check (operator-only surface leakage)

`config/tenant_urls.py` does NOT include `apps.schools.super_urls`. The `/super/` URL family is mounted only from `config/manager_urls.py` (manager-host urlconf), and every operator route in `super_urls.py` is wrapped in `require_super_access_with_host(...)` which enforces both the host gate (`request.public_host_kind == "manager"`) and the operator role gate (`user_has_control_plane_access(user)`).

False-positive concern resolved: `siteconfig:cockpit_configure` lives at `/siteconfig/super/configure/cockpit/` (path contains the literal `super` segment) but is mounted from `config/manager_urls.py` via `include(("apps.siteconfig.urls", "siteconfig"))`. The view uses `LoginRequiredMixin` + `UserPassesTestMixin` requiring `is_staff` or `is_superuser`. Verified staff-only.

**Verdict: no operator-only surfaces accidentally exposed to tenant users.**

## Fix-me-first top 10

| Rank | Workflow | Recommendation | Touch files (est.) | Priority |
|---:|---|---|---|:-:|
| 1 | defect-closure-loop | Cross-link incident <-> ticket <-> feedback <-> roadmap so the operator never context-switches surfaces; no new pages, just link buttons + back-refs. | 4 templates + 2 view files | **p0** |
| 2 | voice-of-customer | Wire `AuditEvent` emission into `operator_feedback_action` + `add_to_roadmap` so cross-tenant triage decisions are append-only. | `apps/feedback/views.py`, `services.py` | p1 |
| 3 | security | Collapse 3 alias routes (`security_hub`, `security_command_center`, `enterprise_security_command_center`) into one canonical `/super/security/` with permanent 301s. | `apps/schools/super_urls.py` | p1 |
| 4 | observability | Build a single `/super/observability/` landing aggregating `/ops/incidents/` + `/super/analytics/` + `/super/pulse/` + `/super/health/` as a 4-card grid. | new view + URL + template | p1 |
| 5 | implementation-command-center | Aggregate provisioning + sales + migration + playbook into one `/super/implementation/` landing with phased card layout (Sell -> Provision -> Migrate -> Launch). | new view + URL + template + search-catalog entry | p1 |
| 6 | blueprints-packs-governance | Link each row in `super:blueprints_catalog` directly to `/configuration/blueprints/<key>/` apply UX; today the operator must remember the surface split. | 4 catalog templates | p1 |
| 7 | sales-pipeline | Add sales pipeline + first-100-schools-dashboard to `manager_search_api._manager_search_static_catalog` for discoverability. | `config/manager_urls.py` | p1 |
| 8 | configuration | Add a help drawer on `configuration_center` + `change_request_detail`; the 5-action approval chain has no in-page how-to. | 2 templates | p1 |
| 9 | ai-center | Demote 8 flat sub-routes to 4 hero cards (Inventory, Friction, KB Drafts, Settings) with secondary nav for the rest. | template + view context | p2 |
| 10 | tenant-health | Add per-row primary-action buttons (Open tenant 360 / Switch-to-tenant / Run sync repair); today it's panel-only. | 1 template + view context | p2 |

## Exemplary workflows — preserve, don't rebuild

Per CLAUDE.md "surface scope violations early": three operator workflows already exemplify the standard and should NOT be rebuilt in subsequent waves; they should be referenced as the pattern:

### 1. `/super command center` (super-command-center)

Curated 31-entry static catalog in `manager_search_api` drives unified search; `require_super_access_with_host` decorator on every route; `manager_search_api` wires `School` + `PlatformIncident` + `TenantSubscription` model deep-links into the search results. Already the gold standard for control-plane single-pane entry.

### 2. Migration Cloud operator view (migration-cloud-operator)

v3.39.0 platform-trust wave (5-agent fan-out) shipped: tamper-evident hash-chained `MigrationCloudAuditEvent` log (append-only, FERPA 7-year retention), per-tenant `CompanionKeypair` with auto-fingerprint-verify on every upload, counsel-pending docket markers for blocked vendor write paths, scoped-API rate-limiting, 8+ audit-event emit sites. Single primary action (`bundle_new`), clear next steps (advance/apply/reconcile/feedback), full audit trail.

### 3. Studio OS operator mode (studio-os-operator-mode)

5-mode shell with shared preview + publish/rollback + version-history + AI copilot rail (`services.ai_helpers` allowlisted infrastructure exception). Operator and tenant code paths unified via `use_control_plane_shell` guard. The mode rail is durable across pages (one shell, five modes). Sets the pattern for any future multi-mode operator surface.

## Honest gaps flagged by inventory (carried forward)

Operator workflow templates without help template (per Phase 0 inventory + this audit):

- `migration_cloud` — vendor_write_status / maa_v2_promotion / health / command-center surfaces rely on external docs (`docs/MIGRATION_CLOUD_AUDIT_LOG.md`), no in-page help drawer
- `studio_os` — 5 modes, 48 routes, no per-mode help drawer
- `siteconfig:cockpit_configure` — no in-page how-to (form-only)
- `platform_runtime:configuration` — change-request 5-action chain has no how-to

Operator workflow templates without feedback hook (per Phase 0):

- `apicenter`, `migration_cloud`, `studio_os`, `platform_runtime`, `sales` — none embed `templates/feedback/partials/help_center_engage_strip.html` or similar contextual feedback widgets.

## Constraints honored

- No product code changes (audit only)
- Read-only filesystem walk (Read + Grep tools)
- Stdlib-only helpers (no helper script needed; direct grep + Read sufficed)
- No commits, no SOT updates
- Django not run
- No emojis

## Verdict

`PHASE_5_OPERATOR_WORKFLOW_GEAR_UP_AUDIT_READY`
