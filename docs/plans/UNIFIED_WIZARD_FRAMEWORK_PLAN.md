# Unified Wizard Framework + 18-Wizard Rollout — execution plan

**Status:** **PLANNED** (audit + design complete, no code shipped). 2026-05-26.
**Plan owner:** RunMyCampus platform team
**Target SW range:** `sms-v3.65.x` (Phase 1 engine + 5 foundation wizards) → `sms-v3.67.x` (Phase 3 closeout)
**Batch IDs to reserve:** 1410 (Phase 1) / 1411 (Phase 2) / 1412 (Phase 3)
**Plan scope:** **REPO ONLY** at design time. Per-wizard live wiring (Stripe Connect e-invoicing handshake, WhatsApp gateway, etc.) is gated separately.
**Handoff-ready for:** Claude Code, Codex, Cursor — this file is self-contained.

---

## 0 — Why this exists and how to read this file

The user surfaced a 30+ wizard catalog (operator sovereignty, FinTech, grading, compliance, migration, omnichannel comms, AI helpcenter, transit, marketplace, cashless POS, HR, safeguarding, dormitory, analytics, whitelabel, plus 8 daily-stakeholder wizards). A platform-wide audit (see §1) confirmed that **most of the underlying capability already exists across the 53 Django apps in `apps/`** — what's missing is a **single coherent wizard surface** that turns existing configuration scattered across siteconfig, studio_os, brand_experience, billing, migration_cloud, etc. into branching, conditional, AI-augmented step trees.

The plan answers three questions:

1. **Do we need wizards?** Yes — but **one wizard engine, not 30 bespoke wizards**.
2. **Will they help with configuration?** Yes — they collapse multi-page tenant-admin scavenger hunts into linear stepped flows and they expose the existing `setup_studio` recommendations layer to operators for the first time.
3. **How does AI play a role?** AI runs through `services.ai_helpers` (boundary scanner stays green) and provides **smart defaults**, **branching rationale**, **natural-language intake**, **translation mesh**, and **proactive recommendations** drawn from `SetupProgress.recommendations` — which is modeled today but never AI-refreshed or rendered.

**If you are picking this up from Codex/Cursor:** start at §11 (Handoff state). The rest of the doc tells you why each choice was made so you can extend without re-litigating.

---

## 1 — Phase 0 audit findings (already done — do NOT re-audit)

### 1.1 Existing platform systems we will REUSE (not duplicate)

| System | Path | Why it matters |
|---|---|---|
| **Setup Studio service layer** | `apps/setup_studio/services.py`, `models.py` | `STEP_DEFINITIONS` tuple at `services.py:13` already declares 8 setup steps with key/label/description/step_group/link_name/weight/recommended_choice. `SetupProgress` model already JSONFields `step_state`, `recommendations`, `role_previews`, `launch_checklist`, `launch_blockers`, `health_score`, `health_breakdown`. **NO UI EXISTS YET.** This is the foundation. |
| **Lifecycle spine + concierge** | `apps/lifecycle/`, `templates/lifecycle/concierge_modal.html`, `views_rapid_create.py` | Concierge modal + 4-card school template picker + rapid-create flow shipped in [[project-lifecycle-360-10x-v3-61-2026-05-22]] and [[project-signup-creation-2-v3-61-6-v3-61-9-2026-05-22]]. Wizards land NEXT TO this — they don't replace it. |
| **Onboarding step catalog** | `apps/siteconfig/onboarding_step_catalog.py`, `views_school_onboarding.py`, `templates/siteconfig/onboarding*.html` | 30+ declarative steps with audience/required/effort flags + deep-link CTAs + per-blueprint overrides. Live-state completion tracking, not a wizard stepper. Wizard engine reads this catalog. |
| **Persona onboarding wizards (partial)** | `templates/student/onboarding_wizard.html`, `templates/teacher/onboarding_wizard.html` | 5-step steppers for student + teacher exist today. Parent + staff symmetric wizards are MISSING and land in Phase 1. |
| **Studio OS shell** | `apps/studio_os/navigation.py`, `views.py`, `deep_links.py`, `copilot_rail_service.py` | 6-mode operator cockpit (Overview/Experience/Automation/Output/Launch/Control) per [[project-studio-os-next-realm-v3-54-2026-05-21]]. Operator wizards live in Launch mode. Copilot rail provides reactive chat; wizard engine wires it to active step. |
| **AI helper bridge** | `services/ai_helpers.py::invoke_with_request`, `normalize_gateway_metadata`, `record_feedback` | Single permitted path for `apps/` code to reach LLMs. `apps/` must NOT import `services.ai_gateway` directly — `scan_ai_gateway_boundary.py` baseline 0 enforces. |
| **AI deployment posture** | `services/ai_deployment_posture.py`, `docs/AI_DEPLOYMENT_POSTURE.md` | Maps `RMC_DEPLOYMENT_PROFILE` → cloud (LiteLLM) or edge (Ollama). Wizard AI inherits this transparently. |
| **Local-first cascade** | `apps/siteconfig/_seed_country_languages.py`, `CountryRegistry`, `LocalExperienceProfile`, `local_experience_profiles.py` | 51 markets with marketing voice, 25 LocalExperienceProfile entries, 10 heritage palettes, per-state India variants, Chinese myriad grouping, Indian lakh-crore grouping, GeoIP integration. Wizards inherit jurisdiction context from this layer — they do NOT re-source country/region data. |
| **7-layer cascade contract** | `apps/platform_runtime/runtime_defaults_first_class.py`, `apps/siteconfig/domain_ownership.py` | `RuntimeDefaults` typed column → migration → `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES` → `EXACT_FIELD_OWNERS` → `SiteSettings.brand_payload` → context processor → meta-tag bridge → CSS custom property. Every wizard answer routes through this — never hardcoded. |
| **Template Marketplace + 150 templates** | `apps/platform_runtime/pack_contract.py`, `apps/brand_experience/views_template_marketplace.py`, `apps/siteconfig/local_experience_profiles.py` | Per [[project-local-first-template-marketplace-waves-bcde-v3-64-0-2026-05-23]] and follow-ons. Whitelabel wizard composes ExperienceTemplate selection; doesn't re-implement. |
| **Migration Cloud platform** | `apps/migration_cloud/` (9 consecutive waves through v3.39) | Companion siblings (extension + Tauri + Docker), MAA v1.0 + draft v2.0, append-only audit chain with HMAC-SHA512 root signatures, REST API alpha, webhook verifier SDKs, per-vendor extractors (PowerSchool/Blackbaud/Veracross/Alma; FACTS/Skyward read-only). Legacy Data Extraction wizard is a thin UX skin over this. |
| **Stripe Connect plan** | `docs/plans/STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md`, `docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md` | Settlement infrastructure is planned. FinTech wizard composes against it; e-invoicing handshake (ZATCA/SAT) is the new step the wizard surfaces. |
| **Brand Experience tokens + palettes** | `apps/brand_experience/`, `static/css/design-tokens.css`, `static/css/design-tokens-local-palettes.css` | Complete tokenization + 10 heritage palette families + PWA + Studio OS Experience mode. Whitelabel wizard = thin stepper over this. |
| **Schoolops meal plan + low-balance** | `apps/schoolops/models.py`, `signals.py`, `tasks.py::notify_low_meal_plan_balance` | Cashless POS wizard wires terminal registration + allergen mapping; meal_plan model + low-balance signal + 7-day cooldown shipped in v3.32. |
| **Customer Success + copilot rail** | `apps/customersuccess/`, `templates/customersuccess/support_copilot.html`, `apps/studio_os/copilot_rail_service.py` | AI Helpcenter wizard intakes PDFs/policies and embeds against this. No `apps/helpcenter/` exists — use `customersuccess`. |

