# Local-First Global Template Marketplace + Experience Blueprint Engine — execution plan

**Status:** **SHIPPED — batch 1400, SW `sms-v3.63.0`, 2026-05-23.** Originally-planned 4-wave program (1400/1401/1402/1403) was compressed into a single foundational wave (1400) by maximum reuse of the existing `pack_*` lifecycle. **Wave B+ residuals listed in §11.5 below.**
**Plan owner:** RunMyCampus platform team
**Target SW range:** `sms-v3.63.0` (Wave A SHIPPED) → `sms-v3.66.x` (Wave B+ polish)
**Batch IDs:** **1400 (SHIPPED)** — Waves B/C/D collapsed into a single residual list (§11.5).
**Created:** 2026-05-23 (planned), **2026-05-23 SHIPPED** same-day single-session execution.
**Plan scope:** **REPO ONLY** — no live tenant rollout, no Render parity claim, no monetization claim.
**Handoff-ready for:** Claude Code, Codex, Cursor — this file is self-contained.

---

## 0 — Why this exists and how to read this file

This plan turns the user's "Local-First Global Template Marketplace" prompt into an **executable, governed program** that ships in 4 waves. It is NOT "create 75 HTML files." It is **layer a new `ExperienceTemplate` registry on top of the existing platform-runtime blueprint/pack engine** so tenants and operators can browse, preview, apply, customize, and roll back premium operating-experience templates that feel local to their country, language, school type, and connectivity reality.

The user explicitly asked: "the prompt may mention 50 templates but I want more than that." Target is **75** (50 base catalog + 25 local-first regional). Wave breakdown sizes each wave so a single 5-agent fan-out can ship it within the existing wave cadence.

**If you are picking this up from Codex/Cursor:** start at §11 (Handoff state). The rest of the doc tells you why we made each choice so you can extend it without re-litigating.

---

## 1 — Phase 0 audit findings (already done — do NOT re-audit)

The audit-before-changing rule from the user's prompt was honored during plan authorship. These findings are **the inheritance** for whoever picks this up; do not redo discovery.

### 1.1 Existing platform systems we will REUSE (not duplicate)

| System | Path | Why it matters |
|---|---|---|
| **Blueprint apply/audit/preview/rollback** | `apps/platform_runtime/blueprint_apply.py`, `blueprint_audit.py`, `blueprint_contract.py`, `blueprint_impact.py`, `blueprint_preview.py`, `blueprint_rollback.py` | The full **Preview → Impact → Apply → Audit → Rollback** lifecycle already exists. Templates use this lifecycle. |
| **Pack apply/audit/preview/rollback** | `apps/platform_runtime/pack_apply.py`, `pack_audit.py`, `pack_contract.py`, `pack_dependency_graph.py`, `pack_impact.py`, `pack_preview.py`, `pack_rollback.py`, `pack_simulation.py` | Pack-level lifecycle twin. `ExperienceTemplate` will be a **pack subtype**. |
| **Live preview engine** | `apps/platform_runtime/live_preview.py` | Tenant-scoped preview sessions with sample data — exactly what §6 of the prompt asks for. |
| **Design system tokens** | `apps/platform_runtime/design_system.py`, `static/css/design-tokens.css` | Canonical token cascade. Local-first palettes register here, NOT in a new tokens system. |
| **Localization** | `apps/platform_runtime/localization.py`, `apps/siteconfig/_seed_country_languages.py` | 60+ market `marketing_voice` voices and 11 multilingual countries already covered (per Wave 13 / v3.62.18). Reuse for template `supported_languages` + `cultural_accent_policy`. |
| **Experience packs** | `apps/brand_experience/experience_packs.py`, `models.py` | Has `ExperiencePack` + `ThemePack` + `InstalledPackage` already. `ExperienceTemplate` references these as composition pieces. |
| **Marketplace pack registry** | `apps/marketplace/pack_registry.py`, `pack_services.py`, `manifest_schema.py`, `permissions.py`, `monetization.py` | Catalog + browse + filter + permission scoping + monetization plumbing all exist. Wire templates through this. |
| **Tenant pack install** | `apps/packages/engine.py`, `tenant_pack_install.py`, `models.py` | `InstalledPackage` is the canonical "what's applied to this tenant" record. Template assignments piggyback. |
| **Runtime blueprint proxies** | `apps/runtime_blueprints/models.py` | Proxies over `BlueprintPack`, `DashboardPack`, `WorkflowPack`, `ReportCardStyle`, `DashboardTemplate`, `DashboardLayout`, `DashboardWidget`, `TenantLayoutAssignment`, `OfficialReportTemplate`, `ReportTemplate`, `ThemeLayout`, `FormDraft`, `UserPreference` — **all of these already exist** in `apps/siteconfig/models_dashboard.py`, `models_workflow.py`, `models_tooling.py`. |
| **Studio OS surface** | `apps/studio_os/navigation.py`, `views.py`, `deep_links.py`, `services.py`, `copilot_rail_service.py`, `school_infrastructure.py` | Studio OS has Overview / Experience / Automation / Output / Launch / Control sections (per batch 1373 next-realm wave). Template selection wires into Experience section. |
| **Setup studio (onboarding)** | `apps/setup_studio/services.py`, `tenant_guard.py`, `models.py` | Onboarding flow already exists. Template-pick step is a new step in this flow. |
| **Cockpit context resolver** | `apps/siteconfig/context_processors.py`, `apps/platform_runtime/context_processors.py`, `apps/platform_runtime/cockpit_context.py` (Wave 12/13 marketing voice) | Already does shallow merge of operator overrides over defaults. `ExperienceTemplate` overrides plug in here. |
| **Configuration change governance** | `apps/platform_runtime/configuration_change_requests.py`, `configuration_change_set.py`, `configuration_versioning.py`, `configuration_urls.py` | Template apply emits a change request → approval → apply → audit chain. Reuse, don't fork. |
| **Country registry + localization** | `apps/siteconfig/CountryRegistry` (cockpit_override_payload from Wave 12), `_INDIA_STATE_BOARD_CALENDAR_VARIANTS`, `_seed_country_localization`, `country_localization_service.py` | Local-first **country/region** layer already exists at country granularity. `LocalExperienceProfile` is a thin overlay, not a new geo system. |
| **AI helper bridge** | `services/ai_helpers.py::invoke_with_request`, `normalize_gateway_metadata` | Template AI recommendations route through here. **`apps/` code must NOT import `services.ai_gateway` directly** — boundary scanner enforces this (baseline 0). |

### 1.2 What is MISSING (the actual work of this plan)

1. A **dedicated `ExperienceTemplate` registry** that composes `ExperiencePack` + `ThemePack` + `DashboardPack` + `WorkflowPack` + `ReportTemplate` into a single browseable, role-aware, local-aware **layout identity** with explicit preview/apply/rollback path.
2. The **75 template definitions** themselves (registry entries, not hardcoded HTML).
3. The **`LocalExperienceProfile`** overlay that bundles country + region + language + academic system + cultural accent tokens.
4. The **Template Marketplace UI** (card grid + filters + compare + preview button) inside Studio OS Experience + Tenant Studio.
5. The **Template apply/rollback views** (thin wrappers over existing `pack_apply` / `pack_rollback` that record `TemplateAuditEvent` with template-specific metadata).
6. The **AI recommendation service** for templates (gateway-routed, permission-filtered, scoped to tenant context).
7. The **layout primitives** (the 10 reusable layout families that produce the 75 variants — NO hardcoded duplicate HTML).
8. **Tests + verifiers** for all of the above.

### 1.3 What is EXPLICITLY out of scope

- Live tenant rollout, beta program, monetization billing pipeline (deferred to Wave E+ after counsel + Lane 2 evidence).
- New top-level Django app — everything fits into existing `apps/marketplace/`, `apps/brand_experience/`, `apps/platform_runtime/`, `apps/studio_os/`, `apps/setup_studio/`.
- New database (no new Postgres cluster, no new schema family).
- Replacing the design-tokens.css cascade. New palettes register as additional token sets, not a new tokens system.
- Re-implementing the existing v3.61–v3.62 country-adaptive signup wave — this plan layers on top of it.

