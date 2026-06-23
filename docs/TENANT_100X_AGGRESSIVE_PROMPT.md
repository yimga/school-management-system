# TENANT 100X — Aggressive Autonomous Execution Prompt

> **Purpose.** This is a self-contained, role-structured prompt that drives the tenant 100X
> initiative end-to-end with minimal owner intervention. Feed it to a fresh session (or a
> moderator + agent fan-out) to continue the work. It already contains the audit findings,
> so the executor does NOT re-discover — it builds.
>
> **North Star.** Become the **Linux / Shopify / Salesforce of education** — the open,
> extensible, configurable, developer-and-admin-empowering platform that beats PowerSchool,
> Infinite Campus, and Ellucian on *simplicity, self-service, and local-first fit*. Every
> decision is measured against: does this make a school feel the platform was built for *their*
> country, *their* terminology, *their* workflow — in ≤3 clicks, with zero stress?

---

## 0. Owner directives (verbatim, non-negotiable)

1. **Footer:** same content, **vertical size reduced by 50%.**
2. **Tenant configuration power:** tenants must self-configure everything that pertains to them —
   school name, logo, branding, footer content, dashboard appearance. They get a **frontend
   (day-to-day)** and a **backend (configuration)**.
3. **Sidebar "Recent Activity":** remove it from the sidebar (it makes the page unnecessarily
   long) and relocate it somewhere appropriate.
4. **Premium luxury surfaces:** every page surface next-level, intelligently using vertical AND
   horizontal space, no wasted empty/black space. `/super/` and `/admin/` operator surfaces are
   the **reference pattern** — they consume space well and are full-width within the dashboard.
   Tenant surfaces must match that full-bleed behavior **platform-wide**.
5. **Horizontal + vertical full-bleed (NEW):** tenant surfaces currently leave **black/empty
   space at the bottom and on the sides** — content does not fully consume the provided
   surface. This is platform-wide and must be fixed at the shell level.
6. **Local-first:** nothing hardcoded. Everything (exam names, terminology, currency, dates,
   menu labels, workflows) seeded by the school's **country / locality / region**. "If Cameroon
   calls an exam GCE, a US school must NOT see GCE." Extrapolate platform-wide.
7. **100% wiring:** AI, copilot rails, tools, help, knowledgebase — everything tenants use must
   be properly wired, no shortcuts; tenant ↔ multi-tenant system is symbiotic.
8. **RBAC:** the user who **created the school is ADMIN and SUPER ADMIN by default**; they can
   **release/transfer** that role to a chosen person; **multi-admin and multi-superadmin** are
   allowed — it is a ROLE.
9. **Offboarding/closure placement (NEW):** offboarding & school closure should **not** sit in
   the tenant's daily profile/workspace. Industry leaders (PowerSchool/Infinite Campus/Ellucian)
   treat closure as gated, compliance-bound, deactivate-not-delete. Move it out; keep
   self-service data export as our anti-legacy differentiator.
10. **100X everything:** creativity, simplicity, innovation, AI-assisted. Reduce clicks **≥50%**
    (solve tenant tasks in **3 clicks or less**). Don't break what works.
11. **Process:** audit → fix → test → validate → audit → fix → test → validate, **in a loop until
    no gaps remain.** Provide **browsable before/after HTML** for every visual change so the owner
    can tweak before it ships.

---

## 1. Operating doctrine (how every agent must work)

- **Verify-first.** Sub-agents and memory have repeatedly produced confident-wrong root causes in
  this codebase. NEVER fix from a theory — read the cited `file:line` first and confirm.
- **Token-only CSS.** Use semantic tokens (`--surface-bg/canvas/elevated/popover`, `--text-*`,
  `--hairline`, `--school-primary/-accent`). Never inline hex / off-token color. All zero-tolerance
  gates stay **0** (off-token, theme-locked, undefined-css, inline-style, render-safety,
  theme-attribute-contract, layout-frame-guard, import-reference-integrity, bare-except, etc.).
