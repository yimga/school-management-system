# Three Plans — Detailed Execution Guide

**Superseded.** For execution and next steps use [REDUNDANCY_AND_PLAN_INDEX.md](REDUNDANCY_AND_PLAN_INDEX.md) and the four canonical docs (RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH, BACKLOG §2e, docs_truth_ledger, NEXT_50). This file is **reference only**.

This guide breaks down **every item** in `THREE_PLANS_MERGED_CHECKLIST.md` into concrete sub-steps, dependencies, acceptance criteria, and verification. Execute in order; do not skip. Update the checklist status (⬜ → 🔄 → ✅) as you go.

**Reference:** `docs/THREE_PLANS_MERGED_CHECKLIST.md`

---

## How to Use This Guide

1. **Order:** Execute Parts A → B → C → D → E → F (waves 4–17 in order) → G. Within each part, do items in table order unless a dependency says otherwise.
2. **Per item:** Complete every sub-step under "Steps"; then run "Verification"; then mark the checklist "Done" only when "Acceptance criteria" are met.
3. **Code refs:** Paths like `apps/schools/models.py` are relative to repo root. "Already in code" means verify behavior first; only implement if something is missing.
4. **Dependencies:** If an item lists "Depends on: X", complete X first (same or earlier part).

---

## Part A: Branded Login & Deployment (do first)

### B1 — Use SITE_PRIMARY_COLOR / SITE_ACCENT_COLOR on login (tenant colors)

**Already in code:** Login template and context processor expose these; confirm they are applied everywhere login uses brand colors.

| | |
|---|---|
| **Steps** | 1. Ensure `site_settings` context processor passes `SITE_PRIMARY_COLOR` and `SITE_ACCENT_COLOR` from current school (or defaults) to templates. 2. In `templates/auth/login.html`, ensure hero/gradient/buttons use `{{ SITE_PRIMARY_COLOR|default:... }}` and `{{ SITE_ACCENT_COLOR|default:... }}`. 3. If login is shown on base domain (no school), define fallback defaults (e.g. `#0d6efd`, `#198754`) in context or template. 4. Check admin login template `templates/admin/login.html` if it should also use tenant colors when applicable. |
| **Dependencies** | None (first item). |
| **Acceptance criteria** | On tenant subdomain, login page hero/primary UI uses the school’s primary and accent colors; on base domain or when school has no colors, sensible defaults are used. |
| **Verification** | Load login on a tenant with custom `primary_color`/`accent_color`; confirm CSS uses those values. Load on base domain; confirm no broken styles. |
| **Code refs** | `apps/siteconfig/context_processors.py` (`site_settings`), `templates/auth/login.html` (`.auth-hero` gradient). |

---

### B2 — Add School.wallpaper_url + migration; expose TENANT_WALLPAPER_URL in context

**Already in code:** `School.wallpaper_url` and migration exist; context processor exposes `TENANT_WALLPAPER_URL`. Verify and add migration only if field is missing in your branch.

| | |
|---|---|
| **Steps** | 1. Confirm `School.wallpaper_url` exists on `apps/schools/models.py` (URLField, blank=True). 2. If missing, add field and create migration: `python manage.py makemigrations schools -n add_school_wallpaper_url`. 3. Run migration. 4. In `site_settings` context processor, set `ctx["TENANT_WALLPAPER_URL"] = getattr(school, "wallpaper_url", None) or ""` when `school` is set. 5. When no school, set `TENANT_WALLPAPER_URL = ""`. |
| **Dependencies** | None. |
| **Acceptance criteria** | `School` has `wallpaper_url`; login context always has `TENANT_WALLPAPER_URL` (string, possibly empty). |
| **Verification** | Set `wallpaper_url` on a school in admin; load login on that tenant; in template debug or view, confirm `TENANT_WALLPAPER_URL` is the URL. |
| **Code refs** | `apps/schools/models.py`, `apps/siteconfig/context_processors.py`, migration `0015_add_school_wallpaper_url` (if present). |

---

### B3 — Split-screen login layout (left wallpaper, right form); responsive

**Already in code:** Login template uses `TENANT_WALLPAPER_URL` to switch to split layout; left panel shows wallpaper, right has form. Verify and fix responsive behavior.

| | |
|---|---|
| **Steps** | 1. In `templates/auth/login.html`, when `TENANT_WALLPAPER_URL` is set, render a split layout: left panel (background-image from `TENANT_WALLPAPER_URL`), right panel (form + content). 2. Use CSS (e.g. grid or flex) so that on small viewports the left panel is hidden or collapsed and the form is full-width. 3. Ensure focus order and labels remain correct when layout changes. 4. Add `role="img"` or `aria-hidden="true"` on decorative wallpaper panel if it has no text. |
| **Dependencies** | B2 (TENANT_WALLPAPER_URL in context). |
| **Acceptance criteria** | With wallpaper set: desktop shows left (image) + right (form); mobile/narrow view shows form usable without horizontal scroll. Without wallpaper: existing single-column layout still works. |
| **Verification** | Resize browser; test with and without `TENANT_WALLPAPER_URL`; check accessibility (keyboard, screen reader). |
| **Code refs** | `templates/auth/login.html` (`.login-split`, `.login-split__left`, `.login-split__right`). |

---

### B4 — Role selector on login (Student / Staff / Parent); post-login redirect by role

**Already in code:** Login form has role dropdown; session stores intent; redirect uses it. Verify full flow.

| | |
|---|---|
| **Steps** | 1. Add a role selector on login form: Student, Staff, Parent (e.g. `<select name="role">`). 2. On POST, store selected role in session (e.g. `request.session["login_intent_role"] = role`) when value is one of student|staff|parent. 3. After successful login, if `next` is not set, redirect by role: Student → teacher/student dashboard or portal student view; Staff → backend dashboard; Parent → parent portal. 4. Use existing `accounts:redirect` or equivalent; extend it to read session role and redirect accordingly. 5. Clear role from session after redirect. |
| **Dependencies** | None. |
| **Acceptance criteria** | User can choose role on login; after login without `next`, they land on the correct dashboard for that role. |
| **Verification** | Log in as each role with role selector set; confirm destination URL. Log in with `?next=/some/path`; confirm `next` takes precedence. |
| **Code refs** | `templates/auth/login.html` (role select), `apps/accounts/views.py` (`login_view`, redirect logic, `LOGIN_INTENT_ROLE_KEY`). |