### 1.4 Non-negotiable constraints from CLAUDE.md (do not re-litigate)

- **No hardcoding** — every value routes through the 7-layer configurability contract.
- **Apple-tier polish** — every new CSS uses semantic tokens (`var(--surface-*)`, `var(--text-*)`, `var(--hairline)`, etc.), never raw hex literals outside theme-scope selectors. `scan_off_token_colors` baseline 0 must hold.
- **`scan_undefined_css_classes` baseline 0** — every `.rmc-*` class referenced in a new template MUST exist in `static/css/rmc-class-grammar.css` or a sibling bundle.
- **`scan_template_safety` clean** — no multi-line `{# … #}` (Django supports single-line only); use `{% comment %}…{% endcomment %}`. Lesson from Wave 13.
- **No `href="#"`, no `javascript:void(0)`, no fake buttons** — `scan_operator_shell_dead_hrefs` enforces this.
- **`scan_tenant_queryset_safety` baseline 0** — every queryset on a tenant-scoped model carries `school=` / `school_id=` / `school__isnull=` OR a 3+-part-hyphenated `# tenant-isolation-allow: <reason>` marker.
- **Role strings** — never literal "ADMIN"/"TEACHER"/"PARENT"/"STUDENT"/"PROPRIETOR". Use `User.Role` enum or `apps.platform_runtime.role_registry`.
- **Service worker version** — bump `CACHE_VERSION` to `sms-vX.Y.Z-<slug>-<YYYY-MM-DD>` on every wave that ships new CSS/JS. Monotonic — `verify_service_worker_version.py --check-monotonic` enforces.
- **AI gateway boundary** — app code must route through `services.ai_helpers`, not `services.ai_gateway` directly. Allowlisted: `apps/portal/ai_provider.py`, `apps/portal/views_ai_gateway.py`, `apps/migration_cloud/ai_bridge.py`, `apps/platform_runtime/ai_providers.py`, `apps/siteconfig/management/commands/aggregate_ai_metrics.py`.
- **PII logging smell** — `scan_pii_logging_smell` baseline 0; no `logger.info(f"... {token}")` for `password`/`token`/`secret`/`hash`/`signature_text`/`email`/`api_key`/`private_key`/`ssn`/`dob` identifiers.

---

## 2 — Strategic positioning (do not lose sight of this)

This is the lens for every architecture decision. If a design choice doesn't serve one of these analogies, drop it.

| Analogy | What this plan delivers |
|---|---|
| **Shopify of education** | A school admin browses premium operating-experience templates (not just visual themes) and applies one to get a working portal, dashboards, role homes, parent surface, finance dashboard — all coherent. |
| **AWS of education** | Templates are governed infrastructure: Preview → Impact → Apply → Audit → Version → Rollback, with tenant scope and permission scope baked in. |
| **Salesforce of education** | Role-aware experiences: principal, teacher, parent, student, bursar, registrar, operator each get a tuned home — not the same dashboard with different filters. |
| **Linux of education** | Modular: `ExperienceTemplate` composes from existing `DashboardPack` + `WorkflowPack` + `ThemePack` + `ReportTemplate`. Partners can ship templates as packages later (out of scope for the 4-wave program, but architecture supports it). |
| **Amazon of education** | Lower friction: a new tenant picks a template at signup and lands with a working operating model on day one, instead of configuring 200 settings manually. |

---

## 3 — Architecture: how ExperienceTemplate layers on the existing engine

```
                  ┌──────────────────────────────────────────────────────┐
                  │              ExperienceTemplate (NEW)                │
                  │   key, name, role_target, profile_type, surface,     │
                  │   layout_family, supported_countries, local_profile, │
                  │   composition refs (below), status, version          │
                  └────────────────────────────┬─────────────────────────┘
                                               │ composes
       ┌───────────────────────┬───────────────┼──────────────────────┬─────────────────┐
       ▼                       ▼               ▼                      ▼                 ▼
┌─────────────┐         ┌──────────────┐  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ ExperienceP │         │  ThemePack   │  │ DashboardPack│   │ WorkflowPack │   │ ReportTpl    │
│ ack (EXIST) │         │   (EXIST)    │  │   (EXIST)    │   │   (EXIST)    │   │   (EXIST)    │
└─────────────┘         └──────────────┘  └──────────────┘   └──────────────┘   └──────────────┘
       │                       │                  │                  │                  │
       └───────────────────────┴──────────────────┼──────────────────┴──────────────────┘
                                                  │ enforced through
                                                  ▼
                  ┌──────────────────────────────────────────────────────┐
                  │   apps/platform_runtime/pack_{preview,apply,audit,   │
                  │   rollback,impact,simulation,dependency_graph}.py    │
                  │   (existing pack lifecycle engine — REUSE)           │
                  └────────────────────────────┬─────────────────────────┘
                                               │ writes
                                               ▼
                  ┌──────────────────────────────────────────────────────┐
                  │  InstalledPackage (EXIST) + TemplateAssignment (NEW) │
                  │  + TemplateAuditEvent (NEW) + TemplatePreviewSession │
                  │  (NEW, may be backed by existing live_preview)       │
                  └──────────────────────────────────────────────────────┘
```

**The hard rule:** if a feature already exists as `blueprint_*` or `pack_*` in `platform_runtime`, the new code in this plan **delegates** to it. We never re-implement `apply` or `rollback`.

---

## 4 — Data model (additions only; no replacements)

### 4.1 `ExperienceTemplate` (registry-backed; can be a model OR a Python registry)

Decision: **start as a Python registry in `apps/brand_experience/experience_templates.py`** (matching the `ExperiencePack` pattern). Promote to a DB model only when partners need to ship templates dynamically.

Fields (every template MUST have all of these):

| Field | Type | Notes |
|---|---|---|
| `key` | str (kebab-case) | Globally unique. e.g. `executive-command-center`. |
| `name` | lazy str (`gettext_lazy`) | Display name. |
| `description` | lazy str | One-sentence purpose. |
| `category` | enum | `operator` / `tenant-admin` / `teacher` / `parent` / `student` / `staff` / `specialized` / `local-first` / `studio-experience` |
| `profile_type` | enum | `dashboard` / `portal` / `role-home` / `report` / `setup` / `studio-section` |
| `role_target` | str list | References `apps.platform_runtime.role_registry` keys. Never literal role strings. |
| `surface` | str list | Which app shells consume it: `portal`, `manager-control-plane`, `studio-os`, `marketing`, `admin`. |
| `layout_family` | str | One of the 10 layout families (see §6.0). |
| `supported_countries` | str list ISO-2 OR `["*"]` | `["*"]` = global default; specific ISO-2 codes for local-first variants. |
| `supported_languages` | str list BCP-47 OR `["*"]` | Aligned with existing 60-market `marketing_voice` coverage. |
| `local_profile_ref` | str or null | FK to `LocalExperienceProfile.key`. Only set for local-first variants. |
| `required_modules` | str list | App labels: `academics`, `finance`, `billing`, `migration_cloud`, etc. Template apply fails preview if module disabled. |
| `optional_modules` | str list | App labels that gracefully degrade. |
| `theme_pack_ref` | str | FK to `apps.brand_experience.models.ThemePack.code` — composition. |
| `dashboard_pack_ref` | str or null | FK to `siteconfig.models_dashboard.DashboardPack.code` if template owns a dashboard pack. |
| `workflow_pack_ref` | str or null | FK to workflow pack code. |
| `report_template_ref` | str or null | FK to report template code. |
| `preview_view_name` | str | Django URL name for live preview. MUST resolve. |
| `apply_view_name` | str | Django URL name for apply. MUST resolve and emit audit event. |
| `rollback_view_name` | str | Django URL name for rollback. MUST resolve. |
| `thumbnail` | static path | Resolves via `{% static %}`. |
| `accessibility_level` | enum | `AA` / `AAA` / `partial`. AA is the floor; AAA preferred. |
| `mobile_level` | enum | `mobile-first` / `responsive` / `desktop-only`. `desktop-only` requires categorical-allow marker. |
| `tenant_safe` | bool | False means operator-only and MUST NOT appear in tenant marketplace listing. |
| `operator_only` | bool | Inverse: True means hidden from tenant catalog. |
| `tags` | str list | `premium`, `compact`, `executive`, `academic`, `finance`, `parent-friendly`, `low-connectivity`, `bilingual`, `mobile-first`, `data-rich`, `minimal`, `luxury`, `heritage` |
| `status` | enum | `draft` / `preview_ready` / `tenant_ready` / `operator_ready` / `deprecated` |
| `version` | str | semver. Bump on layout change. |

