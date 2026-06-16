# Tenant Lived-Experience Gap Backlog (2026-06-15)

Evidence-backed gap inventory from a **skeptical, render-level** audit of a *freshly provisioned*
school across admin / teacher / parent / student / finance surfaces. This is the gap class a
"does the code exist?" audit structurally misses. Deliverable = backlog (no code yet). Each item
tagged **[VERIFIED]** (confirmed by code path/grep this session) or **[SUSPECTED]** (needs one more
confirmation before acting).

## The unifying root cause

Provisioning (`apps/schools/tasks.py` Phase A/B) seeds the **academic skeleton** (academic year,
terms, subjects, classrooms, admin user, payment *routing* policy, tenant schema, and — as of
2026-06-15 — dashboard pack assignments) but leaves the **money layer, the configuration/pack layer,
and the per-role experience layer unseeded**. In several cases a seeder *exists* but is **never wired
into provisioning** (e.g. `seed_finance_defaults.py`, `seed_workflow_dashboard_packs.py`). Net
effect: a new school is usable for almost nothing until heavy manual setup, and several surfaces are
blank or can crash. This is the **same "built-but-not-wired" pattern** as the dashboard packs.

---

## P0 — Blocking / can crash (fix first)

1. **[✅ IMPLEMENTED 2026-06-15 — was the confirmed P0 crash] Per-tenant `ComplianceProfile` now seeded in Phase B.**
   New `apps/finance/provisioning_seed.py::ensure_tenant_compliance_profile(school)` (idempotent,
   region-aware, tenant-schema-scoped, does NOT touch shared RuntimeDefaults) wired into
   `apps/schools/tasks.py` Phase B `seed_data` block after the dashboard-pack assignment (non-fatal).
   6 tests green (`apps/finance/tests/test_provisioning_compliance_seed.py`); `check` 0, no migration.
   _Original finding (kept for context):_
   `apps.finance` is **TENANT_APPS** (schema-per-tenant) → a new tenant schema has zero
   `ComplianceProfile`. `Invoice.profile` = `ForeignKey(PROTECT)` non-null (`finance/models.py:456`).
   Fee/invoice creation resolves `site.compliance_profile → ComplianceProfile.filter(is_active=True).first()`
   inside the empty tenant schema → `None` → **IntegrityError**. `seed_finance_defaults` seeds at the
   *platform* level only — it does NOT populate tenant schemas. **Fix:** write/port a **per-tenant**
   ComplianceProfile seeder into Phase B (region-aware, idempotent, in-tenant-schema) + set the
   tenant's `compliance_profile` RuntimeDefault. (NOT just "wire the existing command.")
2. **[VERIFIED — DOWNGRADED P0→MEDIUM after Phase 0] Wrong sidebar nav url_names → dead/dropped item, NOT a crash.**
   `apps/platform_runtime/sidebar_registry.py:96,105,114` references `portal:grades`,
   `portal:attendance`, `portal:finance` — none of which exist (real names: `student_portal_grades`,
   `teacher_attendance`, `parent_finance`). **Phase 0 found the nav reverse IS guarded** —
   `portal_sidebar_items.py::_safe_reverse` + `control_plane_nav.py::_safe_reverse` swallow
   `NoReverseMatch`; shells don't render registry items via raw `{% url %}`. So this is a dropped/dead
   nav item, not a 500. **Fix:** correct the url_names (trivial). Severity MEDIUM, not blocking.
3. **[VERIFIED] No `FeePlan`/`FeeItem` seeded → invoicing is dead on day one.**
   `auto_generate_fee_invoices_task` returns `no_plans` and exits when a school has zero fee plans
   (`tasks.py`). A new school cannot bill anyone until fees are manually built in Studio, with no
   inline "create your first fee plan" CTA on the empty invoice list. **Fix:** seed a default fee
   plan/template at provisioning (sector/region cascade) + add an empty-state CTA.

## P1 — First-run experience is blank for every role (highest "tenants need work" signal)

4. **[VERIFIED] Teacher portal goes blank with no active year/term.**
   `apps/evals/views.py` teacher_dashboard renders empty `display_widgets`/`teacher_alerts` + one
   warning card when `get_active_year_and_term()` is empty. A fresh teacher with no classes sees a
   dormant portal. **Fix:** guaranteed active year/term at provisioning + a real teacher empty-state
   with next steps.
5. **[VERIFIED] Parent portal entirely hidden until a child is linked.**
   `templates/parent/dashboard.html` hides all KPIs/child cards/finance behind the "link a child" CTA
   when `not links`; finance shows "Finance access not granted" with no pathway. **Fix:** a richer
   pre-link welcome state + clearer link→unlock guidance.
6. **[VERIFIED] Student portal is near-empty by default — cockpit sections self-gate OFF.**
   `templates/student/learning_home.html` cockpit sections each gate on `cockpit.<section>.enabled`
   (off unless an operator enables them); the decision-engine surface is a hardcoded
   "On track / Setup needed" stub. A new student sees hero + empty strip. **Fix:** sensible default-on
   cockpit set per provisioning + wire the decision surface to real classwork.