- **No hardcoding.** Route every value through the 7-layer cascade (RuntimeDefaults → env → user
  prefs → i18n → feature flag → DB fixture → constant). Push values UP, never inline.
- **Cascade-first, adoption-second.** Land the primitive/migration/resolver before any template
  adoption. Never sweep templates alongside an unsettled primitive.
- **Path-scoped commits.** `git commit -F <msgfile> -- <explicit paths>`. NEVER `git add -A`
  (a parallel peer session uses it and will absorb your files). New untracked files: `git add
  <file>` first. Peer advances origin frequently → `git rebase --autostash origin/main` or a
  throwaway worktree off origin/main when the main tree is perpetually dirty.
- **Platform-wide testing.** Testing/migration/validation must NOT stop at the tenant — it is
  platform-wide. No-DB `SimpleTestCase` runs <1s; for DB suites use `pytest <file> --reuse-db`
  against the on-disk keepdb (`.django_test_dbs/default.sqlite3`) — NOT the ~30-min in-memory
  rebuild.
- **Browsable before/after.** Every visual change ships with a `var/design-previews/*-browsable.html`
  so the owner verifies without guessing.
- **Service worker.** Bump `CACHE_VERSION` only when shipping new CSS/JS that must invalidate; the
  peer often holds `service-worker.js` — coordinate or skip if network-first covers it.
- **Don't break working code.** Progressive enhancement that COMPOSES existing primitives beats
  rewrites. Smart-skip opt-outs, fail-soft, no clobbering author-placed content.

---

## 2. Audit findings already in hand (build on these — do not re-discover)

### 2A. Surface / UX (wasted space, click-count, page-awareness)
Reference shells: `templates/portal_base.html` + includes. Per-surface map:

| Surface | View | Template | Key problem | Top fix |
|---|---|---|---|---|
| `/studio/` | `apps/studio_os/views.py::studio_shell` (~1312) | `templates/studio_os/shell.html` | redundant `container-fluid py-2 px-0 px-md-2` (`:33`); generic mode grid | drop padding; tenant-aware mode priority |
| `/studio/hubs/workflow/` | `apps/accounts/views_workflow.py::workflow_center` (~308) | `templates/accounts/workflow_center.html` | **genericness 3/10** — same workflow regardless of term system/modules/role | filter by enabled modules + role; quick-action pills |
| `/siteconfig/preferences/` | `apps/siteconfig/views.py::user_preferences` (~1319) | `user_preferences.html` + `partials/user_preferences_body.html` | **~25% wasted** — 4-layer container/card/header/body padding nest | reduce nesting; 2-col desktop; floating theme toggle; success toast |
| `/authentication/backend/` | `apps/accounts/views_dashboard.py::backend_dashboard` | `templates/accounts/backend_dashboard.html` | grid gaps; empty hero | density pass |
| `/authentication/profile/` | `apps/accounts/views.py::user_profile` (~335) | `templates/accounts/profile.html` | oversized header (`:19-41`); 8-button quick-actions column | single-line hero; gauge above fold; role-filter actions |
| `/finance/` | `apps/finance/views.py::dashboard` | `templates/finance/dashboard.html` | **3 redundant status strips** (`:26,29,30`); hardcoded `value="68"` readiness | merge strips; dynamic score; due-date column |

**Platform-wide patterns:** compounding container/card padding stacks; inter-section margin
collapsing (`mb-3` additive on mobile); sidebar/content column gap; **footer dead space**; and the
NEW **full-bleed gap** — tenant content sits in a constrained column with **black space at bottom
and sides** while operator `/super/` + `/admin/` shells are full-width within the dashboard.

### 2B. Local-first (the headline: excellent infra, near-zero adoption)
The platform ALREADY HAS a full localization spine — **the problem is non-adoption, not missing
infra.** Do NOT rebuild; ADOPT.