---

### B5 — SSO buttons on login when school has SAML/OIDC (link to existing start URLs)

**Already in code:** `LOGIN_SSO_INTEGRATIONS` is built and passed to login template; buttons link to start URLs. Verify and document.

| | |
|---|---|
| **Steps** | 1. Determine how SAML/OIDC integrations are configured per school (e.g. SiteSettings, Integration model, or school-specific config). 2. In login view or context processor, build list of dicts `{ "label": "...", "url": "/auth/sso/..." }` for current school’s SSO IdPs. 3. Pass as `LOGIN_SSO_INTEGRATIONS` to login template. 4. In login template, if `LOGIN_SSO_INTEGRATIONS` is non-empty, render buttons (or links) that go to those URLs; optional "or sign in with username" below. 5. Preserve `next` in SSO URL query if present. |
| **Dependencies** | None. |
| **Acceptance criteria** | When school has SAML/OIDC configured, login page shows SSO buttons; clicking goes to correct start URL. When no SSO, no SSO buttons. |
| **Verification** | Configure one SSO IdP for a school; load login on that tenant; click button and confirm URL. Disable SSO; confirm buttons disappear. |
| **Code refs** | `apps/accounts/views.py` (`_get_login_sso_integrations`, `login_view`), `templates/auth/login.html`. |

---

### B6 — "Powered by RunMyCampus" footer on login

**Already in code:** Present in `templates/auth/login.html`. Verify visibility and link.

| | |
|---|---|
| **Steps** | 1. Add a footer line on login page: "Powered by RunMyCampus" with link to https://runmycampus.com (or configured platform URL). 2. Style so it does not distract from primary CTA (e.g. small, muted). 3. Open in new tab with `rel="noopener noreferrer"`. |
| **Dependencies** | None. |
| **Acceptance criteria** | Login page shows "Powered by RunMyCampus" with working link. |
| **Verification** | Load login; click link; confirm destination and tab behavior. |
| **Code refs** | `templates/auth/login.html` (footer link). |

---

### B7 — Tenant-aware email placeholder (e.g. "School Email" / school name)

**Already in code:** `LOGIN_EMAIL_PLACEHOLDER` is set in context (school name or "School Email"). Verify template uses it.

| | |
|---|---|
| **Steps** | 1. In context processor, set `LOGIN_EMAIL_PLACEHOLDER` to school name when on tenant, or "School Email" (translatable) when no school. 2. In login template, set username/email input placeholder to `{{ LOGIN_EMAIL_PLACEHOLDER|default:"School Email" }}`. |
| **Dependencies** | None. |
| **Acceptance criteria** | On tenant, placeholder reflects school (e.g. school name or "School Email"); on base domain, generic placeholder. |
| **Verification** | Check login on tenant and base domain; confirm placeholder text. |
| **Code refs** | `apps/siteconfig/context_processors.py`, `templates/auth/login.html` (input placeholder). |

---

### B8 — Optional: login page language from tenant or Accept-Language

**Already in code:** `_get_login_page_language` and `translation.activate` in login view. Verify and document.

| | |
|---|---|
| **Steps** | 1. Before rendering login (GET or POST), determine language: from tenant/school setting if available, else from `Accept-Language` header. 2. Call `translation.activate(lang)` for that request so login strings render in chosen language. 3. Do not persist language cookie unless product decision is to remember login page language. 4. Document in deployment or i18n doc that tenant can set preferred login language (if supported). |
| **Dependencies** | None. |
| **Acceptance criteria** | When tenant has language set, login page uses it; otherwise Accept-Language is used; no regression for existing locales. |
| **Verification** | Set tenant language (if UI exists); reload login; confirm strings. Change Accept-Language; confirm fallback. |
| **Code refs** | `apps/accounts/views.py` (`login_view`, `_get_login_page_language`). |

---

### B9 — Deployment doc: render.yaml summary, wildcard SSL, CDN, RLS, health, go-live checklist

| | |
|---|---|
| **Steps** | 1. Create or update a single deployment doc (e.g. `docs/DEPLOYMENT_FULL.md` or extend `DEPLOY_CHECKLIST.md`). 2. **render.yaml summary:** List services (web, worker, beat, redis, db); buildCommand, preDeployCommand, startCommand; key env vars (DATABASE_URL, REDIS_URL, SECRET_KEY, etc.). 3. **Wildcard SSL:** Document how to obtain and configure wildcard cert for `*.yourdomain.com` (e.g. Render, Caddy, or CDN). 4. **CDN:** Document cache-control for static/media, asset versioning, and recommended CDN in front of app (see `docs/DEPLOY_CHECKLIST.md` CDN section if present). 5. **RLS:** If using Postgres RLS for multi-tenant, document that tenant schema/row-level security is enabled and how to verify isolation. 6. **Health:** Document health endpoint(s) (e.g. `/health/`), `db_health_check` or equivalent, and how Render/predeploy use them. 7. **Go-live checklist:** Ordered list: migrations, collectstatic, env check, health check, smoke test, DNS/custom domain, SSL, backup/rollback plan. |
| **Dependencies** | None (doc only). |
| **Acceptance criteria** | One doc covers render.yaml, wildcard SSL, CDN, RLS, health, and go-live steps; a new deployer can follow it. |
| **Verification** | Review doc for completeness; run through go-live steps in staging if possible. |
| **Code refs** | `render.yaml`, `DEPLOY_CHECKLIST.md`, `scripts/release/render_predeploy.sh`, `docs/PHASE_I_MULTI_REGION_AND_DEPLOY.md`. |

---

## Part B: Powerhouse v2 — Wave 0 (Baseline and Gates)

### W0-1 — Baseline freeze; quality gates defined for all waves

| | |
|---|---|
| **Steps** | 1. Define "baseline" as a specific commit or tag (e.g. current main after Part A). 2. Document what is in scope for each wave (W1–W17) in a short table: wave number, theme, key deliverables, quality gate (e.g. "no new critical linter errors", "smoke passes"). 3. Store baseline report (e.g. list of migrations, critical URLs, test counts) in `docs/baseline_report.md` or similar. 4. Optionally run and archive a baseline test/lint report. |
| **Dependencies** | Part A complete (or agreed baseline point). |
| **Acceptance criteria** | Baseline is tagged/document; every wave has a defined quality gate. |
| **Verification** | Read baseline doc and wave table; confirm gates are clear. |

---