### 4.2 `LocalExperienceProfile` (NEW Python registry in `apps/siteconfig/local_experience_profiles.py`)

Composes the local-first overlay. Reuses existing `CountryRegistry.cockpit_override_payload` for marketing voice — does NOT duplicate it. Adds layout-specific overlays.

| Field | Type | Notes |
|---|---|---|
| `key` | str | e.g. `cm-bilingual-private`, `ng-low-connectivity`, `in-ka-state-board`. |
| `country` | str ISO-2 | |
| `region` | str or null | State / province code. |
| `languages` | str list BCP-47 | Primary languages this profile supports. |
| `academic_system` | enum | `gce-anglophone` / `bac-francophone` / `cbse` / `state-board` / `gcse-igcse` / `ap-us` / `ib` / `cambridge` / `state-charter` / `boarding-uk` / `bilingual-mixed` |
| `grading_system` | str | `letter` / `numeric-0-100` / `gpa-4` / `gcse-9-1` / `cgpa-10` / `cgpa-4` |
| `calendar_system` | str | `gregorian-jul-jun` / `gregorian-aug-may` / `gregorian-jan-dec` / `gregorian-apr-mar` / `gregorian-jun-may` |
| `communication_style` | enum | `formal` / `warm-formal` / `community-warm` / `compact-direct` |
| `palette_family` | str | References a palette family in `static/css/design-tokens-local-*.css`. |
| `typography_family` | str | References font-stack token. |
| `cultural_accent_policy` | enum | `geometric-warm` / `geometric-cool` / `editorial-neutral` / `community-organic` |
| `parent_engagement_default` | enum | `daily-digest` / `weekly-summary` / `event-driven` / `mobile-sms-first` |
| `low_connectivity_default` | bool | If True, mobile-first compact templates rank higher in recommendations. |
| `currency_default` | str ISO-4217 | |
| `payment_rails_default` | str list | `bank-transfer` / `mobile-money` / `card-online` / `cash-collection` / `psp-stripe` / `psp-flutterwave` / `psp-mpesa` |

### 4.3 `TemplateAssignment` (NEW Django model in `apps/brand_experience/models.py`)

Records what's applied. **Extends `InstalledPackage` via OneToOne**, does NOT replace it.

```python
class TemplateAssignment(models.Model):
    installed_package = models.OneToOneField(
        "packages.InstalledPackage",
        on_delete=models.CASCADE,
        related_name="template_assignment",
    )
    template_key = models.CharField(max_length=80, db_index=True)
    local_profile_key = models.CharField(max_length=80, blank=True, db_index=True)
    surface = models.CharField(max_length=32)
    role_target = models.JSONField(default=list)
    applied_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    rollback_snapshot = models.JSONField(default=dict, blank=True)
    customizations = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["template_key", "applied_at"]),
        ]
```

### 4.4 `TemplateAuditEvent` (NEW model in `apps/brand_experience/models.py`)

Mirrors `MigrationCloudAuditEvent`'s append-only pattern from v3.39 / v3.40. Tenant-scoped, hashed actor where appropriate, sanitized payload.

| Field | Type |
|---|---|
| `id` | UUID PK |
| `tenant_id_hash` | char(12) — sha256(school.slug)[:12] |
| `event_type` | enum: `template.preview` / `template.apply_requested` / `template.applied` / `template.rolled_back` / `template.customized` |
| `template_key` | char(80) |
| `local_profile_key` | char(80) blank |
| `actor_id` | FK User SET_NULL |
| `payload_summary` | JSONField (sanitized) |
| `created_at` | auto |

Append-only `save()` guard, `delete()` always raises — copy the `migration_cloud.models_audit` pattern.

### 4.5 `TemplatePreviewSession`

**Do not create a new model.** Use the existing `apps/platform_runtime/live_preview.py` engine and pass `template_key` + `local_profile_key` in its existing session payload. Reuse.

---

## 5 — Routes (new URL surface)

All new URLs **must** be wired through `apps.platform_runtime.configuration_urls` (operator) and a new `apps.brand_experience.urls_marketplace` (tenant). Both inherit existing auth + tenant-isolation middleware.

### 5.1 Operator (manager.runmycampus.com)

| Route | Purpose | Auth |
|---|---|---|
| `/configuration/templates/` | Marketplace browse + filter | Staff |
| `/configuration/templates/<key>/` | Template detail | Staff |
| `/configuration/templates/<key>/preview/` | Live preview, role-selectable | Staff |
| `/configuration/templates/<key>/compare/?other=<key2>` | Side-by-side compare | Staff |
| `/configuration/templates/<key>/apply/` | Apply to selected tenant(s) — emits `template.apply_requested` audit | Staff + change-request approval |
| `/configuration/templates/<key>/rollback/` | Rollback last apply | Staff |
| `/configuration/templates/local/` | Local-first catalog by country | Staff |
| `/configuration/templates/audit/` | Audit log (read-only, paginated, hash truncated) | Staff |

### 5.2 Tenant (`<tenant>.runmycampus.com`)

| Route | Purpose | Auth |
|---|---|---|
| `/school/studio/templates/` | Tenant marketplace (only `tenant_safe=True`) | School admin |
| `/school/studio/templates/<key>/` | Template detail | School admin |
| `/school/studio/templates/<key>/preview/` | Live preview, role-selectable | School admin |
| `/school/studio/templates/<key>/compare/?other=<key2>` | Side-by-side compare | School admin |
| `/school/studio/templates/<key>/apply/` | Apply request — may require platform approval depending on template `tenant_safe` policy | School admin |
| `/school/studio/templates/<key>/rollback/` | Rollback | School admin |
| `/school/studio/templates/<key>/customize/` | Customize tokens/blocks within policy | School admin |
| `/school/studio/templates/local/<cc>/` | Local-first catalog for tenant's country | School admin |

### 5.3 Studio OS integration

Add a fold under Studio OS **Experience** section: `/studio/experience/templates/` that hard-links into the tenant catalog (host-aware — operator host shows operator catalog).

### 5.4 Setup Studio integration

`apps/setup_studio/services.py::TenantOnboardingStep` gains a new step `select_experience_template` between the existing brand/logo step and the role-home preview step. Template choice records into `school.settings["experience_template"]` AND emits `template.applied` audit on confirmation.

---

## 6 — The 75-template catalog

### 6.0 Ten layout families (the reusable primitives)

Templates compose from these. The 75 catalog entries are **variants** of these families, NOT 75 hand-coded HTML pages.