- **Infra that exists:** `apps/schools/models.py` tenant identity (`country_code` ~:296,
  `default_region`→`RegionConfig`, `subdivision`, `timezone`, `default_language`, `sub_system`);
  full `apps/registries/models.py` catalog (`CountryRegistry`, `CurrencyRegistry`, `LocaleRegistry`,
  `GradeScaleRegistry`, `AcademicTerminologyRegistry`, `CalendarSystemRegistry`, +
  `TenantGradeScaleOverride`); `apps/siteconfig/country_localization_service.py` (country-pack
  resolver); `apps/siteconfig/terminology_service.py` + `lexicon_catalog.LEXICON_REGISTRY` (50+ keys,
  injected into EVERY shell as `{{ lexicon.* }}` via `context_processors.lexicon_context`);
  resolvers `registries/grade_scale_resolver.py`, `registries/currency.py`,
  `siteconfig/tenant_config.py::format_currency_tenant`.
- **The decisive gap:** only ~7 templates reference `lexicon.` at all (4 just emit the meta tag).
  The terminology engine is fully built + globally injected but **almost entirely unconsumed** —
  tenant UI still prints hardcoded "Principal", "First Term", "Report Card".
- **P0 — Exam boards (the reported GCE bug):** `apps/academics/models.py:372-422,670` —
  `CertificationExamSession.Board`/`.Level` are a **global TextChoices used directly as field
  choices with NO country/tenant filter.** A US school's dropdown shows GCE/WAEC/Baccalauréat.
  FIX: create `ExamBoardRegistry(country_code, …)` + per-tenant enabled-boards (clone the
  `GradeScaleRegistry`/`TenantGradeScaleOverride` pattern); filter the field's form choices by
  `school.country_code`. Migrate the enum + `seed_blueprint_policy_packs.py` exam strings into rows.
- **P0 — Cameroon grading defaults baked into the model:** `apps/evals/models.py:59-98` —
  `AssessmentWeights` defaults `grade_a_min=18.0…`, `grading_scale="numeric_0_20"`, and **`region`
  default `"cameroon_anglophone"`** — every new tenant worldwide inherits Cameroon grading. Route
  through `resolve_grade_scale_for_tenant(school)`; neutralize `pass_mark = score_scale//2`,
  letter tables in `grading.py`/`bulk_gradebook.py`.
- **P1 — Currency `default="USD"`** on ~18 model fields (schools/finance/marketplace/
  school_events/schoolops) → convert to the callable pattern `apps/billing/models.py` already uses;
  swap template `$`/`value="USD"` literals for `|format_currency_tenant`.
- **P1 — Adopt `{{ lexicon.* }}`** across tenant UI (roles, terms, report cards, marks entry,
  sidebar). Engine + keys exist; this is a sweepable adoption wave like the prior `.rmc-*` waves.
- **P2 — Date/week-start:** `static/js/admin-dashboard-security.js:243` uses JS `getDay()` ignoring
  configured `first_day_of_week`; hardcoded `|date:"M j, Y"` + `strftime("%d/%m/%Y")`
  (`accounts/views_certification.py:268`) → locale-aware tag.
- **P3 — Term-count:** relax `academics/models.py:124-135` `Term.position` 1-4 constraint to the
  country-pack's term count.

### 2C. RBAC / creator-as-owner
- **Creation flow:** `apps/schools/tasks.py::ensure_admin_user_for_school` (~533) sets the creator
  to **ADMIN only** (`:558-577`), `is_primary=True`. Never SUPERADMIN, never `is_staff/is_superuser`.
  `apps/schools/signup_views.py:1640` calls it on email verification. **`School` has NO
  `owner`/`created_by` FK** — the only creator anchor is the `is_primary=True` membership.
- **Role model:** 25 roles in `User.Role` (`accounts/models.py:150-176`). Two stores: `User.role`
  CharField + `User.roles` M:N to per-tenant `AccessRole`. `SchoolMembership.role` (`schools/
  models.py:1012`). Rank SUPERADMIN=110 > ADMIN=100 (`permissions.py:26`).