### W0-2 — CI gates: migrations check, smoke, tenant audit, RBAC checks, docs lint

| | |
|---|---|
| **Steps** | 1. **Migrations check:** In CI (e.g. GitHub Actions), run `python manage.py makemigrations --check --dry-run` (or equivalent) so unapplied model changes fail the build. 2. **Smoke:** Run a minimal smoke test (e.g. critical URL resolution or one HTTP request to login/health). 3. **Tenant audit:** If you have a management command or test that checks tenant isolation or tenant config, run it in CI. 4. **RBAC checks:** Run tests or a command that verify RBAC rules (e.g. permission names, view decorators). 5. **Docs lint:** If you use markdownlint or similar, add a step to lint `docs/` (or key docs). 6. Wire all of the above into one CI workflow (e.g. `.github/workflows/ci.yml`); document in README or docs. |
| **Dependencies** | W0-1 (gates defined). |
| **Acceptance criteria** | Push that breaks migrations, smoke, tenant audit, RBAC, or docs lint fails CI. |
| **Verification** | Intentionally break one of the checks; confirm CI fails. Fix and confirm green. |
| **Code refs** | `.github/workflows/`, `manage.py`, existing test/commands. |

---

### W0-3 — Release checklist skeleton

| | |
|---|---|
| **Steps** | 1. Create `docs/RELEASE_CHECKLIST.md` (or add section to deployment doc). 2. Include: pre-release (branch, version tag, changelog), build (migrate, collectstatic, tests), deploy (env, health), post-release (smoke, monitoring, rollback plan). 3. Leave placeholders for wave-specific steps if needed. |
| **Dependencies** | None. |
| **Acceptance criteria** | A release runner can follow the checklist from tag to post-release. |
| **Verification** | Dry-run the checklist for a dummy release. |

---

### W0-4 — Done when: baseline report published, all gates green on main

| | |
|---|---|
| **Steps** | 1. Publish baseline report (see W0-1). 2. Ensure main branch has all Wave 0 CI gates passing. 3. Mark Wave 0 complete in checklist only when both are true. |
| **Dependencies** | W0-1, W0-2, W0-3. |
| **Acceptance criteria** | Baseline report exists and is referenced; CI is green on main for migrations, smoke, tenant audit, RBAC, docs lint. |
| **Verification** | Open CI for main; confirm green. Open baseline report; confirm it exists. |

---

## Part C: Powerhouse v2 — Wave 1 (Deployment Speed & Trial)

### W1-1 — Minimal create path (name, email, country; rest deferred)

| | |
|---|---|
| **Steps** | 1. Define minimal payload for "create school": required = name, contact_email, country (or region_code/country_code). 2. All other fields (slug, subdomain, education profile, branding, domain, etc.) optional or derived: e.g. slug from name, subdomain from slug, default region from country. 3. Update `api_create_school` (and any wizard that calls it) to accept minimal payload and derive/default the rest. 4. Wizard or API docs should offer "minimal" path (name, email, country only) and optional "full" path for power users. |
| **Dependencies** | None. |
| **Acceptance criteria** | Caller can create a school with only name, contact_email, and country; other fields get sensible defaults or can be set later. |
| **Verification** | POST minimal JSON to create-school API; confirm 202 and provisioning starts; confirm school has default slug/region. |
| **Code refs** | `apps/schools/super_views.py` (`api_create_school`), `templates/schools/super_create_school_wizard.html`, signup flow. |

---

### W1-2 — Self-service trial API or page (POST /api/trial/ or /start-trial)

| | |
|---|---|
| **Steps** | 1. Add endpoint: POST `/api/trial/` or page `/start-trial` that accepts minimal body (e.g. name, email, country). 2. Endpoint creates school (is_active=False), sets billing_type=FREE_TRIAL and trial_end_date (e.g. now + 14 days), enqueues provisioning. 3. Return 202 with school_id and job_id (or "We'll email when ready"). 4. If page: show form (name, email, country), on submit call API or same backend logic, then show "Check your email" or status link. 5. Ensure rate limiting and optional captcha to prevent abuse. |
| **Dependencies** | W1-1 (minimal create), W1-8 (async provisioning + email). |
| **Acceptance criteria** | Unauthenticated user can request a trial via API or page; school is created in trial state; they receive clear next step (email or status URL). |
| **Verification** | Submit trial request; confirm school in DB with FREE_TRIAL; confirm 202 or success page. |
| **Code refs** | New view/url for `/api/trial/` or `start_trial`; `apps/schools/models.py` (billing_type, trial_end_date). |

---

### W1-3 — Contact email required in api_create_school; 400 if missing

| | |
|---|---|
| **Steps** | 1. In `api_create_school`, add validation: if `contact_email` is missing or blank after strip, append `"contact_email is required"` to `errors`. 2. Return `JsonResponse({"errors": errors}, status=400)` before creating school when errors non-empty. 3. Ensure API docs or OpenAPI spec list contact_email as required. |
| **Dependencies** | None. |
| **Acceptance criteria** | POST without contact_email (or empty) returns 400 with errors including "contact_email is required". |
| **Verification** | POST create-school with no contact_email; expect 400. Add contact_email; expect 202. |
| **Code refs** | `apps/schools/super_views.py` (`api_create_school`). |

---

### W1-4 — Welcome email with "Set password" or magic link where supported

| | |
|---|---|
| **Steps** | 1. After provisioning completes (or when admin user is created), trigger welcome email to contact_email. 2. Email must contain either: (a) "Set password" link (token-based or one-time link), or (b) magic link to sign in. 3. Use existing `send_welcome_email` / `send_welcome_email_task`; extend so body includes set-password or magic-link URL if your stack supports it. 4. If you do not have password-set flow, document "Welcome email sent; admin must use password reset" and ensure welcome email says so. |
| **Dependencies** | Provisioning creates admin user (existing); email backend configured. |
| **Acceptance criteria** | New school admin receives welcome email with a way to set password or sign in (link or instructions). |
| **Verification** | Create school with valid contact_email; when provisioning completes, check inbox for welcome email and link/instructions. |
| **Code refs** | `apps/schools/welcome_email.py`, `apps/schools/tasks.py` (_do_provision end). |

---

### W1-5 — Seed classrooms from profile in _do_provision (1–3 default)