| # | Layout family | Anchor | Use cases |
|---|---|---|---|
| 1 | **Executive Command** | Hero KPI strip + 4-quadrant signal grid + audit timeline rail | Operator command centers, principal command, support command |
| 2 | **Academic Operations** | Timetable strip + class roster cards + attendance heat + assessment queue | Teacher daily, academic lead hub, registrar |
| 3 | **Finance Control** | Cashflow waterfall + outstanding fees rail + reconciliation queue + ledger anchor | Bursar, finance ops, billing operator |
| 4 | **Family Engagement** | Multi-child carousel + announcement river + payment shortcut + calendar week | Parent home, family dashboard |
| 5 | **Teacher Productivity** | Today's classes strip + fast-input desks + parent-comms queue + risk monitor | Teacher templates, attendance + marks fast desk |
| 6 | **Student Progress** | Schedule strip + assignment kanban + grade trend + learning-path lane | Student home, learning progress, assignments+results |
| 7 | **Migration / Readiness** | Stage tracker + impact preview + checklist + rollback panel | Migration ops, launch readiness, implementation war room |
| 8 | **Security & Compliance** | SLO clocks + audit chain + access matrix + incident lane | Security command, compliance dashboard, residency monitor |
| 9 | **Low-Connectivity Compact** | Single-column flow + offline-sync banner + queue depth + compact data cards | Low-connectivity rural school, mobile teacher desk |
| 10 | **Premium International** | Editorial hero + multilingual masthead + admissions strip + alumni rail | International school, premium boarding, bilingual luxury |

### 6.1 Catalog — 75 templates

**Format:** `key | name | family | category | role_target | supported_countries | tenant_safe`

#### A. Operator / Manager Templates (10)

| key | name | family | tenant_safe |
|---|---|---|---|
| `operator-executive-command-center` | Global Executive Command Center | 1 | No |
| `operator-implementation-war-room` | Implementation War Room | 7 | No |
| `operator-support-cockpit` | Support & Success Cockpit | 1 | No |
| `operator-revenue-billing-ops` | Revenue / Billing Operations | 3 | No |
| `operator-security-compliance-command` | Security & Compliance Command | 8 | No |
| `operator-migration-ops-center` | Migration Operations Center | 7 | No |
| `operator-marketplace-console` | Marketplace Operator Console | 1 | No |
| `operator-observability-health` | Observability / Health Center | 8 | No |
| `operator-tenant-lifecycle-command` | Tenant Lifecycle Command | 1 | No |
| `operator-ai-intelligence-console` | AI Center Intelligence Console | 8 | No |

#### B. Tenant School Admin Templates (8)

| key | name | family | tenant_safe |
|---|---|---|---|
| `admin-school-command-center` | School Command Center | 1 | Yes |
| `admin-launch-readiness-cockpit` | Launch Readiness Cockpit | 7 | Yes |
| `admin-academic-ops-hub` | Academic Operations Hub | 2 | Yes |
| `admin-finance-fees-hub` | Finance & Fees Hub | 3 | Yes |
| `admin-staff-ops-hub` | Staff Operations Hub | 1 | Yes |
| `admin-family-engagement-hub` | Family Engagement Hub | 4 | Yes |
| `admin-data-quality-control-room` | Data Quality Control Room | 8 | Yes |
| `admin-low-connectivity-hub` | Low-Connectivity School Hub | 9 | Yes |

#### C. Teacher Templates (8)

| key | name | family | tenant_safe |
|---|---|---|---|
| `teacher-daily-workspace` | Teacher Daily Workspace | 5 | Yes |
| `teacher-class-performance-studio` | Class Performance Studio | 2 | Yes |
| `teacher-attendance-marks-fast-desk` | Attendance + Marks Fast Desk | 5 | Yes |
| `teacher-parent-comms-desk` | Parent Communication Desk | 5 | Yes |
| `teacher-lesson-syllabus-control` | Lesson / Syllabus Control | 2 | Yes |
| `teacher-student-risk-monitor` | Student Risk Monitor | 5 | Yes |
| `teacher-assessment-publishing` | Assessment Publishing Desk | 2 | Yes |
| `teacher-mobile-compact` | Compact Mobile Teacher Desk | 9 | Yes |

#### D. Parent Templates (6)

| key | name | family | tenant_safe |
|---|---|---|---|
| `parent-family-home` | Family Home Dashboard | 4 | Yes |
| `parent-student-progress` | Student Progress View | 6 | Yes |
| `parent-fees-payments-family` | Fees + Payments Family View | 3 | Yes |
| `parent-attendance-behavior` | Attendance + Behavior View | 4 | Yes |
| `parent-comms-hub` | Parent Communication Hub | 4 | Yes |
| `parent-multi-child` | Multi-Child Family Dashboard | 4 | Yes |

#### E. Student Templates (6)

| key | name | family | tenant_safe |
|---|---|---|---|
| `student-home` | Student Home | 6 | Yes |
| `student-assignments-results` | Assignments + Results View | 6 | Yes |
| `student-attendance-schedule` | Attendance + Schedule View | 6 | Yes |
| `student-learning-progress` | Learning Progress View | 6 | Yes |
| `student-help-support` | Student Help / Support View | 6 | Yes |
| `student-mobile-minimal` | Minimal Mobile Student View | 9 | Yes |

#### F. Staff / Non-Teaching Templates (4)

| key | name | family | tenant_safe |
|---|---|---|---|
| `staff-home` | Staff Home | 1 | Yes |
| `staff-hr-payroll` | HR / Payroll Staff View | 1 | Yes |
| `staff-operations` | Operations Staff View | 1 | Yes |
| `staff-transport-canteen-hostel` | Transport / Canteen / Hostel Staff View | 1 | Yes |

#### G. Specialized School Templates (8)

| key | name | family | tenant_safe |
|---|---|---|---|
| `specialized-boarding-school-ops` | Boarding School Operations | 10 | Yes |
| `specialized-bilingual-school` | Bilingual School Dashboard | 10 | Yes |
| `specialized-international-school` | International School Dashboard | 10 | Yes |
| `specialized-low-connectivity-regional` | Low-Connectivity Regional School | 9 | Yes |
| `specialized-private-primary` | Private Primary School | 4 | Yes |
| `specialized-private-secondary` | Private Secondary School | 2 | Yes |
| `specialized-faith-inspired-neutral` | Faith-Inspired Private School (Neutral) | 4 | Yes |
| `specialized-community-day-school` | Community Day School | 4 | Yes |

#### H. Local-First Regional Templates (25 — the +25 the user asked for)

Africa anglophone (5):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-cm-anglophone-private-secondary` | Cameroon Anglophone Private Secondary | CM | `cm-anglophone-gce` |
| `local-ng-private-secondary` | Nigeria Private Secondary | NG | `ng-private-secondary` |
| `local-gh-private-school` | Ghana Private School | GH | `gh-private-school` |
| `local-ke-primary-secondary` | Kenya Primary + Secondary | KE | `ke-cbc-primary-secondary` |
| `local-za-provincial` | South Africa Provincial School | ZA | `za-provincial-grades` |

Africa francophone (4):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-cm-francophone-bac` | Cameroon Francophone Bac D Track | CM | `cm-francophone-bac` |
| `local-ci-private-college` | Côte d'Ivoire Private Collège | CI | `ci-bac-francophone` |
| `local-sn-private-lycee` | Senegal Private Lycée | SN | `sn-bac-francophone` |
| `local-ma-private-school` | Morocco Private School | MA | `ma-bac-bilingual` |

South Asia (4):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-in-cbse-private` | India CBSE Private School | IN | `in-cbse-hindi-medium` |
| `local-in-ka-state-board` | India Karnataka State Board | IN | `in-ka-state-board` |
| `local-pk-private-school` | Pakistan Private School | PK | `pk-fbise-urdu-medium` |
| `local-bd-private-school` | Bangladesh Private School | BD | `bd-sec-edu-bengali` |

East Asia (3):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-jp-international-private` | Japan International Private | JP | `jp-mext-bilingual` |
| `local-kr-international-private` | Korea International Private | KR | `kr-international-bilingual` |
| `local-cn-bilingual-private` | China Bilingual Private | CN | `cn-bilingual-private` |