- **⚠️ The SUPERADMIN trap (owner decision required):** `CONTROL_PLANE_ROLE_CODES={"SUPERADMIN"}`
  and `middleware.py:462-471` **redirect a tenant user with `role=="SUPERADMIN"` OFF the tenant
  host to `/super/`.** So literally assigning the creator `role=SUPERADMIN` would lock them out of
  their own school. "SUPER ADMIN" as the owner means it = the **top TENANT role**, not the
  platform-operator SUPERADMIN. **Recommended:** introduce a distinct tenant-owner role (e.g.
  `OWNER` / `SCHOOL_SUPERADMIN`) rather than overloading platform SUPERADMIN.
- **Multi-admin:** ✅ already structurally supported — `SchoolMembership` uniqueness is
  `(user, school)` not `(school, role)`; two ADMINs coexist.
- **Transfer/release:** ❌ no endpoint exists to change an existing member's role or hand off admin.
  Build it in `apps/accounts/views_tenant_identity.py`, gated by `_can_manage_tenant_identity()`,
  with a **last-owner guard** (refuse to demote the final owner → no orphaned tenant).
- **Consolidate:** four independent admin-role lists drift (`ADMIN_LIKE_ROLES` in
  `auth_backends_role_perms.py:32`, `_IDENTITY_HUB_MANAGE_ROLES` in `views_tenant_identity.py:45`,
  per-view frozensets, `ROLE_RANK`). Point them all at one helper in `platform_runtime/role_registry.py`.

### 2D. Wiring (verdict: correctly wired; gaps are CONTENT, not wiring)
- **Copilot rail:** correctly wired. JS loaded `portal_base.html:707-708`; send URL host-correct
  (`portal:copilot_rail_*`); `general_chat` passes RBAC for any authed user; **render is independent
  of `RUNMYCAMPUS_AI_ENABLED`** (rules-fallback mode), so governance-off does NOT read as broken.
- **Tools rail:** wired; all chips resolve host-correct. Minor: `voice` chip shows despite
  "off-by-default" docstring (`platform_surface_config.py:354-363`).
- **Help:** wired. **Content gap:** tenant "About this page"/"Your flow" intel map
  (`control_plane_page_intel.py:32-75`) has **zero tenant routes** → generic fallback. Add tenant
  routes (portal dashboards, academics, finance, people).
- **Knowledgebase:** wired but **empty by default** — no `post_migrate`/auto-seed; tenant sees
  "No categories available yet." Seed starter articles via onboarding step or guarded `post_migrate`.
- **Nav links:** no dead links on tenant surfaces (the old "Notifications row is dead" memory note
  is STALE — it resolves to `accounts:user_notifications`).

### 2E. The screenshot bugs (NEW, observed on the live tenant)
- **Full-bleed:** large **black dead-zone** below + beside content; tenant shell not consuming the
  surface like `/super/`+`/admin/`. Root to investigate: tenant shell max-width container +
  background/min-height in `portal_base.html` / `portal-base-shell.css` vs the operator shells'
  full-width grid.
- **Label-doubling:** sidebar + section labels render **twice** ("Approval Hub / Approval Hub",
  "Lifecycle playbook / Lifecycle playbook", "Onboarding playbook / Onboarding playbook",
  "RBAC & Access Control / RBAC & Access Control"). The sidebar template has single instances
  (`portal_sidebar.html:242` Approval Hub once) → suspect a CSS `::after{content:…}` ghost, a
  doubled include, or a text-shadow render artifact. **Investigate verify-first before fixing.**
- **Offboarding in workspace:** "Offboarding & closure / Close account workspace" renders in the
  daily tenant lifecycle hub — move it (see §3, Role F).
- **Recent Activity:** at sidebar bottom (`portal_sidebar.html:261-279`), RBAC-gated to non-
  student/teacher/parent. Relocate per owner.

---

## 3. Role-structured workstreams

