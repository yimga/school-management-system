# Provisioning "Experience Seed" Plan (handoff for a fresh session)

**Authored:** 2026-06-15 · **Status:** PLAN — not executed · **Companion docs:**
[`TENANT_LIVED_EXPERIENCE_GAP_BACKLOG.md`](TENANT_LIVED_EXPERIENCE_GAP_BACKLOG.md) (the 21-item
backlog this closes ~10 of) · [`DASHBOARD_PACKS_REVIVAL_PLAN.md`](DASHBOARD_PACKS_REVIVAL_PLAN.md)
(the already-executed sibling; this follows the same wiring pattern).

## Goal

One idempotent **"experience seed" pass** in provisioning **Phase B** so a freshly-provisioned school
arrives with a working money + configuration + experience layer instead of blank/crashing surfaces.
Attacks the backlog's **root cause** ("seeders exist but are never wired into provisioning") in a
single coherent change set rather than patching symptoms.

> ⚠️ Run **Phase 0** before coding. Two resolution paths must be confirmed (ComplianceProfile via
> RuntimeDefaults vs per-school; nav reverse guard) or the fix targets the wrong layer.

---

## Where it goes (verified anchor)

- Provisioning entry: `apps/schools/tasks.py::_do_provision_tracked` — step tuple
  `("admin_user", "profile", "tenant_schema", "seed_data", "activate")`.
- The **`seed_data` step** (pulse at ~line 1084) already seeds academic structure (~1221–1374) and
  `assign_default_dashboard_packs(school, apply=True)` (~1381). **Add each new seed call here**, in
  the same idempotent + non-fatal (`try/except`, log, never abort provisioning) style as the
  dashboard-pack call. Re-entrancy matters: this step re-runs on stuck-tenant recovery / requeue.

## Seed matrix — what to wire vs what to write