Southeast Asia (3):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-ph-private-school` | Philippines Private K-12 | PH | `ph-deped-k12` |
| `local-my-private-school` | Malaysia Private School | MY | `my-igcse-bilingual` |
| `local-id-private-school` | Indonesia Private School | ID | `id-private-bilingual` |

Western markets (3):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-us-charter` | US Charter School | US | `us-charter-state` |
| `local-uk-cambridge-international` | UK / Cambridge International | GB | `gb-igcse-a-level` |
| `local-au-private-day` | Australia Private Day School | AU | `au-state-curriculum` |

Gulf + Latin America (3):

| key | name | supported_countries | local_profile_ref |
|---|---|---|---|
| `local-ae-gulf-international` | UAE Gulf International | AE | `ae-cbse-or-british` |
| `local-mx-private-bilingual` | Mexico Private Bilingual | MX | `mx-sep-bilingual` |
| `local-br-private-bilingual` | Brazil Private Bilingual | BR | `br-mec-bilingual` |

**Counts:** 10 + 8 + 8 + 6 + 6 + 4 + 8 + 25 = **75** templates. ✓

---

## 7 — Local heritage design system

### 7.1 Palette families (register in `static/css/design-tokens-local-*.css`)

Each palette family is a **set of semantic token overrides** that drop into the existing `:root[data-rmc-local-palette="<key>"]` selector — does NOT replace the base tokens.

| Family key | Anchor hue | Personality | Used by |
|---|---|---|---|
| `editorial-cream` | warm off-white | Editorial, premium, restrained | International, Bilingual, Faith-neutral, Cambridge |
| `warm-terracotta` | warm clay | Community, grounded, regional | West Africa, Latin America |
| `cool-indigo` | cool deep blue | Trust, ops, finance-first | Operator, Finance, Security |
| `green-emerald` | natural green | Growth, academics, family-warm | Tenant admin, Parent, Student |
| `desert-amber` | warm sand | Heritage, Gulf, premium-warm | UAE, Saudi, MENA |
| `monsoon-teal` | cool teal | South Asia coastal, monsoon | India coastal states, Sri Lanka, Bangladesh |
| `sakura-blush` | restrained pink | Japan/Korea minimalist | East Asia international |
| `andes-clay` | warm earth | Latin America heritage | Mexico, Brazil, Argentina, Colombia |
| `savanna-ochre` | warm yellow | East Africa community | Kenya, Tanzania, Uganda |
| `nordic-slate` | cool grey | Compact, low-saturation operations | Low-connectivity, compact mobile |

**Hard rule:** every literal hex in these palette files MUST sit inside a `:root[data-rmc-local-palette="<key>"]` selector OR carry `/* off-token-allow: local-palette-anchor */`. The `scan_off_token_colors` gate baseline 0 stays held.

### 7.2 Typography families

Three reusable stacks; assigned per palette family. Never fork outside this set without an explicit allow marker.

- `stack-editorial-serif` — Source Serif 4 + Inter fallback
- `stack-system-sans` — Inter + system stack
- `stack-bilingual-mixed` — Inter + Noto Sans (for IN/CN/JP/KR/AR/HE labels)

### 7.3 Calendar / academic system tokens

Existing `_INDIA_STATE_BOARD_CALENDAR_VARIANTS` and `country_localization_service.py` already carry calendar metadata. Templates **read** from there — do not duplicate.

### 7.4 What is explicitly NOT in the heritage layer

- No flags in design (data-only).
- No religious or political imagery.
- No ethnic-coded color choices ("African colors", "Asian colors") — palettes are named by aesthetic/material, not by ethnicity.
- No language-direction assumptions baked into layout (RTL handled by existing `LOCALIZATION_RTL_ARCHITECTURE.md`).

---

## 8 — Apply / Customize / Rollback workflow

The user MUST see this exact flow before any apply is committed:

```
Browse ──► Preview ──► Compare (opt) ──► Apply Request ──► Confirm Impact ──► Apply ──► Audit Event ──► Rollback if needed
                                                  │
                                                  ▼
                                       Show:
                                       - pages that change
                                       - roles affected
                                       - modules required (✓/✗)
                                       - data requirements
                                       - tenant impact
                                       - mobile / a11y status
                                       - rollback availability
                                       - approval requirement (yes/no)
```

### 8.1 Customization scope (within a template, post-apply)

Operator/tenant can customize (within policy):
- brand colors (subject to WCAG snap from `services/ai_palette.py`)
- logo
- typography density
- card style
- dashboard blocks (add/remove from family-allowed list)
- role visibility per block
- default landing route
- compact vs rich mode

Customizations persist on `TemplateAssignment.customizations` JSON.

### 8.2 Rollback contract

- One-click rollback to previous `TemplateAssignment` (the snapshot lives in `rollback_snapshot`).
- Audit event `template.rolled_back` emitted.
- If rolling back across a schema migration boundary, refuse with a clear "schema-locked" error and surface the change-request path.

---

## 9 — AI recommendations (gateway-routed, NEVER hallucinated)

### 9.1 Service location

New module `apps/brand_experience/template_ai_recommender.py`. **All AI calls go through `services.ai_helpers.invoke_with_request`.** Boundary scanner enforces this.

### 9.2 Recommendation input

Composed from existing signals (do not re-query):
- `school.settings.country`, `school.settings.region`, `school.settings.primary_language` (already first-class from Wave 10)
- `school.modules_enabled`
- `school.connectivity_profile`
- `school.payment_maturity`
- `school.parent_engagement_signal`
- `school.migration_status`
- `request.user.role_target`

### 9.3 Recommendation output (typed)

```python
@dataclass
class TemplateRecommendation:
    primary: str            # template key
    why: str                # human-readable reason, EN + translated via gettext
    required_modules: list[str]
    missing_setup: list[str]
    preview_url: str
    risks: list[str]        # e.g. "low_connectivity_school_using_data_rich_template"
    alternatives: list[str] # top 2 alternative keys
    confidence: float       # 0..1, model-reported
```

### 9.4 Hard rules

- NEVER expose `operator_only=True` templates to a tenant request.
- NEVER recommend a template whose `required_modules` are not all enabled.
- NEVER fabricate template keys not in the registry — registry membership validated before returning.
- If AI provider unreachable, return a **deterministic rules-based fallback** (the same pattern as `services/ai_palette.py`).

---

## 10 — Tests + Verifiers (the bar that must be green to ship a wave)

### 10.1 New test modules

```
apps/brand_experience/tests/
    test_experience_template_registry.py        # 75 keys exist, unique, valid
    test_local_experience_profiles.py           # all referenced profiles exist
    test_template_assignment_model.py
    test_template_audit_event_append_only.py
    test_template_tenant_boundaries.py          # operator_only hidden from tenant
    test_template_apply_rollback.py
    test_template_ai_recommender.py             # boundary, fallback, registry-validation

apps/marketplace/tests/
    test_template_marketplace_catalog.py        # browse / filter / compare
    test_template_marketplace_ux_a11y.py

apps/platform_runtime/tests/
    test_template_live_previews.py              # every preview_view_name resolves + returns 200
    test_template_profile_coverage.py           # every required role has ≥1 template

apps/studio_os/tests/
    test_studio_os_template_integration.py      # Experience section exposes templates

apps/setup_studio/tests/
    test_tenant_studio_template_selection.py    # onboarding step works
```

### 10.2 New / extended verifiers

Add (or reuse where they exist):

| Verifier | Purpose | Baseline |
|---|---|---|
| `scripts/verify_experience_template_registry.py` | 75 keys, unique, valid composition refs, status enum sane | n/a (structural gate) |
| `scripts/verify_template_marketplace_routes.py` | every `preview_view_name`/`apply_view_name`/`rollback_view_name` resolves | n/a (existence gate) |
| `scripts/verify_template_tenant_boundaries.py` | `operator_only` set never appears in tenant URL responses | 0 |
| `scripts/verify_template_local_first_coverage.py` | every priority market has ≥1 local-first template | 25 markets covered (extend over time) |
| `scripts/verify_template_a11y_floor.py` | every `tenant_ready` template carries `accessibility_level ∈ {AA, AAA}` | 0 violations |
| `scripts/verify_template_ai_recommender_boundary.py` | `template_ai_recommender.py` imports only `services.ai_helpers`, never `services.ai_gateway` | 0 |