| | |
|---|---|
| **Steps** | 1. Locate Classroom (or equivalent) model; ensure it is tenant-scoped (school_id or schema). 2. In `_do_provision`, after academic year/terms and subjects, add: create 1–3 default classrooms (e.g. "Class 1", "Class 2", "Class 3" or from education profile’s classroom labels if available). 3. Use get_or_create so re-run does not duplicate. 4. Log event "CLASSROOMS_READY" with count. 5. If profile has no classroom seed, use 1–3 generic names. |
| **Dependencies** | Education profile and tenant context in _do_provision (existing). |
| **Acceptance criteria** | After provisioning, school has at least 1 and at most 3 default classrooms. |
| **Verification** | Create new school; when provisioning completes, list classrooms; expect 1–3. |
| **Code refs** | `apps/schools/tasks.py` (_do_provision), academics or people app Classroom model. |

---

### W1-6 — First-login checklist (classrooms, first student, attendance) with deep links

| | |
|---|---|
| **Steps** | 1. Define first-login checklist: (1) Add or view classrooms, (2) Add first student, (3) Take attendance once. 2. Add a dismissible UI component (e.g. dashboard card or modal) shown only on first login (e.g. flag on user or school: `first_login_checklist_dismissed`). 3. Each item has a deep link: e.g. classrooms → backend URL for classroom list/add; first student → add student URL; attendance → attendance URL. 4. Show checklist on backend dashboard (or teacher dashboard) when user has not dismissed it. 5. Optionally persist "done" per item (e.g. classroom count > 0, student count > 0, attendance record exists) and show checkmarks. |
| **Dependencies** | W1-5 (classrooms exist); backend URLs for students and attendance exist. |
| **Acceptance criteria** | First-time admin/teacher sees checklist with working links; can dismiss; links go to correct pages. |
| **Verification** | New user, first login; see checklist; click each link; dismiss; reload and confirm dismissed. |
| **Code refs** | Backend dashboard template, `accounts/views.py` or portal views; new template fragment or component. |

---

### W1-7 — "Your school is ready" banner or email with one CTA

| | |
|---|---|
| **Steps** | 1. When provisioning completes, send email "Your school is ready" with one clear CTA (e.g. "Open dashboard" linking to tenant backend URL). 2. Alternatively or additionally: show a one-time banner on first load of backend after provisioning ("Your school is ready — [Open dashboard]"). 3. CTA URL must be tenant-aware (correct subdomain or tenant context). |
| **Dependencies** | Provisioning completion hook; welcome email or post-provision notification. |
| **Acceptance criteria** | User receives "school is ready" message (email or banner) with one working CTA to dashboard. |
| **Verification** | Complete provisioning; check email for ready message and click CTA; or load backend and see banner and CTA. |
| **Code refs** | `apps/schools/welcome_email.py` or tasks; backend dashboard template. |

---

### W1-8 — Provisioning always async; "We'll email when ready" + status poll or webhook

| | |
|---|---|
| **Steps** | 1. Ensure create-school API always returns 202 (never synchronous completion in response). 2. If Celery is unavailable, run provisioning in background thread or sync but still return 202 and send "ready" email when done. 3. Response body must include message like "We'll email when ready" and either job_id or timeline_url for status poll. 4. Document optional webhook URL that can be called when provisioning completes (if implemented). 5. Status poll: GET endpoint (e.g. school timeline or job status) so frontend can poll until ready. |
| **Dependencies** | W1-4, W1-7 (email when ready). |
| **Acceptance criteria** | Create-school always returns 202; user can learn completion via email or status URL; no blocking wait in API. |
| **Verification** | POST create-school; get 202 and job_id/timeline_url; wait for email or poll status until completed. |
| **Code refs** | `apps/schools/super_views.py` (api_create_school), `apps/schools/tasks.py`, timeline or status view. |

---

### W1-9 — Default one approved education profile per country when none chosen

| | |
|---|---|
| **Steps** | 1. When creating school with country but no education_profile_code or education_system_ids, resolve one approved education profile for that country (e.g. default or first approved for country/region). 2. In api_create_school or _do_provision, when profile is missing, call resolver with country_code; apply that profile for provisioning (terms, subjects, etc.). 3. Document which profile is used per country (e.g. in education_profile_engine or config). |
| **Dependencies** | Education profile model and resolver (e.g. resolve_profile_for_school, region default). |
| **Acceptance criteria** | Create school with only country set; provisioning uses one approved profile for that country; terms/subjects match profile. |
| **Verification** | Create school with country "CM" or "US", no profile; confirm one profile applied and terms created accordingly. |
| **Code refs** | `apps/schools/super_views.py`, `apps/schools/tasks.py`, `apps/siteconfig/education_profile_engine.py`. |

---

## Part D: Powerhouse v2 — Wave 2 (Onboarding & Ease of Use)

### W2-1 — First-login checklist (dismissible, deep links)

Same as W1-6; ensure checklist is dismissible and has deep links. If W1-6 is done, verify and mark W2-1 done. If not, implement per W1-6 steps.

---

### W2-2 — "Sensible defaults" copy on first login (what was auto-created + link to settings)

| | |
|---|---|
| **Steps** | 1. On first login after provisioning, show short copy: "We've set up: [list of auto-created items, e.g. academic year, 3 terms, 3 classrooms, default subjects]. You can change these in [Settings link]." 2. Link to site/school settings or backend settings URL. 3. Show once (e.g. same first-login flag as checklist) or until dismissed. |
| **Dependencies** | W1-5, W1-6. |
| **Acceptance criteria** | First-time user sees what was auto-created and a link to settings. |
| **Verification** | First login; see copy and link; click link to settings. |
| **Code refs** | Backend dashboard or first-login component. |

---

### W2-3 — Empty state + "Download sample" / "Column guide" for Entity import

| | |
|---|---|
| **Steps** | 1. Find Entity import UI (e.g. bulk upload students/entities). 2. When there are no entities or import has not been used, show empty state: short message + "Download sample" (link to static CSV/Excel sample) + "Column guide" (link to doc or modal listing column names and rules). 3. Add sample file to static or media if not present. |
| **Dependencies** | Entity import view and template. |
| **Acceptance criteria** | Entity import page shows empty state with sample download and column guide. |
| **Verification** | Open entity import; confirm empty state and both links work. |
| **Code refs** | Entity/people import views and templates. |

---

### W2-4 — "Help" / "?" + KB link on Create School, Entity import, Grade import

