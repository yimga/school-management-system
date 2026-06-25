# How a School Starts on RunMyCampus — Non-Negotiable Flow

**Source:** [RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md](RunMyCampus_Global_Education_Research_and_Competitive_Strategy_Report.md) Section 7.  
**Rule:** The school journey is three phases. Every phase is implemented; no phase is "backlog."

---

## Overview

1. **Phase 1:** Signup and wizard for setup and onboarding.  
2. **Phase 2:** Branding — school identity, templates, live preview, design studio.  
3. **Phase 3:** Select features and see live previews.

After completion, the school has an active tenant, branding (or placeholder), a plan/trial, and optional template applied.

---

## Phase 1: Signup and wizard

**Purpose:** School creates an account and completes a guided setup so they know what they get and what their upgrade path is.

**Steps (in product):**

1. **Welcome + region** — Country and school flavor (e.g. General Academic, Technical/Vocational).  
   - **Code:** `apps/schools/signup_views.py` → `onboarding_wizard`; `templates/schools/onboard_wizard.html` (step 1).  
   - **Data:** `GlobalGeoCatalog.list_countries()`; session holds `country_code`, `school_flavor`.

2. **Plan / trial** — Choose free trial or plan; see plan comparison (Starter, Growth, Enterprise and add-ons).  
   - **Code:** Onboarding step 2; `templates/schools/partials/plan_comparison.html`; plans from `Plan.objects.filter(is_active=True)`.  
   - **Data:** Session holds `plan_slug` or `trial: true`.

3. **Branding placeholder + template** — Optional logo upload; "Choose a look" (template gallery); **Import from your website** form (implemented).  
   - **Code:** Onboarding step 3; template list from `ThemePack.objects.filter(is_active=True)`; selection stored in session; import-from-URL form POSTs to same view, stores result in session; applied after signup or on first login.  
   - **Live preview:** Preview pane or link to theme preview for selected template.

4. **Done** — Summary and CTA to signup form or trial API.  
   - **Code:** Onboarding step 4; links to `signup_school` and trial endpoint; session cleared or passed to signup (e.g. prefill country/plan).

**Entry points:**

- **Public:** `/onboard/` (marketing/public_urls).  
- **Signup form:** `signup_school` at `/signup/` (or equivalent).  
- **Trial API:** `POST /api/trial/` or `/start-trial` → `api_trial_school`.

**Verification:** A school can complete the wizard, see plan comparison and template choice, then proceed to signup or trial. Free trial and upgrade path are visible. See STRATEGY_REPORT_GAP_CLOSURE.md.

---

## Phase 2: Branding

**Purpose:** School establishes identity (logo, colors, template) and can preview across devices.

**What exists:**

- **Logo, colors, wallpaper:** School/SiteSettings; branding API.  
- **Custom domain:** School.custom_domain; verification flow.  
- **Theme pack / template:** ThemePack; SiteSettings.theme_pack and apply_theme_pack.  
- **Live preview:** `siteconfig:theme_colors` with live preview button; reportcard_style_live_preview.  
- **Template gallery:** `siteconfig:template_gallery` (or equivalent) — list theme packs, preview, "Use this template."  
- **Design studio:** Gated feature; link from Theme & Experience (`siteconfig:theme_colors`).  
- **Website import:** Implemented (brand_import.py; API; Theme & Experience + onboarding step 3 form). See HOW_WE_SCOPE_WEBSITE_IMPORT.md.

**Where it appears:**

- In onboarding: step 3 (branding placeholder + choose a look).  
- After login: Theme & Experience at `/siteconfig/theme-colors/`; template gallery; design studio when enabled.

**Verification:** School can pick a template in onboarding and/or after login; live preview works; design studio is reachable when gated feature is enabled. See STRATEGY_REPORT_GAP_CLOSURE.md.

---

## Phase 3: Feature selection and live previews

**Purpose:** School selects plan and optional add-ons and sees a preview of what their portal/dashboard will look like.

**What exists:**

- **Plan and add-ons:** Plan model; School.plan, School.addons; PlanAddon; is_feature_enabled.  
- **Plan comparison:** Partial `plan_comparison.html`; plans in onboarding step 2.  
- **Setup studio:** Onboarding steps 2 (plan) + 3 (template) with preview pane = single setup flow.  
- **Upgrade path:** Upgrade modal placeholder links to plan comparison or contact; in-product upgrade UX.

**Verification:** School sees plan comparison and add-ons during onboarding; selection updates session/context; preview (theme or placeholder) is shown. Post-signup, upgrade CTA and plan comparison are available. See STRATEGY_REPORT_GAP_CLOSURE.md.

---

## Phase 4: Post-login setup → launch (canonical extension)

**Purpose:** After email verification and portal provisioning, the school admin completes Setup Studio, optional Migration Cloud import, and launch readiness before daily operations.

**Steps (in product):**

1. **Owner onboarding (3 steps)** — Account password → school profile → done + provision poll.  
   - **Code:** `apps/accounts/views_owner_onboarding.py`; routes under `/authentication/onboarding/`.

2. **Setup command surface** — Admin backend shows **School readiness** ring until checklist ≥ 70% **and** Setup Studio `launch_ready` is false.  
   - **Code:** `templates/partials/tenant/setup_command_surface.html`; `apps/accounts/views.py` `_resolve_setup_landing`.

3. **Setup Studio (9 steps + wizards)** — Plan, blueprint, branding, data path, academic year, launch checklist.  
   - **Code:** `apps/setup_studio/services.py` `STEP_DEFINITIONS`; wizards under `apps/setup_studio/wizards/`.

4. **Migration branch (optional)** — Public wizard step 3 or `account_migration` wizard → Migration Cloud / CSV.  
   - **Code:** `signup_views.onboard_migration_handoff`; `apps/migration_cloud/`.

5. **Go live** — `launch_ready` true → post-setup cockpit (Overview | Cockpit); lifecycle `daily_operations` when setup health ≥ 85.  
   - **Code:** `execute_launch`; `apps/platform_runtime/tenant_operational_lifecycle.py`.

6. **Unified readiness API** — Single meter for provision + checklist + launch blockers.  
   - **Code:** `apps/schools/school_readiness.py`; `GET /api/school/readiness/`.

**Audit reference:** `docs/phase_checklists/PROVISIONING_TO_GOLIVE_AUDIT.md` (batch 1731).

---

## Code and doc references

| Item | Location |
|------|----------|
| Signup | `apps/schools/signup_views.py` → signup_school, verify_signup |
| Trial API | `apps/schools/signup_views.py` → api_trial_school |
| Onboarding wizard | `apps/schools/signup_views.py` → onboarding_wizard; `templates/schools/onboard_wizard.html` |
| Plan comparison | `templates/schools/partials/plan_comparison.html`; plans in onboarding view |
| Template gallery | `apps/siteconfig/views.py` → template_gallery_page; `templates/siteconfig/template_gallery.html` |
| Theme & Experience | `apps/siteconfig/views.py` → theme_colors_page; `templates/siteconfig/theme_colors.html` |
| Design studio | Feature gate `design_studio`; siteconfig design_studio module |
| How a school starts (this doc) | `docs/HOW_A_SCHOOL_STARTS.md` |
| Gap closure (no backlog) | `docs/STRATEGY_REPORT_GAP_CLOSURE.md` |

---

## Non-negotiable

- All three phases are implemented.  
- No phase is "saved for later" or left as backlog.  
- Changes to this flow must update this doc and STRATEGY_REPORT_GAP_CLOSURE.md.