### 10.3 Existing verifiers / scanners that MUST stay green

Every wave runs these and refuses to ship if any regress:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `scripts/check_real_migration_drift.py`
- `scripts/verify_sot_batch_id_uniqueness.py`
- `scripts/verify_service_worker_version.py --check-monotonic`
- `scripts/verify_doc_plan_density_discipline.py`
- All 22 zero-tolerance scanners from CLAUDE.md (esp. `scan_off_token_colors 0`, `scan_undefined_css_classes 0`, `scan_inline_style_off_token 0`, `scan_theme_locked_token_text 0`, `scan_tenant_queryset_safety 0`, `scan_ai_gateway_boundary 0`, `scan_template_safety` clean, `scan_operator_shell_dead_hrefs 0`)
- `audit_template_render_safety.py`
- `audit_role_permission_matrix.py --max-candidate-anonymous 66`

### 10.4 Browser QA

`tests/e2e/template-marketplace.spec.js`:
- operator browses → filters by role → opens detail → triggers preview → confirms apply gate
- tenant browses → operator-only templates absent
- preview iframe renders + no horizontal overflow at 390/768/1366px
- rollback button present + functional after apply
- compare view side-by-side at 1366px

---

## 11 — Handoff state (start here if you're picking up cold)

**As of batch 1400 SHIPPED (2026-05-23, single-session execution):**

### 11.1 SHIPPED — all of the below is in the repo, run-verified at file level

- **Phase 0 audit:** DONE (§1 above; never redo).
- **75 ExperienceTemplate `PackContract` entries** in `apps/platform_runtime/pack_contract.py::EXPERIENCE_TEMPLATE_PACKS` via new `_tpl(...)` helper. PACK_TYPES extended; `_all_packs()` aggregator; `package_payload()` extended.
- **75-entry overlay registry** at `apps/brand_experience/experience_templates.py` — `ExperienceTemplateOverlay` frozen dataclass; `LAYOUT_FAMILY_NAMES` 1..10; 10 `PALETTE_FAMILIES`; 3 `TYPOGRAPHY_STACKS`; `OVERLAYS` tuple; `get_overlay`/`list_overlays`/`overlay_keys`/`assert_registry_invariants`.
- **25 LocalExperienceProfile** entries at `apps/siteconfig/local_experience_profiles.py`.
- **Operator URL surface** `/configuration/experience-templates/*` (6 paths) — wired in `configuration_urls.py` + `views_administration.PACK_ROUTE_TYPES`. Reuses existing pack lifecycle views — zero new view code.
- **Tenant URL surface** `/school/studio/templates/*` (8 routes) at `apps/brand_experience/{views,urls}_template_marketplace.py`. Mounted via include in `config/tenant_urls.py`. Every view enforces `_gate_operator_only()`.
- **AI recommender** `apps/brand_experience/template_ai_recommender.py` — gateway-routed via `services.ai_helpers` only; registry-validated; deterministic rules fallback.
- **6 marketplace templates** `templates/marketplace/{templates_browse,templates_detail,templates_preview_frame,templates_compare,templates_apply_confirm,_local_first_catalog}.html` + existing `pack_marketplace.html` extended with `experience-templates` branch.
- **Semantic-token CSS bundle** `static/css/rmc-template-marketplace.css` (~280 lines).
- **10 heritage palette families** consolidated in `static/css/design-tokens-local-palettes.css` (~120 lines, all anchors `/* off-token-allow: local-palette-anchor */`).
- **CSP-safe progressive enhancement JS** `static/js/_pages/rmc-template-marketplace.js` (idempotent IIFE).
- **6 verifier scripts** at `scripts/verify_experience_template_{registry,routes_renamed_to_marketplace_routes}.py` and four siblings — see §10.2 for the exact list.
- **24 SimpleTestCase tests** at `apps/brand_experience/tests/test_experience_template_registry.py`.
- **SW bumped** to `sms-v3.63.0-local-first-template-marketplace-wave-a-75-templates-25-profiles-10-palettes-2026-05-23`.
- **SOT batch 1400 entry** added at top of §11.4 forward queue in `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`.
- **Execution log slice** prepended to `RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`.
- **Memory index + body** updated in `MEMORY.md` + `project_local_first_template_marketplace_v3_63_0_2026_05_23.md`.

### 11.2 DELIBERATE deviations from this plan (declared, not stealth)

1. **10 palette CSS bundles consolidated into 1 file.** Plan §11 originally listed `design-tokens-local-{editorial-cream,warm-terracotta,...}.css` as 10 separate files. The behavior is identical when consolidated under `:root[data-rmc-local-palette="<family>"]` selectors. Split into per-family files in Wave B+ if there's a CDN-cache reason; until then the single bundle is correct.
2. **`TemplateAssignment` + `TemplateAuditEvent` first-class models NOT created.** `apps.packages.models.InstalledPackage` + `apps.packages.models.PackageChangeLog` already record everything the plan needed for the apply/audit chain. First-class template models are deferred to Wave B when `TemplateAssignment.customizations` JSON persistence needs something `InstalledPackage` doesn't cover.
3. **No new migration.** Direct consequence of (2). `python manage.py makemigrations --check --dry-run` should still report "No changes detected" post-this wave.

### 11.3 What an operator should run to verify

```
cd beta/school-management-system

python manage.py check --settings=config.settings
python manage.py makemigrations --check --dry-run --settings=config.settings

python scripts/verify_experience_template_registry.py
python scripts/verify_template_marketplace_routes.py
python scripts/verify_template_tenant_boundaries.py
python scripts/verify_template_local_first_coverage.py
python scripts/verify_template_a11y_floor.py
python scripts/verify_template_ai_recommender_boundary.py

# 22 zero-tolerance scanners must stay at 0:
python scripts/scan_off_token_colors.py --compare
python scripts/scan_undefined_css_classes.py --compare
python scripts/scan_inline_style_off_token.py --compare
python scripts/scan_theme_locked_token_text.py --compare
python scripts/scan_tenant_queryset_safety.py --compare
python scripts/scan_ai_gateway_boundary.py --compare
python scripts/audit_template_render_safety.py
python scripts/scan_operator_shell_dead_hrefs.py --strict
python scripts/verify_service_worker_version.py --check-monotonic

# 24 SimpleTestCase tests:
python manage.py test apps.brand_experience.tests.test_experience_template_registry --settings=config.settings --noinput --keepdb
```

### 11.4 Picking this up cold (if Wave B+ is your task)

1. Read §1.1 (existing systems) and §11.1 (what shipped) — do not redo any of that.
2. Pick a residual from §11.5 below.
3. Use the file paths in §11.1 to find the exact extension point.
4. Use §13 SOT/log/memory templates for closeout.
5. Update §11.5 to subtract what you completed.

### 11.5 Wave B+ residuals — burndown after batch 1401 (2026-05-23, SW v3.64.0)

**9 of 12 residuals SHIPPED; 3 of 12 are explicit external blockers (counsel + live LiteLLM gateway) with scaffolds + verifiers + counsel docket filed.**