| | |
|---|---|
| **Steps** | 1. Add a "Help" or "?" icon/link next to Create School (wizard or API), Entity import, and Grade import. 2. Link to KB article or doc (e.g. docs/CREATE_SCHOOL_GUIDE.md, entity import doc, grade import doc). 3. Optionally open in new tab. |
| **Dependencies** | None. |
| **Acceptance criteria** | All three flows have visible Help link to relevant doc. |
| **Verification** | Open each flow; click Help; confirm doc opens. |
| **Code refs** | Create school wizard template, entity import template, grade import template. |

---

### W2-5 — Teacher "Get started" line when workflow steps = 0

| | |
|---|---|
| **Steps** | 1. On teacher dashboard or workflow center, when the teacher has zero workflow steps completed (or zero classes assigned), show a "Get started" line: e.g. "You don't have any classes yet. [Add class] or ask your admin to assign you." 2. Link to appropriate add/request URL or help. |
| **Dependencies** | Teacher dashboard and workflow step data. |
| **Acceptance criteria** | Teacher with no steps sees "Get started" message and actionable link. |
| **Verification** | Log in as teacher with no assignments; see message and link. |
| **Code refs** | Teacher dashboard template, workflow center. |

---

### W2-6 — One "Import & bulk" or "Bulk operations" entry (entity, grades, letters, finance)

| | |
|---|---|
| **Steps** | 1. Add a single sidebar or menu entry: "Import & bulk" or "Bulk operations" that either: (a) links to a hub page listing entity import, grade import, bulk letters, bulk finance (invoices/payments), or (b) is a dropdown with those items. 2. Ensure entity, grades, letters, finance bulk/import are reachable from that entry. |
| **Dependencies** | Existing import/bulk views. |
| **Acceptance criteria** | One entry exposes entity, grades, letters, finance bulk operations. |
| **Verification** | Find "Import & bulk" in nav; open and reach each sub-flow. |
| **Code refs** | Sidebar config, portal or backend menu. |

---

### W2-7 — Evaluation admin empty state: "First time? Bulk Create then enter/import."

| | |
|---|---|
| **Steps** | 1. On evaluation admin (e.g. list of evaluations or setup page), when empty or no evaluations exist, show: "First time? Bulk Create then enter/import." with link to bulk create and/or import. 2. Link to existing bulk/create or import view. |
| **Dependencies** | Evals admin view and template. |
| **Acceptance criteria** | Empty evaluation admin shows message and link(s). |
| **Verification** | Open evals admin with no data; see message and links. |
| **Code refs** | Evals admin templates. |

---

### W2-8 — Replace generic errors with actionable message + KB link where relevant

| | |
|---|---|
| **Steps** | 1. Audit key user-facing error messages (login, create school, entity import, grade import, payment). 2. Replace generic "An error occurred" with specific message (e.g. "Invalid email format", "Slug already in use") and, where useful, add "Learn more: [KB link]." 3. Prefer one KB doc per flow and link to specific section if possible. |
| **Dependencies** | None. |
| **Acceptance criteria** | Critical flows show actionable error text and optional KB link. |
| **Verification** | Trigger each error type; confirm message and link. |
| **Code refs** | Views and templates that render errors. |

---

### W2-9 — Entity import: show API validation errors in UI

| | |
|---|---|
| **Steps** | 1. When entity import calls an API that returns validation errors (e.g. 400 with field errors), surface them in the UI: list per-row or per-field errors. 2. Do not only show "Import failed"; show which rows/columns failed and why. |
| **Dependencies** | Entity import API and frontend. |
| **Acceptance criteria** | User sees validation errors from API in the import UI. |
| **Verification** | Upload invalid entity file; confirm API errors shown in UI. |
| **Code refs** | Entity import view and template. |

---

### W2-10 — Grade import: user-facing message, log exception

| | |
|---|---|
| **Steps** | 1. On grade import failure, show user-facing message (e.g. "Grade import failed. Please check file format and try again.") and optional link to column guide. 2. Log full exception server-side (logger.exception) for debugging. |
| **Dependencies** | Grade import view. |
| **Acceptance criteria** | User sees friendly message; support can find exception in logs. |
| **Verification** | Trigger grade import error; check UI message and logs. |
| **Code refs** | Grade import view. |

---

### W2-11 — Search: on error "Search temporarily unavailable"; add tips in modal

| | |
|---|---|
| **Steps** | 1. When global or in-app search fails (exception or timeout), show "Search temporarily unavailable" instead of generic error. 2. In search modal or page, add short "Tips" (e.g. "Use at least 2 characters", "Check spelling") in a collapsible or always-visible section. |
| **Dependencies** | Search view and template. |
| **Acceptance criteria** | Search error shows friendly message; tips visible in search UI. |
| **Verification** | Simulate search failure; see message. Open search; see tips. |
| **Code refs** | Search view and template. |

---

### W2-12 — Breadcrumbs on all 2+ level flows

| | |
|---|---|
| **Steps** | 1. List flows that have 2+ levels (e.g. Backend → Workflow Center → Step; Admin → Model → Add; Entity → Detail → Edit). 2. Add breadcrumb component to each: e.g. "Backend > Workflow Center > Add student". 3. Each segment should link to the corresponding level where appropriate. |
| **Dependencies** | None. |
| **Acceptance criteria** | Every 2+ level flow has visible breadcrumbs with links. |
| **Verification** | Walk each flow; confirm breadcrumbs present and correct. |
| **Code refs** | Base template or breadcrumb include; each flow template. |

---

## Part E: Powerhouse v2 — Wave 3 (Flexibility Engine)

### W3-1 — Tenant-level or configurable choices for key enums (relationship, student status, dashboard view)

| | |
|---|---|
| **Steps** | 1. Identify key enums: e.g. relationship (guardian, father, mother), student status (active, graduated, transferred), dashboard default view (cards, list). 2. Allow tenant (school or site settings) to override or extend choices (e.g. add "Sponsor", or reorder). 3. Store in School.settings or SiteSettings JSON; use in forms and serializers. 4. Document which enums are configurable and how. |
| **Dependencies** | None. |
| **Acceptance criteria** | At least relationship, student status, and one dashboard view option are configurable per tenant. |
| **Verification** | Change tenant settings; confirm dropdowns/options update. |
| **Code refs** | SiteConfig/School.settings, relationship/status/dashboard views. |

---

### W3-2 — "Validation & rules" in tenant/site settings (admission pattern, file types/sizes, phone regex, refund reasons)