Each role is an agent (or batch of agents) the moderator dispatches. Roles run mostly in parallel;
the moderator synthesizes, ships path-scoped, and loops. Every role obeys §1 doctrine.

### Role A — Principal Shell Architect (full-bleed + footer + density) — HIGHEST LEVERAGE
**Mission:** make every tenant surface consume the full dashboard surface like `/super/`+`/admin/`,
kill the black dead-zone, halve the footer, and standardize density tokens.
- A1. **Full-bleed shell:** diagnose the constrained-column + black-background in `portal_base.html`
  + `static/css/portal-base-shell.css`; match the operator full-width grid. Confirm min-height/
  background extends so no black gap below content. Browsable before/after.
- A2. **Footer −50% vertical:** same content, half the height (token-driven padding/line-height,
  fold rows inline) — mirror the prior chrome-strip "Compact" pass; put overrides in
  `rmc-class-grammar-ext.css` if the base file is peer-dirty.
- A3. **Density tokens:** `--shell-vertical-padding`, `.page-section` margin-collapse utility,
  responsive grid gaps — applied platform-wide via the class grammar, not per-template.
- A4. **Label-doubling bug:** verify-first root cause; fix at source.
**Acceptance:** zero black dead-zone on the 6 example surfaces + 4 shells; footer height −50%
measured; gates 0; before/after browsables.

### Role B — Localization / Local-First Engineer — HIGHEST CORRECTNESS LEVERAGE
**Mission:** adopt the existing localization spine so schools feel built-for-their-country.
- B1. **ExamBoardRegistry** (P0) + per-tenant enabled-boards + form-choice filter by
  `school.country_code`. Migration + seed + resolver + tests. This is the literal GCE-in-USA fix.
- B2. **Neutralize evals Cameroon defaults** (P0) via `resolve_grade_scale_for_tenant`.
- B3. **Currency `default="USD"` → callable** (P1) + template `|format_currency_tenant`.
- B4. **Lexicon adoption sweep** (P1): render `{{ lexicon.* }}` across tenant UI.
- B5. **Date/week-start + term-count** (P2/P3).
**Acceptance:** a US-country test tenant sees zero GCE/Cameroon/USD-hardcoded leakage; gates 0;
`scan_role_strings`/`scan_magic_numbers --compare` reconciled; platform-wide DB tests green.

### Role C — Surface/UX Elevation Engineer (per-surface premium pass)
**Mission:** apply the §2A fixes surface-by-surface to premium-luxury + ≤3-click standard.
- Per surface: reduce wasted space, raise info density, make it page-aware (module/role/term
  filtered), cut click-count, add quick-actions. Compose existing `.rmc-*` grammar + the prior
  intelligence engines (table/form/dashboard/loading/empty/detail/modal/notification).
- Provide a browsable before/after per surface; ship only after owner tweak-window where visual.
**Acceptance:** each surface ≥70% content density, primary task ≤3 clicks, page-aware copy; gates 0.

### Role D — Tenant Configuration Studio Engineer (frontend + backend config power)
**Mission:** tenants self-configure everything that pertains to them — name, logo, branding, footer
content, dashboard appearance — via a **day-to-day frontend** + a **configuration backend.**
- Extend the branding studio (already shipped: favicon, theme-default navy, logo maker, color
  controls, live preview, persistence) into a full **Tenant Config Backend**: footer content
  editor, dashboard-appearance controls, all cascading through `SiteSettings`/`RuntimeDefaults`
  (zero new hardcoding). Frontend = the daily surfaces honoring those configs live.
**Acceptance:** a tenant can change name/logo/branding/footer/dashboard look without engineering;
values persist through the cascade; gates 0.

### Role E — RBAC / Security Engineer (creator-as-owner + transfer)
**Mission:** implement §2C without breakage.
- E1. Surface the **SUPERADMIN semantics fork** to the owner (new tenant-owner role vs. middleware
  carve-out) — recommend the new `OWNER` role. **Owner decision gate before coding the role.**
