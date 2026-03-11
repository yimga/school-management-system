# Remaining PLAN_AUDIT gaps (prioritised)

**Doc status: Closed.** All items below are either **Done** or **Closed (Phase 10 / deferred)**. Optional work (tenant "Get blueprints" entry, pack versioning UX, 26.5 remaining lists) is in **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

Short checklist for items from the execution map and plan audit. Use for prioritisation and sprint planning. **Current status:** [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) — all items are either completed or explicitly deferred. **Every deferred refinement from the consolidated checklist (6.3, 11.2, 29.10) is listed here so nothing is left behind.** See RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md “Deferred and optional items register”.

---

## 6.3 / 29.10 Tenant app billing (and commercial app billing wiring)

- **Goal:** Wire app installs to billing (proration, usage-based charge for installed apps per school).
- **Current:** **Implemented.** On install, `record_app_install_for_billing` creates `PlatformLedgerEntry` (source=`marketplace_app_install`). Invoice line generation: `billing.services.invoice_lines_from_app_ledger(school, period_start=..., period_end=...)`. See SCOPED_WORK_VERIFICATION.md § Completed.
- **Next:** Optional: proration and usage-based metering per app when productized.

## 11.2 Blueprint marketplace — tenant-facing “Get blueprints” and pack versioning

- **Goal:** Tenant-facing entry for discovering and requesting blueprint packs; optional pack version/update UI for tenants.
- **Current:** BlueprintPack, apply_blueprint_pack, preview, manager UI (super:blueprint_marketplace) implemented; pack versioning (applied_pack, applied_pack_version, update_bundle_for_schools) in place.
- **Next:** Add tenant backend entry (e.g. “Get blueprints” or “Blueprint gallery”) and, if needed, tenant-facing pack version/compatibility UI. See phase6_marketplace.md.

## 1.8 Secure app sandbox

- **Goal:** iframe/CSP and safe execution for installed apps (tenant-facing and developer sandbox).
- **Current:** **Implemented.** sandbox_embed: iframe with sandbox attribute and CSP; origin validation (Referer/Origin vs ALLOWED_HOSTS; 403 if disallowed). Checklist: `docs/architecture/sandbox_hardening_checklist_1_8.md`. See SCOPED_WORK_VERIFICATION.md § Completed.
- **Next:** Optional: additional security pass on embed points if needed.

## 26.5 UX rules

- **Goal:** Consistently add search/filters/export to key lists; form autosave/draft where critical.
- **Current:** Audit doc: ux_rules_audit_26_5.md. Done: document library CSV; applicants list (search/filter/export); application form Save draft. Students, invoices, teachers, guardians, evals already had reference implementation.
- **Done:** Classes/sections list (backend_classroom_list); student onboarding step-level draft (FormDraft student_onboarding). See SCOPED_WORK_VERIFICATION.md.

## Control plane maturity

- **Goal:** Incrementally improve superadmin toward “AWS console for schools” (health, rollout, support).
- **Current:** Dashboard, command center, billing, marketplace, support, pulse, tenant-health, migration cloud entry, AI model hub. **Health dashboard:** `super_control_health_dashboard` at `/super/health/` (super_urls name=`control_health`); template `schools/super_control_health.html`; links to Tenant health, Incident console, SLO dashboard (API), Runbooks (when CONTROL_PLANE_RUNBOOKS_URL set). Linked from super dashboard.
- **Next:** Refine SLO dashboard data; optional support queue integration. Runbooks/canary doc done (see below).

### Control plane runbooks and canary

- **Runbooks URL:** **Done.** Set env `CONTROL_PLANE_RUNBOOKS_URL`; documented in `.env.example`; health dashboard links when set. See SCOPED_WORK_VERIFICATION.md.
- **Canary/rollout:** **Done (doc).** [preview_release_canary.md](preview_release_canary.md) updated with ops note for runbooks + canary.
- **Support queue:** **Done.** Support dashboard and queue show SLA breach; GlobalSupportTicket.first_response_at; support_sla integrated.

---

**Full list of scoped work not yet done (with next steps and priority):** [SCOPED_WORK_NOT_DONE.md](SCOPED_WORK_NOT_DONE.md).

**References:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md, PLAN_AUDIT_DONE_VS_PARTIAL_VS_NOT_DONE.md, phase8_migration_cloud_and_marketplaces.md.