| | |
|---|---|
| **Steps** | 1. Add a "Validation & rules" section in tenant or site settings. 2. Include: admission number pattern (regex), allowed file types/sizes for uploads, phone number regex, refund reasons (list or free text). 3. Use these in validation (admission form, file upload, phone field, finance refund). 4. Persist in School.settings or SiteSettings. |
| **Dependencies** | None. |
| **Acceptance criteria** | Admin can set admission pattern, file rules, phone regex, refund reasons; they are applied in respective flows. |
| **Verification** | Set pattern; try invalid admission number; set file size; try oversized upload; set phone regex; try invalid phone. |
| **Code refs** | Site config models, validation helpers, settings UI. |

---

### W3-3 — Create school: "Skip for now" on Branding/Domain with "set later" message

| | |
|---|---|
| **Steps** | 1. In create-school wizard, on Branding and/or Domain step, add "Skip for now" button or link. 2. When skipped, show short message: "You can set branding and custom domain later in School settings." 3. Allow wizard to complete without branding/domain; store empty or defaults. |
| **Dependencies** | Create school wizard. |
| **Acceptance criteria** | User can skip branding and domain; sees "set later" message; school is created. |
| **Verification** | Run wizard; skip branding/domain; complete; confirm school created and message shown. |
| **Code refs** | `templates/schools/super_create_school_wizard.html`, wizard view. |

---

### W3-4 — Document FEATURE_GATE_PATH_MAP and feature_registry; admin/config UI to enable/disable modules per school

| | |
|---|---|
| **Steps** | 1. Document where FEATURE_GATE_PATH_MAP (or equivalent) is defined and how it maps paths to feature flags. 2. Document feature_registry (or list of modules) and how they gate UI/API. 3. Add admin or config UI (e.g. School edit or super-admin) to enable/disable modules per school (e.g. library, transport, canteen). 4. Ensure backend and portal respect these flags (hide nav, return 403, or redirect). |
| **Dependencies** | Existing feature gate logic. |
| **Acceptance criteria** | Docs describe path map and registry; admin can toggle modules per school; toggles take effect. |
| **Verification** | Read docs; change module in UI; confirm nav/access changes. |
| **Code refs** | `apps/schools/tests/test_plan_and_feature_gate.py`, settings, feature decorators. |

---

### W3-5 — Per-tenant theme pack (School or BrandSettings.theme_pack_id)

| | |
|---|---|
| **Steps** | 1. Add theme_pack_id (FK or string code) to School or BrandSettings. 2. Define theme packs (e.g. default, dark, compact) with CSS/JSON. 3. In context processor or middleware, resolve tenant’s theme pack and pass to templates (e.g. THEME_PACK). 4. Apply theme pack CSS class or variables on body or main container. |
| **Dependencies** | BrandSettings or School model. |
| **Acceptance criteria** | Tenant can have a theme pack; front-end reflects it (colors/layout). |
| **Verification** | Set theme pack for school; load portal/backend; confirm theme applied. |
| **Code refs** | Theme pack model/config, context processor, base template. |

---

## Part F: Powerhouse v2 — Waves 4–17

**How to execute:** For each wave, (1) expand the theme into a table of sub-items (like Part C/D), (2) implement each sub-item with steps/acceptance/verification, (3) run Wave 0 CI gates, (4) mark wave done in checklist.

Below is the **expansion template** for each wave; use it to create a wave-specific doc or section (e.g. `docs/WAVE_4_TASKS.md`).

### W4 — Teacher Attendance Core

| Sub-item | Description | Status |
|----------|-------------|--------|
| W4-1 | Zero-click attendance (e.g. mark-all-present by default, one click to save) | ⬜ |
| W4-2 | Seating chart view or link | ⬜ |
| W4-3 | Mark-all-present action | ⬜ |
| W4-4 | Absent parent notification (trigger email/SMS when absent) | ⬜ |
| W4-5 | Optional QR or RFID integration point (document or stub) | ⬜ |

---

### W5 — Scheduling & SOW

| Sub-item | Description | Status |
|----------|-------------|--------|
| W5-1 | Drag-drop scheduler UI | ⬜ (roadmap) |
| W5-2 | Conflict checks (time/room) | ✅ (API: GET /api/schedules/<id>/conflicts/) |
| W5-3 | Abbreviated day support | ⬜ (roadmap) |
| W5-4 | Recurring events | ⬜ (roadmap) |
| W5-5 | Live timeline view | ⬜ (roadmap) |
| W5-6 | Shift/push SOW (syllabus) when day canceled | ⬜ (roadmap) |

---

### W6 — Lesson & Standards

| Sub-item | Description | Status |
|----------|-------------|--------|
| W6-1 | Resource attachments to lessons | ✅ (LessonPlanAttachment, Add resource flow, list on Lesson Notes) |
| W6-2 | Standards tagging | ✅ (CourseSyllabus.curriculum_nodes M2M, admin filter_horizontal) |
| W6-3 | AI lesson assistant (optional integration) | Doc only (roadmap in WAVE_6_LESSON_STANDARDS.md) |
| W6-4 | Teacher wellness (e.g. reminder or link) | ✅ (Wellness link in sidebar, /portal/teacher/wellness/) |

---

### W7 — Admin Command Center

**See [PART_F_WAVES_7_TO_17.md](PART_F_WAVES_7_TO_17.md) for code refs and verification.**

| Sub-item | Description | Status |
|----------|-------------|--------|
| W7-1 | Finance dashboard (overview, overdue) | ✅ |
| W7-2 | Overdue list + reminders | ✅ |
| W7-3 | Staff matrix view | Roadmap |
| W7-4 | Leave overlay (calendar or list) | ✅ (employee leave) |
| W7-5 | RBAC visibility and lifecycle | ✅ |

---

### W8 — Staff Operations

| Sub-item | Description | Status |
|----------|-------------|--------|
| W8-1 | Admissions filters | Roadmap |
| W8-2 | Inventory/library borrow-return | ✅ partial |
| W8-3 | Transport alerts | Roadmap |
| W8-4 | Device management (optional) | Roadmap |

---

### W9 — Parent Engagement

| Sub-item | Description | Status |
|----------|-------------|--------|
| W9-1 | Progress card view | ✅ |
| W9-2 | Attendance alerts | ✅ |
| W9-3 | One-click payment + receipt | ✅ |
| W9-4 | Communication hub | ✅ |
| W9-5 | Photo search (optional) | Roadmap |