- E2. Add the tenant-owner role to `User.Role`, `ROLE_RANK`, `role_registry.py` in one pass.
- E3. Set creator to owner role on creation (`tasks.py:558-582`), keep idempotency, never touch
  `is_superuser/is_staff`.
- E4. Build transfer/release endpoint in `views_tenant_identity.py` with last-owner guard + audit.
- E5. Consolidate the four admin-role lists to one registry helper.
**Acceptance:** creator is owner+admin on verify; multi-admin coexist (no IntegrityError); transfer
works + refuses last-owner demotion; non-admin caller 403; owner role NOT redirected off tenant;
`audit_role_permission_matrix` candidate_anonymous stays 0; `scan_role_strings --compare` reconciled.

**Role E — 3-VOTE-VALIDATED DESIGN (2026-06-23; supersedes the audit's loose plan).** Three
adversarial reviewers returned 2×REVISE + 1×PROCEED-WITH-CHANGES. Consensus, with the anchor
corrected:
- **DO NOT use `SchoolMembership.is_primary` as the owner anchor.** It is a per-USER "which of my
  schools is my default" pointer (`schools/models.py:1100-1103`), read by the login/onboarding
  home-school resolver (`accounts/views.py:4044-4057`, `views_owner_onboarding.py:79-88`) and
  demoted per-user at `tasks.py:585-587`. It carries ZERO authority (`get_effective_role` keys on
  `role`, never `is_primary`) and is a per-user singleton → cannot represent multi-superadmin and
  would silently repoint users' login tenant. WRONG anchor.
- **Correct anchor = a new per-school `SchoolMembership.is_school_owner` BooleanField** (default
  False, db_index, multi-owner-capable → satisfies multi-superadmin; no `role` enum change → avoids
  the `role==SUPERADMIN` middleware lockout at `middleware.py:462-471`). AddField migration (safe) +
  a data migration backfilling existing `is_primary=True` creator memberships → `is_school_owner=True`
  (audit existing 0/multi-primary schools first). Set `is_school_owner=True` on the creator in
  `tasks.py:573-582`.
- **Endpoint** `tenant_identity_transfer_ownership` in `views_tenant_identity.py`, route
  `backend/identity/<int:user_id>/transfer-ownership/`, UI in `tenant_identity_detail.html` action bar
  (`:67-78`). MUST-HAVE guardrails (from the votes): (1) explicit owner check —
  `caller_membership.is_school_owner is True` under lock, NOT the `_can_manage_tenant_identity` role
  gate (it admits IT_ADMIN/LEADERSHIP/VICE_PRINCIPAL → escalation); (2) `select_for_update()` on owner
  rows inside `transaction.atomic()`; (3) school-scoped last-owner guard (never 0 owners per SCHOOL;
  the existing `offboard` view ALSO lacks this — fix together); (4) target resolved via
  `request.school` only (never client school_id), must be `User.is_active` + existing membership
  (there is NO `SchoolMembership.is_active` field); (5) forbid self-transfer; (6) set `target.role`
  via `User.Role.ADMIN` (no string literal — `scan_role_strings`); (7) `membership.save()` NOT
  `.update()` (preserve `rebac_signals.py:29` tuple sync); (8) explicit `log_security_event` audit
  (add an `OWNERSHIP_TRANSFERRED` EventType + choices AlterField migration); (9) decorators
  `@login_required @require_school @require_POST`. Multi-superadmin = `is_school_owner` is a SET;
  "grant" adds an owner, "release" removes self (last-owner-guarded), "transfer" = grant+release.
- **Status: NOT shipped overnight** — security boundary + cross-tenant data migration cannot be
  DB-tested on the stale keepdb nor owner-reviewed; functional baseline (creator=ADMIN+primary,
  multi-admin) is already met so nothing is broken. Build this in a supervised, DB-tested pass.

### Role F — Lifecycle / Offboarding Architect (move closure out — industry-leader model)
**Mission:** relocate offboarding/closure out of the daily tenant workspace into a gated,
owner-only **Account → Close account** zone (Shopify/Stripe placement), keeping self-service data
export as the anti-legacy differentiator; deactivate-not-delete for compliance.
- F1. Remove "Offboarding & closure / Close account workspace" from the daily lifecycle hub render.
- F2. New owner-only "Account & lifecycle" settings surface (bottom of account settings, danger
  zone), behind confirmation + cooling-off; soft-deactivate (`is_active` toggle) NOT hard-delete;
  historical records preserved read-only (FERPA/transcript compliance).
- F3. Keep one-click **portability export** (data sovereignty) as the headline differentiator.
- F4. Relocate sidebar **Recent Activity** to its own activity surface / collapsible panel
  (`portal_sidebar.html:261-279`), out of the always-expanded sidebar.
**Acceptance:** closure no longer in daily workspace; owner-only + gated; deactivate reversible
within grace; export works; sidebar shorter.

### Role G — QA / Validation Engineer (the loop closer)
**Mission:** after every role's change, run the audit→test→validate loop until no gaps.
- Run all zero-tolerance gates (must be 0). Run platform-wide DB suites via `--reuse-db`. Re-audit
  each shipped surface against acceptance. Maintain a living gap register; loop until empty.
- Verify nothing working broke (regression pass on login, dashboards, copilot, finance, people).
**Acceptance:** gap register empty; all gates 0; no regressions; every wave has a browsable + memory.

---

## 4. Phasing & loop protocol

1. **Phase 0 — safe ships (no owner review needed):** footer −50% (A2), sidebar Recent-Activity
   relocation (F4), label-doubling fix (A4), RBAC creator=owner correctness (E), local-first
   correctness (B1/B2/B3). These are owner-directed or correctness — ship with tests + gates.
2. **Phase 1 — full-bleed shell (A1/A3):** platform-wide, ship with before/after browsable.
3. **Phase 2 — per-surface premium (C) + config studio (D):** browsable before/after per surface;
   ship after the owner's tweak-window for anything visual.
4. **Phase 3 — lexicon adoption sweep (B4) + wiring content (KB seed, tenant help intel).**
5. **Phase 4 — lifecycle relocation (F1/F2/F3).**
6. **Loop:** Role G re-audits after each phase; any gap re-enters the queue. Exit only when the gap
   register is empty AND all gates are 0 AND no regressions.

**Exit criteria (no gaps):** every tenant surface full-bleed (no black dead-zone); footer −50%;
≤3-click primary tasks; zero hardcoded locale leakage on a non-Cameroon test tenant; creator =
owner+admin with working transfer + multi-admin; closure moved out + gated; KB seeded; tenant help
page-aware; all zero-tolerance gates 0; platform-wide tests green; browsables + memory per wave.

---

## 5. Competitive alignment (the Linux/Shopify/Salesforce bar)

- **Linux:** open, extensible, no lock-in — self-service data export + deactivate-not-delete is our
  anti-PowerSchool promise (they require legal letterhead + multi-year contract buyout to leave).
- **Shopify:** the merchant (school) configures their own storefront (branding studio, footer,
  dashboard appearance) with zero engineering, and a clean "close account" in the danger zone — not
  buried in a support ticket.
- **Salesforce:** roles/permissions as first-class, multi-admin, transferable ownership, an admin
  backend distinct from the daily frontend — exactly Role D + Role E.
- Every wave: ask "does this beat PowerSchool/Infinite Campus/Ellucian on simplicity, self-service,
  and local-first fit?" If not, it's not done.

---

## 6. Live verification target

Owner inspects on `https://new-school.runmycampus.com/`. **Render auto-deploy may be off** — the
owner must DEPLOY `origin/main` to see shipped work, and set `RUNMYCAMPUS_AI_ENABLED=true` to turn
copilot inference on (it already renders + chats in rules-fallback). State this in every handoff.