| Backlog item | Existing seeder? | Action |
|---|---|---|
| ComplianceProfile (P0 #1) | ✅ `finance/management/commands/seed_finance_defaults.py` (seeds **platform** Generic Global profile + RuntimeDefaults; `--include-cameroon` optional) | **Phase 0 first:** confirm whether `Invoice.profile` resolves the platform default via RuntimeDefaults or needs a per-school row. If platform default suffices → ensure it's seeded once per env (predeploy/migration). If per-school → factor the `get_or_create` into a callable invoked in Phase B. |
| FeePlan / FeeItem (P0 #3) | ❌ none | **Write** a small default fee-plan seeder (region/sector cascade; e.g. one tuition plan per seeded classroom) + idempotent. Add empty-state CTA on the invoice list separately. |
| Permission groups (P2 #18) | ❌ none found | **Write** `ensure_default_role_groups(school)` (Teachers / Finance / Class Tutors / Comms) idempotent. |
| Guardian / BankAccount defaults (#16, #17) | ❌ none | **Write** minimal seed OR (better) make the dependent surfaces (reminders) degrade gracefully + show setup CTAs. Decide per-item: seed vs empty-state. |
| WorkflowPackAssignment (P2 #11) | partial — `seed_workflow_dashboard_packs.py`, `seed_process_definitions.py` | Wire a default per-module workflow-pack assignment into Phase B (idempotent on (school, module)). |
| ExperiencePack / DocumentPack (P2 #9,#10) | `seed_ultra_high_end_experience_packs.py` (opt-in flag) | Wire a default ExperiencePack assignment; for DocumentPack, seed a starter set or confirm the library degrades cleanly when empty. |
| PolicyRule defaults (P2 #13) | `seed_blueprint_policy_packs.py`, `seed_compliance_baseline.py` | Wire a sensible default policy/compliance baseline per tenant. |
| Report-card / GradingScale objects (#19) | profile stores family NAME string only | Decide: materialize default GradingScale/ReportCard rows from the profile family, or make the editor resolve from the string. |

## Phase 0 — FINDINGS (verified read-only, 2026-06-15) ✅

**Check 1 — ComplianceProfile: CONFIRMED CRITICAL crash for a new tenant. Mechanism nailed.**
- `apps.finance` is in **TENANT_APPS** (`config/settings.py:3596`) → schema-per-tenant. A freshly
  provisioned tenant schema contains **zero** `ComplianceProfile` rows.
- `Invoice.profile = ForeignKey(ComplianceProfile, on_delete=PROTECT)` and is **non-null**
  (`apps/finance/models.py:456`).
- Resolution chain when creating fees/invoices (`apps/finance/services.py:547-548, 915, 1394-1397`):
  `getattr(site, "compliance_profile", None)` → fallback `ComplianceProfile.objects.filter(is_active=True).first()`.
  Both run **inside the tenant schema** → `None` for a new tenant → `Invoice(profile=None)` →
  **IntegrityError** on the PROTECT/non-null FK.
- `compliance_profile_id` IS a RuntimeDefaults first-class field
  (`apps/platform_runtime/runtime_defaults_first_class.py:111`) but is **not set at provisioning**.
- **Consequence for the fix:** `seed_finance_defaults` seeds at the *platform* level — it does NOT
  populate new tenant schemas. So item #1 is **"write/port a per-tenant ComplianceProfile seeder into
  Phase B"** (region-aware, idempotent, executed inside the tenant schema) **+ set the tenant's
  `compliance_profile` RuntimeDefault** — NOT merely "wire the existing command." This is the single
  most important Phase-0 correction.

**Check 2 — Dead nav (backlog P0 #2): DOWNGRADED from CRITICAL to MEDIUM. Not a crash.**
- The nav layer guards reverse: `apps/siteconfig/portal_sidebar_items.py::_safe_reverse()` and
  `apps/schools/control_plane_nav.py::_safe_reverse()` wrap `reverse()` in
  `try/except (NoReverseMatch, …)` and return a default. Shell templates do NOT render `for_shell()`
  registry items via raw `{% url item.url_name %}`.
- The names `portal:grades` / `portal:attendance` / `portal:finance` in
  `apps/platform_runtime/sidebar_registry.py:96,105,114` ARE wrong (real names:
  `student_portal_grades` / `teacher_attendance` / `parent_finance`), but a wrong name yields a
  **dropped/dead nav item, not a 500**. Fix = correct the names (trivial), severity MEDIUM not P0.

**Check 3 — idempotency keys:** unchanged guidance below; confirm natural keys per seeder before coding.

---

## Phase 0 — Verify (no code) — original checklist (now answered above)
1. **ComplianceProfile resolution:** read `Invoice.profile` definition (on_delete + null?) and how a new
   invoice picks its profile. Does it fall back to the RuntimeDefaults platform profile, or require a
   per-school FK target? This decides whether item #1 is a "seed platform default once" or "seed
   per-school" fix. (Earlier audit: `seed_finance_defaults` is platform-scoped + RuntimeDefaults.)
2. **Nav reverse guard (P0 #2 — independent of seeding):** confirm `sidebar_registry.py` items
   `portal:grades` / `portal:attendance` / `portal:finance` and how the nav template reverses them
   (guarded vs raw `{% url %}`). Fix = correct the names (`student_portal_grades` /
   `teacher_attendance` / `parent_finance`) and/or add a safe-reverse that drops unresolved items.
3. **Idempotency surface:** confirm each seeder's natural key so re-running `seed_data` (recovery
   path) creates no duplicates.

## Phase 1 — Implement
- Add `apps/schools/provisioning_experience_seed.py` (one module) exposing
  `seed_tenant_experience(school, *, apply=True) -> dict` that calls each seeder/writer above,
  each wrapped so one failure logs + continues (mirror the dashboard-pack call's non-fatal pattern).
- Call it from the `seed_data` step in `_do_provision_tracked` right after the dashboard-pack call.
- Backfill command `manage.py seed_tenant_experience [--school <slug>|--all] [--apply]` (per-row
  atomic, idempotent) for existing tenants — mirror `assign_default_dashboard_packs` CLI.
- No-hardcoding: defaults chosen via the cascade (sector / region / education system), not literals.

## Phase 2 — Empty-state safety net (for the items we choose NOT to seed)
- For anything left intentionally empty (guardians, banks, some packs), ensure the consuming surface
  renders an actionable empty-state with a CTA, never a blank panel or a crash. (Backlog P1 #4–7 are
  the per-role empty-state pass; can be a separate change but should land close to this.)

## Tests
- Provisioning seed idempotency: run `seed_data` twice → zero duplicate ComplianceProfile / fee plan /
  groups / assignments.
- A freshly-provisioned school can: reach the invoice generation path without a missing-profile crash;
  render admin/teacher/parent/student dashboards without a blank/dead surface; nav links all reverse.
- Non-fatal contract: force one sub-seeder to raise → provisioning still completes + activates.
- Re-run the dashboard-pack tests (`apps/siteconfig/tests/test_dashboard_packs_revival.py`) to ensure
  the additional Phase-B calls don't perturb them.

## Frozen-tree test protocol (the reliability item, #21)
The 2026-06-15 full run (5,661 tests → 413 fail / 32 err) was **contaminated** by a mid-run tree
mutation; it is NOT a valid baseline. Before *and* after this work:
1. Ensure a clean, **static** working tree (no parallel commits mid-run) — coordinate with the peer or
   work in an isolated worktree.
2. Shard **finance separately** — a `finance_webhooklog` UNIQUE(provider, idempotency_bucket)
   test-isolation collision aborted an earlier run; fix/quarantine that test or run finance with
   `--parallel 1`.
3. Use `config.settings_test` (in-memory; ~31-min cold build amortized by running apps together in one
   process). Capture the real `Ran N tests … FAILED/OK` summary as the baseline, then compare post-fix.

## Gotchas (from this session)
- **Peer churn:** the repo is being committed to in parallel — do Phase 1's new module + any migration
  in an isolated worktree or immediately after a pull; keep migration leaves isolated. (The
  dashboard-packs work already hit a migration-leaf-numbering trap — always `ls migrations/ | sort`
  fully, don't trust a filtered listing.)
- **Moderate sub-agent claims:** P2 items #9–13, #18 are [SUSPECTED] in the backlog; re-confirm each
  is genuinely unseeded (not seeded by some other path) before writing a seeder for it.
- `seed_finance_defaults` is **platform-scoped + RuntimeDefaults**, not per-school — don't blindly
  call it per-tenant without resolving Phase 0 #1.
- `schools.School.default_dashboard_slug` stays dead (superseded by the pack `*Assignment` models).