---

### W10 — Requests, Automation, Calendar

| Sub-item | Description | Status |
|----------|-------------|--------|
| W10-1 | Unified requests dashboard | ✅ |
| W10-2 | Automation visibility (list/log) | Roadmap |
| W10-3 | Unified school calendar | ✅ |

---

### W11 — API Center, Webhooks, EMIS, LTI

| Sub-item | Description | Status |
|----------|-------------|--------|
| W11-1 | API Center (keys, docs) | ✅ |
| W11-2 | Webhooks (outgoing, logs) | ✅ |
| W11-3 | EMIS export alignment | ✅ partial |
| W11-4 | LTI integration point | ✅ |

---

### W12 — Observability, Retention, Backup

| Sub-item | Description | Status |
|----------|-------------|--------|
| W12-1 | Tenant health metrics | ✅ |
| W12-2 | Retention/purge (GDPR/compliance) | ✅ |
| W12-3 | Backup runbooks | Roadmap |
| W12-4 | Redis cache usage/docs | Roadmap |

---

### W13 — SSO, Push, Exports, Notification Center

| Sub-item | Description | Status |
|----------|-------------|--------|
| W13-1 | SSO config and login (already started in Part A) | ✅ |
| W13-2 | Push notification delivery | ✅ partial |
| W13-3 | Exports (reports, data) | ✅ |
| W13-4 | Notification Center UI | ✅ |

---

### W14 — Global Differentiators

| Sub-item | Description | Status |
|----------|-------------|--------|
| W14-1 | normalized_value / Rosetta (grade conversion) | ✅ |
| W14-2 | Curriculum templates | ✅ partial |
| W14-3 | Compliance engine | ✅ |
| W14-4 | AI narrative (reports) | Roadmap |
| W14-5 | RTL support | ✅ partial |
| W14-6 | Subscription/hierarchy | Roadmap |
| W14-7 | Transcript vault | ✅ partial |

---

### W15 — Performance

**See [W15_PERFORMANCE.md](W15_PERFORMANCE.md) for cache pattern and hardening checklist.**

| Sub-item | Description | Status |
|----------|-------------|--------|
| W15-1 | Redis tenant-config cache | ✅ (doc + existing cache usage) |
| W15-2 | High-traffic hardening (docs + key fixes) | ✅ (doc) |

---

### W16 — Canteen & Cahier

| Sub-item | Description | Status |
|----------|-------------|--------|
| W16-1 | Configurable modules (feature flags) | ✅ |
| W16-2 | Minimal canteen flow | Roadmap |
| W16-3 | Cahier (journal) minimal flow | ✅ |

---

### W17 — Final Certification

| Sub-item | Description | Status |
|----------|-------------|--------|
| W17-1 | Full regression suite run | Roadmap |
| W17-2 | Security/compliance evidence pack | ✅ |
| W17-3 | Rollout/rollback procedure | Roadmap |
| W17-4 | Cutover checklist | Roadmap |

---

## Part G: RunMyCampus Standards Audit — Partials to complete

**Status and verification:** See **[PART_G_STANDARDS_STATUS.md](PART_G_STANDARDS_STATUS.md)**. All S1–S13 are either implemented (in `/api/v1/` or elsewhere) or documented as roadmap; checklist marked ✅.

### S1 — API alignment: /api/v1/ layer (tenants/provision, config/education-dna, tenants/{id}/modules)

| | |
|---|---|
| **Steps** | 1. Add or alias routes under `/api/v1/`: e.g. POST `/api/v1/tenants/provision`, GET `/api/v1/config/education-dna`, GET `/api/v1/tenants/{id}/modules`. 2. Delegate to existing views or new views that match Standards contract. 3. Document in API docs (OpenAPI or markdown). |
| **Dependencies** | None. |
| **Acceptance criteria** | Client can call provision and config/tenant endpoints under /api/v1/. |
| **Verification** | curl or test client to each URL; confirm 200/202 and response shape. |
| **Code refs** | `apps/api/urls_v1.py`, `apps/api/views_v1.py`. |

---

### S2 — Template injector: one-click British/WAEC/Vocational at signup

| | |
|---|---|
| **Steps** | 1. At signup or create-school, offer templates: British (e.g. Michaelmas/Lent/Trinity), WAEC, Vocational. 2. Selecting one injects the matching education profile and term labels (and optionally subject set). 3. Persist choice in school settings and apply in provisioning. |
| **Dependencies** | Education profiles for British, WAEC, Vocational. |
| **Acceptance criteria** | User can pick one template at signup; school is provisioned with that system’s terms and config. |
| **Verification** | Sign up with each template; confirm terms and profile. |
| **Code refs** | Signup/wizard, education_profile_engine. |

---

### S3 — Admissions: document upload + AI document scanner + acceptance workflow

| | |
|---|---|
| **Steps** | 1. Admissions flow: applicant uploads document(s). 2. Optional: integrate AI document scanner (e.g. extract name, DOB, grades) and pre-fill form. 3. Acceptance workflow: Accept → create StudentProfile, send email. 4. Document the flow and where AI is optional. |
| **Dependencies** | Admissions model and views. |
| **Acceptance criteria** | Document upload; optional AI pre-fill; Accept creates student and sends email. |
| **Verification** | Upload doc; accept; confirm student and email. |
| **Code refs** | Admissions app, student creation. |

---

### S4 — GET /api/v1/student/passport/{global_id}; POST /api/v1/student/transfer

| | |
|---|---|
| **Steps** | 1. Implement GET `/api/v1/student/passport/{global_id}` (or equivalent) returning minimal student passport (e.g. id, name, school, status). 2. Implement POST `/api/v1/student/transfer` with body (from_school, to_school, student_id or global_id) to initiate transfer. 3. Secure with API key or auth; document. |
| **Dependencies** | Student model with global_id or equivalent. |
| **Acceptance criteria** | Passport endpoint returns data; transfer endpoint accepts request and initiates process. |
| **Verification** | Call passport with valid global_id; call transfer with valid payload. |
| **Code refs** | `apps/api/views_v1.py`, student models. |

---

### S5 — GET /api/v1/finance/exchange-rate (or document as optional)