| # | Residual | Status | Where it lives |
|---|---|---|---|
| 1 | Studio OS Experience-section template fold partial | **SHIPPED** | `templates/studio_os/partials/experience_templates_fold.html` |
| 2 | Setup Studio onboarding `select_experience_template` step | **SHIPPED** | `apps/setup_studio/services.py::STEP_DEFINITIONS` |
| 3 | `TemplateAssignment.customizations` first-class model + migration | **SHIPPED** | `apps/brand_experience/models_template.py` + `migrations/0004_template_assignment_and_audit_event.py` |
| 4 | `TemplateAuditEvent` first-class model | **SHIPPED** | Same file, append-only via `AppendOnlyModelMixin` + sanitized payload |
| 5 | Full Playwright at 390/768/1366 breakpoints | **SHIPPED** | `tests/e2e/template-marketplace.spec.js` |
| 6 | Side-by-side live-iframe compare view | **SHIPPED** | `templates/marketplace/templates_compare.html` extended with 2× `<iframe sandbox>` + CSS frame wrap |
| 7 | AI recommender live LiteLLM smoke | **VERIFIER SHIPPED + EXTERNAL BLOCKER for live** | `scripts/verify_template_ai_recommender_live_smoke.py` (passes as `TEMPLATE_AI_RECOMMENDER_FALLBACK_PASS` today; auto-upgrades to `TEMPLATE_AI_RECOMMENDER_LIVE_PASS` when `LITELLM_*` + `RMC_PRODUCT_MCP_ENABLED=1` configured on Render) |
| 8 | Partner-published templates | **MANIFEST SCAFFOLD SHIPPED + EXTERNAL BLOCKER for live** | `apps/marketplace/template_partner_manifest.py` + counsel docket at `docs/TEMPLATE_MARKETPLACE_WAVE_E_COUNSEL_PENDING.md` (6 gates) |
| 9 | Monetization billing pipeline | **MANIFEST SCAFFOLD SHIPPED + EXTERNAL BLOCKER for live** | `apps/marketplace/template_monetization_manifest.py` + same counsel docket + Stripe Connect onboarding |
| 10 | Per-family palette CSS file split | **SHIPPED (materialized live)** | `scripts/split_palette_bundles.py` ran live → 10/10 `static/css/design-tokens-local-<family>.css` files |
| 11 | Studio OS deep-link from Experience to operator catalog | **SHIPPED** | 3 entries added to `apps/studio_os/deep_links.py::_PATHS` |
| 12 | Per-template thumbnail SVGs (75 files) | **SHIPPED (materialized live)** | `scripts/generate_template_thumbnails.py` ran live → 75/75 `static/img/template-thumbs/<key>.svg` with 10 layout-family schematics |

**Plan §11.5 verdict:** **FULLY CLOSED IN-REPO.** Items 7/8/9 reach maximum repo-side completeness — actual go-live is gated on Lane 2 evidence (LiteLLM on Render) and counsel signoff (Wave E+).

### 11.6 Files this wave created or edited (verbatim — match against `git status` to spot drift)

See `project_local_first_template_marketplace_v3_63_0_2026_05_23.md` in auto-memory for the exact verbatim list (28 files).

**Files you will create or edit (cumulative across all 4 waves):**

```
apps/brand_experience/experience_templates.py            (NEW — registry)
apps/brand_experience/template_ai_recommender.py         (NEW)
apps/brand_experience/models.py                          (EXTEND — TemplateAssignment + TemplateAuditEvent)
apps/brand_experience/urls_marketplace.py                (NEW — tenant routes)
apps/brand_experience/views_marketplace.py               (NEW)
apps/brand_experience/views_template_apply.py            (NEW — delegates to platform_runtime.pack_apply)
apps/brand_experience/views_template_rollback.py         (NEW — delegates to platform_runtime.pack_rollback)
apps/brand_experience/migrations/00NN_template_assignment_and_audit.py  (NEW — single leaf)

apps/siteconfig/local_experience_profiles.py             (NEW — registry)

apps/platform_runtime/configuration_urls.py              (EXTEND — operator routes)

apps/studio_os/navigation.py                             (EXTEND — Experience section fold)
apps/studio_os/views.py                                  (EXTEND — context for new fold)
templates/studio_os/partials/experience_templates_fold.html (NEW)

apps/setup_studio/services.py                            (EXTEND — new step)
apps/setup_studio/models.py                              (review — may not need changes)
templates/setup_studio/steps/select_experience_template.html (NEW)

templates/marketplace/templates_browse.html              (NEW)
templates/marketplace/templates_detail.html              (NEW)
templates/marketplace/templates_preview_frame.html       (NEW)
templates/marketplace/templates_compare.html             (NEW)
templates/marketplace/templates_apply_confirm.html       (NEW)
templates/marketplace/_template_card.html                (NEW)
templates/marketplace/_template_filter_rail.html         (NEW)
templates/marketplace/_local_first_catalog.html          (NEW)

static/css/rmc-template-marketplace.css                  (NEW — semantic tokens only)
static/css/design-tokens-local-editorial-cream.css       (NEW)
static/css/design-tokens-local-warm-terracotta.css       (NEW)
static/css/design-tokens-local-cool-indigo.css           (NEW)
static/css/design-tokens-local-green-emerald.css         (NEW)
static/css/design-tokens-local-desert-amber.css          (NEW)
static/css/design-tokens-local-monsoon-teal.css          (NEW)
static/css/design-tokens-local-sakura-blush.css          (NEW)
static/css/design-tokens-local-andes-clay.css            (NEW)
static/css/design-tokens-local-savanna-ochre.css         (NEW)
static/css/design-tokens-local-nordic-slate.css          (NEW)
static/css/rmc-class-grammar.css                         (EXTEND — define every new .rmc-* class)

static/js/_pages/rmc-template-marketplace.js             (NEW — CSP-nonce-safe, armed-attribute compliant)

static/js/service-worker.js                              (BUMP CACHE_VERSION per wave)

docs/architecture/RUNMYCAMPUS_LOCAL_FIRST_TEMPLATE_MARKETPLACE.md  (NEW)
docs/generated/local_first_template_marketplace_code_truth_inventory.{json,md}  (NEW)
docs/generated/local_first_template_marketplace_architecture_audit.{json,md}    (NEW)
docs/generated/local_first_template_catalog_75_premium.{json,md}                (NEW)
docs/generated/local_first_template_profile_coverage_matrix.{json,md}           (NEW)
docs/generated/local_first_template_live_preview_engine_audit.{json,md}         (NEW)
docs/generated/local_first_template_studio_os_integration.{json,md}             (NEW)
docs/generated/local_first_template_tenant_studio_integration.{json,md}         (NEW)
docs/generated/local_first_template_apply_customize_rollback_audit.{json,md}    (NEW)
docs/generated/local_first_template_ai_recommendation_audit.{json,md}           (NEW)
docs/generated/local_first_template_marketplace_ux_audit.{json,md}              (NEW)
docs/generated/local_first_template_marketplace_browser_qa_report.{json,md}     (NEW)
docs/generated/local_heritage_design_system.{json,md}                           (NEW)

tests/e2e/template-marketplace.spec.js                   (NEW)

scripts/verify_experience_template_registry.py           (NEW)
scripts/verify_template_marketplace_routes.py            (NEW)
scripts/verify_template_tenant_boundaries.py             (NEW)
scripts/verify_template_local_first_coverage.py          (NEW)
scripts/verify_template_a11y_floor.py                    (NEW)
scripts/verify_template_ai_recommender_boundary.py       (NEW)

.github/workflows/template-marketplace-gates.yml         (NEW — gate the new verifiers in CI, retention-days: 1 on any artifact upload)
```

**Important DO NOT TOUCH list:**
- `services/ai_gateway.py` — gateway boundary
- `services/ai_helpers.py` — only consumer surface
- `ai/Modelfile` — model contract
- `apps/schools/super_views_create_school_wizard.py` — preserved
- Any `apps/migration_cloud/*` (separate program track)

---

## 12 — Wave breakdown

Each wave is one batch ID, one SW bump, one SOT entry, one log entry, one memory file. Each wave is a 3- to 5-agent parallel fan-out where boundaries allow.

### Wave A (batch 1400, target `sms-v3.63.0`): Registry + 25 operator/admin templates + apply/rollback core