7. **[VERIFIED] Admin dashboard zero-states read as "all good," not "set me up."**
   Snapshot cards show all-zeros, Operations Watch says "System stable / queues clear," Recent
   Activity shows a placeholder "Role home is ready," and the **Setup** intent is not the default for
   a zero-data school. **Fix:** zero-data-aware empty states + default new schools into Setup intent +
   actionable CTAs ("add your first student/class").

## P2 — Dormant "pack/template/assignment" features (the dashboard-packs pattern, repeated)

Each exists as a model with live readers, but is **never seeded per tenant** and/or **never surfaced**:
8. **[VERIFIED] `role_visual_presets` switcher has no UI.** Read path works
   (`context_processors` emits the preset; 50+ presets in `portal_visual_presets_registry.py`), but
   no template surfaces a picker. Users can't change their visual preset. **[not-surfaced]**
9. **[SUSPECTED] `DocumentPack` never seeded.** Live reader in `portal/views_documents.py`; zero rows
   for new tenants → empty document library. **[not-seeded]**
10. **[SUSPECTED] `ExperiencePack` never seeded + no operator assign cockpit** (admin-only CRUD).
    **[not-seeded / not-surfaced]**
11. **[SUSPECTED] `WorkflowPackAssignment` never seeded.** Runtime resolver reads it; new schools have
    zero default workflow packs per module. **[not-seeded]**
12. **[SUSPECTED] `TemplateAssignment` (brand_experience) never seeded.** New tenant starts with no
    active document/design templates. **[not-seeded]**
13. **[SUSPECTED] `PolicyRule` defaults never seeded.** Compliance/governance engine is live but has no
    default enforcement rules per tenant. **[not-seeded]**
14. **[SUSPECTED] `InstalledPackage.package_type` — only 2 of 7 types read** (blueprint, workflow);
    theme/document_pack/experience_pack/policy/dashboard are data-layer-only via this model. **[not-read]**
15. **[SUSPECTED] Marketplace `ScopeGrant` auto-grants on install** (no tenant-admin approve/revoke
    UI) — a consent/compliance gap. **[not-surfaced]**

## P2 — Other provisioning-seeding gaps (money + config)

16. **[VERIFIED] No guardian/`StudentGuardian` records** → finance reminders iterate an empty list;
    finance visibility = 0 for parents until linked.
17. **[VERIFIED] No `BankAccount` rows** → payment reminders render blank bank/MoMo/Orange details.
18. **[SUSPECTED] No role-based permission groups** (Teachers/Finance/Staff) seeded → "Manage Groups"
    UI is blank.
19. **[SUSPECTED] Report-card templates / `GradingScale` objects not seeded** — profile stores the
    *family name* string only, so the assessment/report editor is blank on first visit.
20. **[SUSPECTED] No onboarding communication templates** (email/SMS/WhatsApp) seeded.

## Reliability gap (separate from features)

21. **[VERIFIED] No trustworthy green test baseline.** Full tenant suite ran 5,661 tests in ~2.1h →
    **413 failures / 32 errors**, but the run was **contaminated** (working tree mutated mid-run:
    3 bug-fix commits + the dashboard-packs feature + migrations landed during execution). Need a
    **frozen-tree re-run** (shard finance separately — a `finance_webhooklog` unique-constraint
    test-isolation collision aborted an earlier run) to separate real regressions from noise. Until
    then, "it works" is unprovable.

## Money correctness — GOOD (no gap)

- **[VERIFIED] Decimal discipline holds.** Invoice/fee/payment amounts are `DecimalField`; the
  `scan_money_float` gate is in place; the few `float()` sites are marked display/gateway-format, not
  ledger. No new violations in provisioning/finance. Payment-provider readiness is *honestly* blank
  (no fake PSP claims) until credentials are added.

---

## Recommended sequencing (when you decide to fix)

1. **One provisioning "experience seed" pass** that wires the existing-but-unwired seeders into
   Phase B (ComplianceProfile + fee plan + workflow packs + document/experience packs + permission
   groups), all idempotent — kills items 1, 3, 9–13, 16–20 with one coherent change set. This is the
   single highest-leverage fix and directly attacks the root cause.
2. **Nav link fix** (item 2) — small, high-visibility.
3. **Per-role empty-state pass** (items 4–7) — the "feels blank" complaint.
4. **Surface the dormant switchers** (item 8) — small.
5. **Frozen-tree test re-run** (item 21) — establish a real baseline before/after.

## Confidence note

Items marked [SUSPECTED] came from skeptical sub-agents and were not individually re-confirmed this
session; treat them as "very likely, verify the exact failure mode before coding." The [VERIFIED]
items were confirmed by direct grep/code-path read. Two earlier agent claims were corrected this
session (a resolver over-claimed "fully live"; an audit missed the `siteconfig/models_dashboard.py`
pack models entirely) — so re-confirm before trusting any single agent claim.