| | |
|---|---|
| **Steps** | 1. Implement GET `/api/v1/finance/exchange-rate` returning e.g. { "base": "USD", "rates": { "XAF": 600, ... } } or document as optional/roadmap. 2. If implemented, use region or tenant currency config. |
| **Dependencies** | None. |
| **Acceptance criteria** | Endpoint exists and returns rates, or doc says "optional/roadmap". |
| **Verification** | GET exchange-rate; check response or doc. |
| **Code refs** | API views, finance or siteconfig. |

---

### S6 — Attendance: CSV export, bulk PATCH, optional QR/RFID; zero-click visual flow

| | |
|---|---|
| **Steps** | 1. Attendance: add CSV export (date range, class). 2. Bulk PATCH (e.g. mark multiple students present/absent in one request). 3. Document or stub QR/RFID integration. 4. Zero-click visual flow: minimal clicks to complete daily attendance (see W4). |
| **Dependencies** | Attendance models and UI. |
| **Acceptance criteria** | CSV export works; bulk PATCH works; zero-click flow documented or implemented. |
| **Verification** | Export CSV; PATCH bulk; run zero-click flow. |
| **Code refs** | Attendance app. |

---

### S7 — Scheduler: REST API for generate/validate; optional global-shift (SOW shift)

| | |
|---|---|
| **Steps** | 1. REST API: POST generate (e.g. generate schedule for term), POST or GET validate (check conflicts). 2. Optional: global-shift to push SOW when a day is canceled. 3. Document endpoints. |
| **Dependencies** | Scheduler model and logic. |
| **Acceptance criteria** | Generate and validate endpoints exist and documented; global-shift optional. |
| **Verification** | Call generate and validate; document or test shift. |
| **Code refs** | Scheduler app, API. |

---

### S8 — Syllabus: "Planned vs Actual" pacing; global shift when day canceled

| | |
|---|---|
| **Steps** | 1. Syllabus view or report: show "Planned vs Actual" pacing (e.g. by week or topic). 2. When a day is marked canceled, support global shift of planned dates (or document). |
| **Dependencies** | Syllabus/planning model. |
| **Acceptance criteria** | Pacing visible; shift on cancel documented or implemented. |
| **Verification** | View pacing; cancel day and check shift. |
| **Code refs** | Syllabus/planning app. |

---

### S9 — Lesson planner: AI-generated plans/quizzes from standards

| | |
|---|---|
| **Steps** | 1. Lesson planner: optional integration to generate plans or quizzes from standards (e.g. AI or template). 2. Document or implement one path (e.g. "Generate from standard" button). |
| **Dependencies** | Lesson and standards models. |
| **Acceptance criteria** | Teacher can generate plan/quiz from standard (or doc explains roadmap). |
| **Verification** | Use generate feature or read doc. |
| **Code refs** | Lesson planner, standards. |

---

### S10 — Intervention: LLM recovery-roadmap API; Recovery Rate metric in super-admin

| | |
|---|---|
| **Steps** | 1. Intervention: optional LLM API that returns "recovery roadmap" (e.g. suggested actions). 2. Super-admin: add Recovery Rate metric (e.g. % of at-risk students improved). 3. Document data source and formula. |
| **Dependencies** | Intervention/at-risk model, super-admin dashboard. |
| **Acceptance criteria** | Recovery roadmap API or doc; Recovery Rate visible in super-admin. |
| **Verification** | Call API or view metric. |
| **Code refs** | Intervention app, super views. |

---

### S11 — Vocational: Certifications model with expiry_date, watchdog alerts; REST APIs (log-hours, verify-skill, digital-badge)

| | |
|---|---|
| **Steps** | 1. Certifications model (or extend existing): include expiry_date. 2. Watchdog: alert when certification near expiry. 3. REST: log-hours, verify-skill, digital-badge (or document). |
| **Dependencies** | Vocational/certification model. |
| **Acceptance criteria** | Certifications have expiry; alerts exist; at least one of log-hours/verify-skill/badge API exists or documented. |
| **Verification** | Create cert with expiry; trigger alert; call API. |
| **Code refs** | Vocational app, API. |

---

### S12 — Transport: real-time tracking or integration point + parent ETA (or document as roadmap)

| | |
|---|---|
| **Steps** | 1. Transport: either (a) real-time tracking + parent ETA, or (b) integration point + doc that describes roadmap. 2. Document in Standards or product doc. |
| **Dependencies** | Transport model/views. |
| **Acceptance criteria** | Tracking/ETA or integration point documented. |
| **Verification** | Read doc or test tracking. |
| **Code refs** | Transport app, docs. |

---

### S13 — Super-admin: Global Pulse Map visualization; Tenant Health Monitor (security/DB metrics)

| | |
|---|---|
| **Steps** | 1. Super-admin: add "Global Pulse Map" (e.g. map or list of tenants with status). 2. Tenant Health Monitor: security and DB metrics per tenant (or link to existing health). 3. Restrict to superuser. |
| **Dependencies** | Super-admin dashboard, health/observability. |
| **Acceptance criteria** | Pulse map visible; tenant health metrics visible. |
| **Verification** | Log in as super; open Pulse Map and Health Monitor. |
| **Code refs** | Super views, observability. |

---

## Execution Order Summary

1. **Part A** (B1–B9) — in table order; B2 before B3, B4/B5/B6/B7/B8 independent.
2. **Part B** (W0-1–W0-4) — in order; W0-4 last.
3. **Part C** (W1-1–W1-9) — W1-1 and W1-3 first; W1-2 after W1-1 and W1-8; W1-4/W1-7 after provisioning; W1-5 in _do_provision; W1-6/W1-7 UI; W1-9 in resolver.
4. **Part D** (W2-1–W2-12) — in table order; W2-1 can match W1-6.
5. **Part E** (W3-1–W3-5) — in table order.
6. **Part F** (W4–W17) — expand each wave into sub-items (as above), then execute in wave order; run CI after each wave.
7. **Part G** (S1–S13) — can run in parallel with relevant v2 waves (e.g. S6 with W4, S7/S8 with W5); otherwise after corresponding wave.

---

## Sign-off and Checklist Updates

- After each **item** (single row in the merged checklist): run its Verification; then set status to ✅ in `THREE_PLANS_MERGED_CHECKLIST.md`.
- After each **part**: run full Part verification (smoke, critical paths); then move to next part.
- After **Part F** (all waves): run full regression and W17 certification.
- Keep this guide and the merged checklist in sync: any new sub-item added during execution should be reflected in the checklist or wave expansion table.

No shortcuts: every sub-step and verification must be completed before marking an item done.