### 1.2 What is MISSING (the actual work of this plan)

1. A **Unified Wizard Engine** (Python registry + JSON branching schema + view layer + state cache + AI integration + mobile-locked layout) that lives in `apps/setup_studio/wizard_engine.py` + `apps/setup_studio/wizard_views.py`.
2. The **18 wizard JSON definitions** themselves (registry entries composing existing apps; **NO hardcoded HTML duplicates**).
3. The **Parent + Staff persona wizards** symmetric to existing student + teacher.
4. The **AI recommendation layer** on `SetupProgress.recommendations` (modeled today, never AI-refreshed, never rendered).
5. **Master `.rmc-wizard-shell` class** in `static/css/rmc-class-grammar.css` + `.rmc-wizard-stepper`, `.rmc-wizard-pane`, `.rmc-wizard-nav` siblings.
6. **State cache contract** (localStorage with per-school + per-wizard-key TTL, survives back-nav, schema versioned).
7. **Wizard JSON branching schema** documented at `docs/WIZARD_BRANCHING_SCHEMA.md` (Phase 1 deliverable).
8. **Tests + verifiers** for engine + each wizard.

### 1.3 What is EXPLICITLY out of scope

- **Three wizards from the user's catalog are deferred** pending new modules: Real-Time Smart Transit & Geo-Fence (needs `apps/transport_fleet/`), Localized Activity & Asset Marketplace QR-Code Sticker subsystem (needs `apps/asset_tracker/`), High-Density Dormitory & Residential Lifecycle (needs `apps/logistics/` or schoolops extension). Not in Phase 1-3.
- **Four wizards from the user's catalog are dropped** as wrong-shape: Contextual Quick-Grade (daily-use teacher form), Mobile Money Fee & Invoice Settlement (payment flow, not config), Async Medical Emergency & Absence Notification (3-tap form), Cashless Campus Onboarding student-side (sub-flow of operator-side, not separate wizard).
- **Live FinTech wiring** — e-invoicing handshake (ZATCA/SAT) UI lands; actual cert upload + live submission is gated on Stripe Connect plan delivery.
- **Live WhatsApp / USSD gateway provisioning** — wizard UI lands; gateway accounts provisioned per tenant outside this plan.
- **AI Helpcenter live embeddings** — PDF intake UI + embedding scaffold lands; per-tenant vector store provisioning depends on AI deployment posture (cloud LiteLLM vs edge Ollama).
- **New top-level Django app** — everything fits into existing `apps/setup_studio/` (engine) + per-domain apps (each wizard's logic lives in its native app).

### 1.4 Non-negotiable constraints from CLAUDE.md (do not re-litigate)

- **No hardcoding** — every wizard answer routes through the 7-layer configurability contract. Country lists, school types, payment vendors, role strings — all pull from existing registries.
- **Apple-tier polish** — every new CSS uses semantic tokens (`var(--surface-*)`, `var(--text-*)`, `var(--hairline)`, etc.). `scan_off_token_colors` baseline 0 must hold.
- **`scan_undefined_css_classes` baseline 0** — every `.rmc-wizard-*` class referenced in new templates MUST exist in `static/css/rmc-class-grammar.css` or a sibling bundle.
- **`scan_template_safety` clean** — no multi-line `{# … #}`; use `{% comment %}…{% endcomment %}`.
- **No `href="#"`, no `javascript:void(0)`** — `scan_operator_shell_dead_hrefs` enforces.
- **`scan_tenant_queryset_safety` baseline 0** — every queryset on tenant-scoped models (Wizard state per-school) carries `school=` / `school_id=` / `school__isnull=` OR a 3+-part-hyphenated `# tenant-isolation-allow: <reason>` marker. Sister gate `scan_tenant_isolation_marker_quality` baseline 0 enforces marker quality.
- **Role strings** — never literal "ADMIN"/"TEACHER"/"PARENT"/"STUDENT"/"PROPRIETOR". Use `User.Role` enum or `apps.platform_runtime.role_registry`.
- **Service worker version** — bump `CACHE_VERSION` to `sms-vX.Y.Z-<slug>-<YYYY-MM-DD>` on every wave shipping new CSS/JS. Monotonic — `verify_service_worker_version.py --check-monotonic` enforces.
- **AI gateway boundary** — wizard AI MUST route through `services.ai_helpers`, NEVER `services.ai_gateway` directly. `scan_ai_gateway_boundary.py` baseline 0 enforces.
- **PII logging smell** — `scan_pii_logging_smell.py` baseline 0. Wizard step inputs may include guardian phone, payment IDs, identity numbers — NEVER log them as interpolated f-string values.
- **Money never float** — `scan_money_float.py` baseline 0. FinTech wizard step state stores monetary values as Decimal (`apps/finance/json_decimal.py::amount_str` for serialization).
- **CSP nonce + SRI required** — `verify_csp_nonce_emission.py` + `scan_sri_required.py` both baseline 0. Wizard JS that's external (state cache, branching helpers) lands with `nonce="{{ csp_nonce }}"` + SRI on any CDN asset (we self-host where possible).

---

## 2 — Architecture: the Unified Wizard Engine

### 2.1 The engine in one diagram

```
                   ┌─────────────────────────────────────────────────────────┐
                   │              wizard_engine.py (orchestrator)            │
                   │                                                         │
                   │  WIZARD_REGISTRY: dict[wizard_key, WizardDefinition]    │
                   │  StepDefinition  : key/audience/branching/ai_recommend  │
                   │  resolve_next_step(wizard_key, state) -> StepDefinition │
                   │  apply_step(wizard_key, step_key, payload) -> Result    │
                   │  request_ai_recommendation(step) -> dict                │
                   └─────────────────────────────────────────────────────────┘
                                            │
                ┌───────────────────────────┼───────────────────────────────┐
                ▼                           ▼                               ▼
   ┌─────────────────────────┐ ┌───────────────────────────┐ ┌──────────────────────────┐
   │ setup_studio.           │ │ services.ai_helpers       │ │ wizard_state_cache.js    │
   │ SetupProgress           │ │ (gateway-routed)          │ │ (localStorage, per-key,  │
   │  • step_state JSON      │ │  • smart_defaults()       │ │   schema-versioned)      │
   │  • recommendations JSON │ │  • branch_rationale()     │ │                          │
   │  • health_score         │ │  • intake_classify()      │ │                          │
   │  • launch_checklist     │ │  • translate_mesh()       │ │                          │
   └─────────────────────────┘ └───────────────────────────┘ └──────────────────────────┘
                │                                                          │
                ▼                                                          ▼
   ┌────────────────────────────────────────────────────────────────────────────────────┐
   │              Two surface skins (one template per audience)                         │
   │                                                                                    │
   │  Operator: templates/setup_studio/operator_wizard.html                             │
   │            extends: control_plane_skeleton.html                                    │
   │            mounted at /super/wizards/<wizard_key>/[<step_key>/]                    │
   │                                                                                    │
   │  Tenant:   templates/setup_studio/tenant_wizard.html                               │
   │            extends: portal_base.html                                               │
   │            mounted at /school/studio/wizards/<wizard_key>/[<step_key>/]            │
   │                                                                                    │
   │  Persona:  reuses tenant skin for parent + staff wizards (Phase 1 deliverable)     │
   └────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data model — what gets added vs reused

**REUSE (no migrations):**

- `apps/setup_studio/models.py::SetupProgress` already holds `step_state`, `recommendations`, `launch_checklist`, `launch_blockers`, `health_score`, `health_breakdown`, `current_step_key`, `completed_keys`. Each wizard run = one `SetupProgress` row per school with `step_state[wizard_key]` namespacing.
- `apps/siteconfig/SiteSettings.cockpit_payload` already exists for tenant-wide configuration overrides; wizard answers that resolve to tenant config write here through the existing form layer (Wave 13/15 patterns).
- `apps/lifecycle/SchoolLifecycleStage` already tracks lifecycle phase; wizard completion advances stage where applicable.

**NEW (NO migrations — pure code):**

- `apps/setup_studio/wizard_engine.py` (~600 lines) — registry + branching + AI integration.
- `apps/setup_studio/wizard_views.py` (~400 lines) — operator + tenant CBVs.
- `apps/setup_studio/wizard_state_resolver.py` (~150 lines) — pure resolver, no DB writes, ergonomic for tests.
- `apps/setup_studio/wizard_ai.py` (~200 lines) — `request_smart_defaults`, `request_branch_rationale`, `request_translate_mesh`, all routed via `services.ai_helpers`.
- `apps/setup_studio/wizards/` directory — one JSON file per wizard (18 files; each ~150 LOC of JSON).
- `apps/setup_studio/urls_wizards.py` — operator + tenant URL maps, included from `siteconfig:super` namespace and `studio_os:tenant` namespace.

**State namespacing (CRITICAL):**

```python
SetupProgress.step_state = {
    "select_experience_template": {...},   # legacy single-step state preserved
    "wizards": {
        "<wizard_key>": {
            "current_step_key": "...",
            "answers": {"<step_key>": {...}, ...},
            "completed": ["...", ...],
            "schema_version": 1,
            "ai_recommendations_cache": {...},
            "last_modified": "<iso>",
        },
        ...
    },
}
```

This means a school can have multiple wizards in-flight simultaneously without state collision, and the existing setup_studio step lifecycle stays untouched.

### 2.3 JSON branching schema (the single source of truth for every wizard)

Every wizard is a JSON file at `apps/setup_studio/wizards/<wizard_key>.json` matching this schema (formal schema lives at `docs/WIZARD_BRANCHING_SCHEMA.md` after Phase 1):

```json
{
  "wizard_key": "local_first_fintech_tax_matrix",
  "version": 1,
  "audience": ["operator", "tenant_admin"],
  "label_token": "wizards.local_first_fintech_tax_matrix.label",
  "description_token": "wizards.local_first_fintech_tax_matrix.description",
  "icon_class": "rmc-icon-finance",
  "estimated_minutes": 8,
  "gates": {
    "permission_codename": "billing.change_paymentsettings",
    "feature_flag": "wizard.fintech_matrix",
    "prerequisite_wizard": "multi_campus_sovereignty"
  },
  "ai": {
    "smart_defaults": true,
    "branch_rationale": true,
    "translate_mesh": false
  },
  "steps": [
    {
      "key": "settlement_destination",
      "label_token": "...",
      "input_type": "single_choice",
      "options_resolver": "apps.platform_runtime.country_registry::list_settlement_countries",
      "ai_recommend": {
        "enabled": true,
        "context_keys": ["primary_language", "country_code", "school_type"]
      },
      "next_step_resolver": "apps.setup_studio.wizard_engine::next_after_settlement"
    },
    {
      "key": "apm_integration",
      "input_type": "branched_single_choice",
      "branches": {
        "BR": "pix_setup",
        "IN": "upi_setup",
        "KE|TZ|UG|GH": "mpesa_setup",
        "default": "stripe_setup"
      }
    },
    {"key": "split_ledger_allocation", "...": "..."},
    {"key": "e_invoicing_handshake", "...": "..."}
  ]
}
```

**Key contracts the schema enforces:**

1. `options_resolver` is a Python dotted path to a callable returning `list[{value, label_token, metadata}]`. **NO hardcoded option lists in JSON** — they must resolve through the 7-layer cascade.
2. `next_step_resolver` is a Python dotted path to a callable that takes `(progress, current_answers)` and returns the next `step_key` (or `None` for end-of-wizard).
3. `ai_recommend.context_keys` lists which prior-step answers + tenant-context fields ride along to `services.ai_helpers` — keeps PII out of AI by default, opt-in fields explicit.
4. Branching is **declarative for simple cases** (`branches` dict) and **callable for complex cases** (`next_step_resolver`). This is the lesson from the studio_os deep-link work — keep simple things declarative.

### 2.4 The frontend: `.rmc-wizard-*` class grammar

New entries in `static/css/rmc-class-grammar.css` + new bundle `static/css/rmc-wizard.css`:

```
.rmc-wizard-shell           — 100dvh-locked container, mobile-safe
.rmc-wizard-shell--operator — dark-shell variant (control_plane)
.rmc-wizard-shell--tenant   — light-shell variant (portal)
.rmc-wizard-stepper         — top progress bar; auto-collapses to dots <768px
.rmc-wizard-pane            — current step content card
.rmc-wizard-pane__title     — H2 step title, var(--type-size-h2)
.rmc-wizard-pane__body      — form fields region; flex column, gap var(--space-3)
.rmc-wizard-pane__rationale — AI-provided branch rationale (collapsible)
.rmc-wizard-nav             — bottom button row (back / save-draft / next)
.rmc-wizard-nav__back       — secondary button
.rmc-wizard-nav__next       — primary button; disabled when validation fails
.rmc-wizard-nav__save-draft — tertiary; explicit save (state cache is implicit)
.rmc-wizard-help-rail       — right-side copilot rail (desktop only)
```

All classes use semantic tokens (`var(--surface-elevated)`, `var(--text-primary)`, `var(--hairline)`, `var(--elev-2)`, etc.). Mobile breakpoint: `@media (max-width: 768px) { .rmc-wizard-stepper { ... dots layout ... } }`. Reduced motion honored on all transitions. RTL-safe via `padding-inline-*` rather than `padding-left/right`.

### 2.5 The state cache (CSP-safe IIFE)

`static/js/rmc-wizard-state-cache.js` — external file so CSP nonce works:

- Keys: `rmc.wizard.<school_id>.<wizard_key>.v<schema_version>`.
- Storage: `localStorage` (survives reload, scoped to origin).
- TTL: 30 days; cleared on wizard completion or explicit reset.
- Schema: `{ answers: {<step_key>: <payload>}, last_step_key: "...", saved_at: "<iso>", schema_version: N }`.
- Server-side authoritative; client cache is convenience for back-nav and unstable-connection survival.
- On wizard load: server state wins if both present; client cache is offered as "you have unsaved changes from Tuesday — restore?" prompt.
- **No PII in localStorage** — wizard input that touches PII (guardian names, identity numbers) is server-only; client cache stores opaque step-keys + non-sensitive answers.

---

## 3 — AI integration points (single source of leverage)

All AI calls route through `services.ai_helpers::invoke_with_request`. Boundary scanner stays green. AI deployment posture (`docs/AI_DEPLOYMENT_POSTURE.md`) decides cloud vs edge — wizard layer doesn't care.

### 3.1 Five AI roles inside the wizard layer

| Role | When | What | Where it lands |
|---|---|---|---|
| **Smart defaults** | Step entry, before render | Given country + school_type + language + (optional) primary intent, fill the most likely answer pre-checked | `step_state.<step_key>.ai_suggested_default` |
| **Branch rationale** | Step entry, when `branches` are conditional | Plain-English "why these options" + "why this would change if you picked X earlier" | `.rmc-wizard-pane__rationale` slot, dismissible |
| **Natural-language intake** | Free-text steps (e.g. "describe your school") | Parse → fill multiple structured fields (school_type, grade_levels, calendar) → confirm | Pre-fills downstream `step_state` entries |
| **Translation mesh** | Communication Routing wizard | Generate SMS/WhatsApp templates in tenant's selected locales (uses Wave 13 marketing voice as style anchor) | `step_state.communication_routing.templates_by_locale` |
| **Proactive recommendations** | Dashboard tile (not wizard-internal) | AI scans `SetupProgress.health_breakdown` and `recommendations` → "you skipped E-Invoicing; schools like yours in MX/BR typically configure this within first 14 days" | Existing `SetupProgress.recommendations` JSON; rendered in Studio OS Launch mode + tenant Studio OS dashboard |

### 3.2 What AI MUST NOT do

- Never auto-apply a step answer without operator/tenant confirmation. AI fills the form; the human clicks Next.
- Never store AI rationale containing PII. `ai_recommendations_cache` is sanitized like the audit-event payload sanitizer (`_sanitize_payload` 14-key reject list from `apps/migration_cloud/models_audit.py`).
- Never invoke during step transitions that block — AI is async with a 5s budget; on timeout, the wizard advances without rationale and logs a metric (`wizard.ai.timeout`) via `apps/observability/metrics.py`.

### 3.3 AI helper API surface (the only public callables)

```python
# apps/setup_studio/wizard_ai.py
def request_smart_defaults(*, request, wizard_key, step_key, context) -> dict
def request_branch_rationale(*, request, wizard_key, step_key, prior_answers) -> str | None
def request_natural_language_intake(*, request, wizard_key, free_text, target_steps) -> dict
def request_translation_mesh(*, request, source_locale, target_locales, message) -> dict[str, str]
def refresh_setup_recommendations(*, request, school) -> list[dict]   # writes to SetupProgress.recommendations
```

Every callable is a 1-line wrapper around `services.ai_helpers.invoke_with_request(...)` plus PII sanitization plus metric emission plus typed dataclass return. Tests assert these are the ONLY AI call sites in the wizard layer.

---

## 4 — The 18 wizards: tier-by-tier rollout

Each row below is a one-line wizard spec. Detailed JSON drafts land in `apps/setup_studio/wizards/` during implementation; the table here is the planning SOT.

### 4.1 Phase 1 (foundation engine + 5 highest-leverage wizards) — Batch 1410, SW range `v3.65.0`→`v3.65.3`

| # | Wizard key | Audience | Composes | New surface area |
|---|---|---|---|---|
| **P1.0** | (engine itself) | both | setup_studio + ai_helpers | wizard_engine.py + wizard_views.py + JSON schema + class grammar + state cache |
| **P1.1** | `cross_platform_whitelabel_branding` | tenant_admin | brand_experience + design_tokens + LocalExperienceProfile + PWA generator | 4 steps: brand_asset_injection → typography_style_scaling → custom_domain_mapping → progressive_app_generator |
| **P1.2** | `multi_campus_local_sovereignty` | operator | locale + global_registries + CountryRegistry + LocalExperienceProfile | 4 steps: jurisdiction_mapping → dynamic_core_routing → cultural_vocabulary_injection → statutory_alignment |
| **P1.3** | `polymorphic_grading_curricula` | tenant_admin | academics + evals + runtime_blueprints + registries | 4 steps: track_selection → assessment_metrics → course_schema_association → transcript_factory |
| **P1.4** | `legacy_data_extraction_pipeline` | operator + tenant_admin | migration_cloud (full stack) + metadata + student360 + people | 4 steps: legacy_upload → field_vector_mapping → inline_error_cleanup → identity_core_seeding |
| **P1.5** | `ai_helpcenter_knowledge_injection` | tenant_admin | customersuccess + copilot_rail_service + ai_helpers | 4 steps: source_scraping → context_tagging → fallback_redirection_matrix → core_validation_test |

**Phase 1 acceptance criteria:**

- Engine + 5 wizards complete in repo.
- All 12 zero-tolerance gates green.
- `verify_unified_wizard_framework.py` introduced — verifies schema integrity, options_resolver/next_step_resolver dotted paths import, ai_helpers boundary preserved.
- One Playwright spec per wizard at `tests/e2e/wizards/<wizard_key>.spec.js` covering 390/768/1366 breakpoints + happy path.
- SW bumped to `sms-v3.65.x-unified-wizard-foundation-<date>`.
- MEMORY.md updated with `project_unified_wizard_framework_phase_1_<date>.md` memory.

### 4.2 Phase 2 (revenue + compliance + comms) — Batch 1411, SW range `v3.66.0`→`v3.66.5`

| # | Wizard key | Audience | Composes |
|---|---|---|---|
| **P2.1** | `local_first_fintech_tax_matrix` | tenant_admin | billing + finance + Stripe Connect plan + e-invoicing handshake |
| **P2.2** | `localized_activity_asset_marketplace` | tenant_admin | marketplace + brand_experience + finance + school_events |
| **P2.3** | `cashless_campus_pos` | tenant_admin | schoolops (meal_plan) + billing + finance + security + student360 (allergens) |
| **P2.4** | `dynamic_safeguarding_incident_medical` | operator + tenant_admin | security + compliance + policies_rules + student360 + communication |
| **P2.5** | `omnichannel_communication_routing` | tenant_admin | communication + automation + orchestration + social_media + ai_helpers (translate_mesh) |

**Phase 2 honest deferral:** P2.1's e-invoicing handshake UI lands; per-jurisdiction cert format (ZATCA `.pfx`, SAT `.cer`) validation is gated on Stripe Connect Wave delivery. P2.5's WhatsApp gateway/USSD provisioning is gated on per-tenant gateway account setup outside the wizard.

### 4.3 Phase 3 (operations + analytics + lifecycle) — Batch 1412, SW range `v3.67.0`→`v3.67.6`

| # | Wizard key | Audience | Composes |
|---|---|---|---|
| **P3.1** | `jit_operator_compliance_safeguarding` | operator | security + policies + policies_rules + observability |
| **P3.2** | `human_capital_shift_substitute_market` | operator + tenant_admin | payroll + people + schoolops + automation + policies |
| **P3.3** | `institutional_performance_board_reporting` | tenant_admin | analytics + reports + dashboard + observability + customersuccess |
| **P3.4** | `self_healing_observability_guard` | operator | observability + customersuccess (Prometheus bridge from v3.39) |
| **P3.5** | `dynamic_multi_campus_scheduling` | tenant_admin | academics + orchestration + runtime_blueprints + ai_helpers (conflict solver) |
| **P3.6** | `localized_field_trip_coordinator` | teacher | school_events + communication + finance + compliance + student360 |
| **P3.7** | `personal_graduation_pathway_elective` | student | academics + student360 + runtime_blueprints + analytics |

### 4.4 Persona wizard symmetry closure (lands in Phase 1)

- `parent_onboarding_wizard` (NEW) — symmetric to `templates/teacher/onboarding_wizard.html`, 5 steps: profile → linked_children → communication_preferences → payment_method → consent_signatures.
- `staff_onboarding_wizard` (NEW) — symmetric to teacher, 5 steps: profile → role_assignment → background_check_status → schedule_preferences → training_module_assignment.

These ride the same engine; they're not separate frameworks.

### 4.5 Explicitly dropped (not in any phase)

| Original wizard | Reason |
|---|---|
| Real-Time Smart Transit & Geo-Fence | Needs `apps/transport_fleet/` module — out of scope for unified wizard plan; surface as separate program later. |
| High-Density Dormitory & Residential | Needs `apps/logistics/` — same reasoning. |
| Asset QR Matrix subsystem of Marketplace wizard | Needs `apps/asset_tracker/` — can be re-added as Marketplace wizard Step 5 after asset_tracker lands. |
| Contextual Quick-Grade (teacher daily) | Daily-use form, not config wizard. Belongs as a streamlined form in teacher dashboard (different plan). |
| Mobile Money Fee Settlement (parent) | Payment flow. Belongs in parent portal checkout (different plan). |
| Async Medical Emergency & Absence (parent) | 3-tap form. Wizardizing adds friction. Belongs as one-screen action. |
| Cashless Campus Onboarding (student-side) | Sub-flow of P2.3 operator-side; not separate. |

---

## 5 — Phase 1 implementation step-by-step (the only fully-specified phase)

Phase 2 + 3 inherit this template — once the engine + 5 wizards ship, every subsequent wizard is ~150 LOC JSON + 1 view + 1 template extension + tests.

### Step 1 — Engine skeleton (no UI yet)

1. Create `apps/setup_studio/wizard_engine.py` with `WizardDefinition` + `StepDefinition` dataclasses, `WIZARD_REGISTRY: dict[str, WizardDefinition]` autoloaded from `wizards/*.json` at module import.
2. Create `apps/setup_studio/wizard_state_resolver.py` — pure functions: `get_state(school, wizard_key)`, `apply_answer(school, wizard_key, step_key, payload)`, `resolve_next(school, wizard_key)`.
3. Add validators: schema validator (jsonschema lib already in tree), resolver-importability validator, audience validator, ai-context-key whitelist validator.
4. Tests at `apps/setup_studio/tests/test_wizard_engine.py` — registry load, schema validation, resolver imports, state namespacing, JSON round-trip.

### Step 2 — JSON schema doc + first wizard JSON

1. Author `docs/WIZARD_BRANCHING_SCHEMA.md` — formal jsonschema + example + every field documented.
2. Author `apps/setup_studio/wizards/cross_platform_whitelabel_branding.json` (P1.1) — simplest wizard, all 4 steps mappable to existing brand_experience.
3. Add unit test asserting JSON parses + every `options_resolver` and `next_step_resolver` imports.

### Step 3 — Class grammar + state cache JS

1. Add `.rmc-wizard-*` entries to `static/css/rmc-class-grammar.css`.
2. Create `static/css/rmc-wizard.css` bundle (~400 lines, semantic tokens only, RTL-safe, reduced-motion-safe, 100dvh-locked).
3. Create `static/js/rmc-wizard-state-cache.js` — CSP-safe IIFE, no globals leaking beyond `window.RmcWizardStateCache`.
4. Wire bundle + JS into both `portal_base.html` (tenant) and `control_plane_skeleton.html` (operator) via `{% block extra_css %}` / `{% block extra_js %}` per existing patterns.

### Step 4 — Operator + tenant skin templates

1. `templates/setup_studio/operator_wizard.html` — extends `control_plane_skeleton.html`. Single template; step content slots in via `{% include step.template_path %}` if defined, else generic-form fallback.
2. `templates/setup_studio/tenant_wizard.html` — extends `portal_base.html`. Same shape, tenant-shell variant of `.rmc-wizard-shell`.
3. Both templates render: stepper (top), pane (center), nav (bottom), help-rail (desktop right) — all hookable via Django `{% block %}` so per-wizard custom panes can override without forking.

### Step 5 — Views + URLs

1. `apps/setup_studio/wizard_views.py` with `OperatorWizardView` (LoginRequiredMixin + staff_required + permission check) and `TenantWizardView` (LoginRequiredMixin + tenant_admin permission per `apps.platform_runtime.role_registry`).
2. Both views: GET renders current step; POST applies answer + advances + redirects to next step's GET (POST-Redirect-GET pattern).
3. URLs:
   - Operator: `/super/wizards/<wizard_key>/` + `/super/wizards/<wizard_key>/<step_key>/` under `siteconfig:super` namespace.
   - Tenant: `/school/studio/wizards/<wizard_key>/` + `/school/studio/wizards/<wizard_key>/<step_key>/` under `studio_os:tenant` namespace.
4. Add `# rbac-allow: <role>-wizard-<key>-access` markers per `audit_role_permission_matrix.py`.

### Step 6 — AI helper bridge

1. `apps/setup_studio/wizard_ai.py` with 5 public callables from §3.3.
2. Each callable: PII-sanitize context → `services.ai_helpers.invoke_with_request(...)` → typed return → metric emission.
3. Add tests asserting `services.ai_gateway` is NOT imported (regex test on AST).
4. Add `wizard.ai.timeout`, `wizard.ai.success`, `wizard.ai.fallback_to_static` to metric emission via `apps/observability/metrics.py`.

### Step 7 — Wizards P1.2 → P1.5 + parent + staff persona

Each wizard: ~150 LOC JSON + per-step input-type templates (if non-generic) + tests. Reuses engine + skin + AI + state cache from Steps 1-6. No new infrastructure.

### Step 8 — Verifiers + CI

1. `scripts/verify_unified_wizard_framework.py` — schema integrity + resolver imports + ai boundary + audience markers + URL resolve + template safety.
2. Add as CI step under `architectural-boundaries.yml`.
3. Add to `MEMORY.md` index with project memory file.

### Step 9 — Service worker + docket + memory

1. Bump `static/js/service-worker.js::CACHE_VERSION` to `sms-v3.65.0-unified-wizard-foundation-<date>`.
2. Append `## YYYY-MM-DD — v3.65.0 …` section to `docs/CSS_RETIREMENT_DOCKET.md` per checklist.
3. Write `project_unified_wizard_framework_phase_1_<date>.md` memory + add MEMORY.md index entry.

---

## 6 — Acceptance criteria (per phase)

### Phase 1 acceptance

- [ ] Engine + 5 wizards + parent + staff persona wizards complete in repo.
- [ ] All zero-tolerance gates green: tenant_queryset_safety, ai_gateway_boundary, sentry_boundary, print_statements, bare_except, migration_model_imports, drf_schema_coverage, assert_in_production, subprocess_shell_true, money_float, tenant_isolation_marker_quality, pii_logging_smell, theme_attribute_contract, sticky_with_overflow_hidden, reveal_armed_invariants, template_render_safety, inline_style_off_token, undefined_css_classes, off_token_colors, theme_locked_token_text, sri_required, csp_nonce_emission, pwa_manifest_coverage, slo_registry, service_worker_version (`--check-monotonic`).
- [ ] `verify_unified_wizard_framework.py` passes.
- [ ] One Playwright spec per wizard passes 3-breakpoint sweep (390/768/1366).
- [ ] `audit_role_permission_matrix.py` — every new view carries `# rbac-allow:` marker.
- [ ] Memory + MEMORY.md updated.
- [ ] SW monotonic bump landed.

### Phase 2 acceptance

- [ ] 5 wizards complete + JSON schema unchanged from Phase 1 (forward-compat).
- [ ] All gates still green.
- [ ] Honest deferrals catalogued: e-invoicing cert formats, WhatsApp/USSD live gateway provisioning.

### Phase 3 acceptance

- [ ] 7 wizards complete.
- [ ] All gates still green.
- [ ] Dropped wizards documented in §4.5 — never delivered, by design.

---

## 7 — How AI gets compounding leverage as wizards multiply

After Phase 1: AI assists 5 wizards. After Phase 3: AI assists 18 wizards through the same 5 callables, because the wizards share the engine. No per-wizard AI code. This is the lesson from the Migration Cloud waves — invest in the bridge once.

Specifically:

- **`refresh_setup_recommendations`** runs nightly via Celery beat (`setup_studio-recommendations-refresh` Mondays 04:00 UTC). It scans every active school's `SetupProgress` + tenant context + completion data and writes a fresh `SetupProgress.recommendations` JSON. Operator Studio OS Launch mode + tenant Studio OS dashboard render these recommendations. **This single addition turns the existing-but-invisible recommendations layer into an always-fresh proactive nudge system.**
- **`request_natural_language_intake`** in P1.2 (Sovereignty wizard) lets a tenant admin say "we're a Catholic K-12 in Karnataka with English+Kannada medium" and the wizard pre-fills 7 steps' worth of structured answers across Jurisdiction Mapping, Cultural Vocabulary, Statutory Alignment, plus dependent wizards (Whitelabel palette, Polymorphic Grading state board, FinTech UPI). One AI call front-loads the entire setup.
- **`request_translation_mesh`** in P2.5 (Omnichannel Comms) generates SMS/WhatsApp templates in 5-10 locales at once, anchored to Wave 13 marketing voice. School ships day-1 multilingual without writing a single template.
- **AI conflict solver** in P3.5 (Multi-Campus Scheduling) is the only wizard that uses `services.ai_helpers` for hard problem-solving (resource constraints + curricular pathways). Lower-leverage AI elsewhere is intentional — we resist AI-everywhere theater.

---

## 8 — CI gates added by this plan

| Scanner / verifier | Baseline | Phase | Purpose |
|---|---|---|---|
| `verify_unified_wizard_framework.py` | n/a (structural) | 1 | Schema + resolver imports + AI boundary + audience markers + URL resolve |
| `scan_wizard_json_schema_drift.py` | 0 | 1 | All `wizards/*.json` validate against `docs/WIZARD_BRANCHING_SCHEMA.md` |
| `scan_wizard_class_grammar.py` | 0 | 1 | Every `.rmc-wizard-*` class referenced in wizard templates exists in CSS bundles |
| (existing) `scan_ai_gateway_boundary.py` | 0 | 1+ | Wizard layer keeps boundary; allowlist NOT extended |
| (existing) `scan_pii_logging_smell.py` | 0 | 1+ | Wizard step payloads pass through `_sanitize_payload` before any logger call |
| (existing) `scan_role_strings.py` | 292 | 1+ | New wizard views/JSON use `User.Role` or `role_registry` |
| (existing) `verify_service_worker_version.py --check-monotonic` | n/a | 1+ | Every wave bumps cleanly |

---

## 9 — Risks + mitigations

| Risk | Mitigation |
|---|---|
| **Engine over-design** — schema turns into a DSL no one can read | Keep `next_step_resolver` simple; branching reserved for genuinely conditional logic. If a wizard needs >5 steps with branches, split into two wizards. |
| **AI failure cascades wizard UX** | 5s timeout per AI call; fallback to static defaults; metrics surface failure rate; copilot rail always available as escape hatch. |
| **Tenant queryset isolation lapses** | Engine forces `SetupProgress.objects.filter(school=school)` in resolver; tests assert no `.all()` without school scope; `scan_tenant_queryset_safety` baseline 0 holds. |
| **PII bleed via AI context** | `ai.context_keys` is a whitelist, not a blacklist — fields must be explicitly opted in. Default empty. |
| **Wizard sprawl — 18 becomes 50** | This plan caps at 18. New wizards require a new plan doc; no organic accretion. |
| **State cache survives schema bumps** | `schema_version` key in localStorage; mismatch → discard cache + warn user once. |
| **Mobile layout regressions on small screens** | `.rmc-wizard-stepper` collapse + 100dvh-lock + Playwright 390/768/1366 sweep on every wizard. |
| **Persona wizard duplication with existing student/teacher wizards** | Phase 1 absorbs existing `templates/student/onboarding_wizard.html` and `teacher/onboarding_wizard.html` into the engine — they become JSON specs, not separate templates. Migration: keep old URLs as 301s to new engine routes for 30 days, then drop. |
| **CLAUDE.md "no hardcoding" violation in JSON** | JSON cannot inline option lists — `options_resolver` dotted path is required by schema. Validator enforces. |

---

## 10 — Out-of-scope (revisit after Phase 3)

- Wizard analytics dashboard (which step has highest drop-off? AI cost per wizard?). Likely Phase 4.
- Self-service wizard authoring UI for tenant admins. Probably never — wizards are platform-curated.
- Wizard versioning + A/B testing of step ordering. Premature optimization.
- Voice-driven wizard input. Out of scope; revisit when accessibility audit demands it.
- New top-level Django app `apps/wizards/`. Explicitly rejected — keep engine in `apps/setup_studio/` to consolidate, not fragment.

---

## 11 — Handoff state for the next implementer

**Read order:**
1. This file end-to-end (§0 → §11).
2. `apps/setup_studio/services.py` + `models.py` — understand existing step lifecycle.
3. `services/ai_helpers.py` — understand AI invocation contract.
4. `docs/AI_DEPLOYMENT_POSTURE.md` — understand cloud vs edge routing.
5. CLAUDE.md sections "Non-negotiable directives" + "Architectural CI gates".

**Start at:** Phase 1 Step 1 (§5). Engine skeleton + JSON schema doc + first wizard JSON. Do NOT skip ahead to wizards before engine ships clean.

**Branch naming:** `wave/unified-wizard-engine-batch-1410`.

**SW bump path:**
- Phase 1 first patch: `sms-v3.65.0-unified-wizard-foundation-<date>`.
- Subsequent patches in Phase 1: `v3.65.1`, `v3.65.2`, etc.
- Phase 2 opens: `sms-v3.66.0-unified-wizard-revenue-compliance-<date>`.
- Phase 3 opens: `sms-v3.67.0-unified-wizard-operations-<date>`.

**Reserve nothing in advance.** The version range is a guide; actual increment follows reality.

---

## 12 — Honest deferrals catalogue

These are deliberately NOT in scope and must NOT be invented during implementation:

1. **Transport Fleet** module — no `apps/transport_fleet/`. Transit wizard cannot land until this exists. Surface as a separate plan if/when fleet management becomes a roadmap priority.
2. **Asset Tracker** module — no `apps/asset_tracker/`. QR Matrix sub-step of Marketplace wizard deferred.
3. **Logistics / Dormitory** module — no `apps/logistics/`. Dormitory wizard deferred.
4. **AI Helpcenter live embedding store** — `apps/customersuccess/` lacks a per-tenant vector store today. Phase 1 P1.5 ships the intake UI + a deterministic-rules fallback identical to `template_ai_recommender.py`'s pattern. Live LiteLLM embedding wiring is gated on AI deployment posture rollout.
5. **E-invoicing per-jurisdiction cert validation** — P2.1 ships the `.pfx`/`.cer` upload form + format-shape validation only. Per-jurisdiction live submission (ZATCA, SAT, GST e-Invoice) is gated on Stripe Connect plan delivery + counsel signoff per jurisdiction.
6. **WhatsApp Business / USSD gateway provisioning** — P2.5 ships routing config; per-tenant gateway accounts are outside the wizard.
7. **Substitute teacher live SMS broadcast** — P3.2 ships the wizard config; live broadcast invocation goes through `apps/communication/` + `apps/automation/` which exist but aren't wired for substitute-specific batch SMS at scale today.
8. **Board reporting PDF compile** — P3.3 ships the data assembly + dashboard preview; cryptographically-signed PDF export pipeline gated on `apps/reports/` PDF pipeline expansion (currently single-template).
9. **Multi-campus scheduling AI conflict solver** — P3.5 ships the wizard + a deterministic constraint solver (existing `apps/orchestration/`). The "AI permutation search" upgrade is gated on LLM availability + multi-campus pilot tenant.
10. **Operator Whitelabel PWA generator instant install** — P1.1 Step 4 ships the manifest compile; deploying compiled PWA to per-tenant CDN is gated on existing CDN orchestration.

Every deferral above is **honest** — feature flag, counsel docket, external provisioning, or modular dependency. NOT "we'll do it later" hand-waving.

---

**Plan author:** Claude Opus 4.7 (1M context)
**Audit basis:** 30+ wizard catalog from operator, 53-app codebase scan, CLAUDE.md constraints, MEMORY.md history (v3.39 → v3.64.1), `apps/setup_studio/services.py:13` step catalog inspection.