**Scope:**
- `ExperienceTemplate` registry module + first 25 templates (A. Operator 10 + B. Tenant admin 8 + C. Teacher 7).
- `LocalExperienceProfile` registry skeleton (10 palette families + typography stacks; profile entries are stubbed for Wave B+).
- `TemplateAssignment` + `TemplateAuditEvent` models + single migration.
- Operator routes under `/configuration/templates/*` (browse + detail + preview + apply + rollback).
- Reuse `platform_runtime.pack_apply` / `pack_rollback` — no new lifecycle code.
- Marketplace browse + detail templates with semantic tokens only.
- Verifiers: `verify_experience_template_registry.py` + `verify_template_marketplace_routes.py` + `verify_template_tenant_boundaries.py`.

**Honest deferred at Wave A close:** tenant routes (Wave B), local-first overlays not yet wired (Wave C), AI recommender (Wave D).

### Wave B (batch 1401, target `sms-v3.64.0`): Tenant catalog + 25 more templates + customization

**Scope:**
- Tenant routes under `/school/studio/templates/*` (full surface).
- Templates D. Parent 6 + E. Student 6 + F. Staff 4 + G. Specialized 8 + 1 remaining teacher = 25.
- Customization view + persistence on `TemplateAssignment.customizations`.
- Setup Studio onboarding step wired.
- Studio OS Experience fold wired.
- Verifier: `verify_template_a11y_floor.py`.

### Wave C (batch 1402, target `sms-v3.65.0`): 25 local-first regional templates + heritage palettes

**Scope:**
- All 25 H. Local-First Regional templates.
- All 10 palette families landed (the 10 `design-tokens-local-*.css` files).
- All `LocalExperienceProfile` entries populated.
- Local-first catalog routes.
- Verifier: `verify_template_local_first_coverage.py`.
- AI input signals wired into recommender (recommender itself can stay stubbed).

### Wave D (batch 1403, target `sms-v3.66.0`): AI recommender + browser QA + monetization architecture (stubbed)

**Scope:**
- `template_ai_recommender.py` live, routed through `services.ai_helpers`, with rules-based fallback.
- Recommendation UI on tenant + operator marketplaces.
- `tests/e2e/template-marketplace.spec.js` full Playwright suite.
- Compare view fully functional with side-by-side preview.
- Monetization architecture STUBBED (manifest fields only, no billing pipeline — that's a separate Wave E+ program after counsel review).
- Verifier: `verify_template_ai_recommender_boundary.py`.

### Wave E+ (NOT in this plan)

Reserved for: partner-published templates, monetization billing pipeline, per-template paid tier, marketplace settlement state machine, live tenant rollout. **Do not start without counsel signoff + the Wave A-D body of evidence shipped.**

---

## 13 — SOT + log update templates (use these EXACTLY when shipping each wave)

### 13.1 SOT entry template (insert at top of `§11.4 forward queue` in `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`)

```
**§11.4 forward queue - batch 1400 (Local-First Template Marketplace Wave A — registry + 25 templates + apply/rollback core - YYYY-MM-DD):** **DONE (Lane 1, repo-scope)** — Plan at [`docs/plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md`](plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md). **Shipped:** ExperienceTemplate registry at `apps/brand_experience/experience_templates.py` (25 keys: operator 10 + admin 8 + teacher 7); LocalExperienceProfile skeleton; TemplateAssignment + TemplateAuditEvent models (migration `00NN_template_assignment_and_audit`); operator routes `/configuration/templates/{,<key>/,<key>/preview/,<key>/apply/,<key>/rollback/}`; marketplace browse + detail templates; semantic-token-only CSS bundle `rmc-template-marketplace.css`. **Reuses (NOT duplicated):** `platform_runtime.pack_apply` + `pack_rollback` + `pack_preview` + `live_preview`; `brand_experience.experience_packs` + `ThemePack`; `marketplace.pack_registry`; `cockpit_context._deep_merge` for overrides. **Proof:** `verify_experience_template_registry.py` PASS (25/25); `verify_template_marketplace_routes.py` PASS; `verify_template_tenant_boundaries.py` PASS; `python manage.py check` clean; `makemigrations --check --dry-run` "No changes detected" post-0NN; all 22 zero-tolerance scanners 0; `audit_template_render_safety.py` 0; SW `sms-v3.63.0-local-first-template-marketplace-wave-a-YYYY-MM-DD`. **Honest residual (Wave B+):** tenant routes; remaining 50 templates; local-first palettes; AI recommender; full browser QA. **Verdict:** **TEMPLATE MARKETPLACE PARTIAL — WAVE A SHIPPED, REPO SCOPE**.
```

(Replicate for batches 1401, 1402, 1403 with their wave scope.)

### 13.2 Log entry template (prepend to `RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`)

```
## Slice — batch 1400 Local-First Template Marketplace Wave A (YYYY-MM-DD)

**A. Scope:** Registry + first 25 templates + apply/rollback core wired through existing pack lifecycle. Plan: [`docs/plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md`](../docs/plans/LOCAL_FIRST_TEMPLATE_MARKETPLACE_PLAN.md).

**B. Shipped:** [list]

**C. Proof:** [verifier output lines]

**D. Residual (Wave B+):** [list]

**E. Plan:** Wave A todos completed; Wave B begins at batch 1401.

**F. Headline:** **TEMPLATE MARKETPLACE PARTIAL — WAVE A SHIPPED, REPO SCOPE**
```

### 13.3 Memory entry (auto-memory, one file per wave)

Path: `C:\Users\yimga\.claude\projects\c--Users-yimga-Documents-HY-DOC-MAINPC-Docs-for-Others-Friends-family-Gilead-Tech-High\memory\project_local_first_template_marketplace_wave_a_vN.M.x_YYYY_MM_DD.md`

Memory index one-liner (in `MEMORY.md`):

```
- [Local-First Template Marketplace Wave A vN.M.x YYYY-MM-DD](project_local_first_template_marketplace_wave_a_vN_M_x_YYYY_MM_DD.md) — SHIPPED ...
```

---

## 14 — Final verdict criteria

After all 4 waves:

- **FAILURE** if any wave shipped with a zero-tolerance scanner regression OR introduced `href="#"` OR exposed operator-only templates to tenants.
- **TEMPLATE MARKETPLACE PARTIAL** if Wave A and Wave B shipped but local-first catalog or AI recommender deferred.
- **TEMPLATE MARKETPLACE READY — FOCUSED REPO SCOPE** if all 4 waves shipped with all verifiers green, but no live tenant rollout claimed.
- **75 PREMIUM TEMPLATE SYSTEM READY — REPO SCOPE** is the program-complete verdict: 75 templates, 25 local-first profiles, AI recommender live, browser QA passing, no live monetization claim.

---

## 15 — External blockers (NOT code-fixable; do not block waves on these)

| Blocker | Affected scope | Defer until |
|---|---|---|
| Partner template publishing pipeline | Wave E+ monetization | Counsel signoff + Lane 2 evidence |
| Live tenant rollout to >1 production school using a non-default template | Composite verdict | Pilot scorecard + Render evidence per §13.7 of SOT |
| Per-template paid tier billing | Wave E+ monetization | Stripe settlement + counsel review |
| Real-tenant Playwright over Render (vs local) | Browser QA composite | Render SHA parity per §13 SOT |
| Sentry alert rule snapshot for new template-marketplace transactions | Drift detector | Operator runs `export_sentry_alert_rules` |
| MaxMind .mmdb mounted in production for local-first geo-default | Local-first sign-up auto-pick | Operator action per `docs/GEOIP_DEPLOYMENT.md` (already documented in Wave 12) |

---

## 16 — Cleanliness checklist (run at every wave close)

```
git status --short
git diff --stat
git diff --check
```

Ensure no:
- .env files, DB files, logs, screenshots (unless intentionally ignored)
- private data, secrets
- raw AI prompt logs with PII
- service worker version regression (`verify_service_worker_version.py --check-monotonic`)
- SOT batch ID duplicate (`verify_sot_batch_id_uniqueness.py`)

---

**End of plan. This document is intentionally self-contained so a fresh Claude / Codex / Cursor session can pick it up cold by reading §1 (audit) → §11 (handoff state) → §12 (wave to ship) → §13 (closeout template).**
