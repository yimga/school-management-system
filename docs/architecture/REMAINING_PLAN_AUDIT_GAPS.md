# Remaining PLAN_AUDIT gaps (prioritised)

Short checklist for items from the execution map and plan audit that are not yet fully closed. Use for prioritisation and sprint planning. **Every deferred refinement from the consolidated checklist (6.3, 11.2, 29.10) is listed here so nothing is left behind.** See RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md “Deferred and optional items register”.

---

## 6.3 / 29.10 Tenant app billing (and commercial app billing wiring)

- **Goal:** Wire app installs to billing (proration, usage-based charge for installed apps per school).
- **Current:** **Implemented.** On install, `apps.marketplace.services.install_app` calls `record_app_install_for_billing(school, app, installation)` in `apps.billing.services`; that creates a `PlatformLedgerEntry` (source=`marketplace_app_install`) so each install is recorded for invoicing. Optional `amount` can be set when add-on pricing is configured. Revenue share / publisher payout unchanged.
- **Next:** Optional: proration and invoice line generation from ledger entries; usage-based metering per app when productized.

## 11.2 Blueprint marketplace — tenant-facing “Get blueprints” and pack versioning

- **Goal:** Tenant-facing entry for discovering and requesting blueprint packs; optional pack version/update UI for tenants.
- **Current:** BlueprintPack, apply_blueprint_pack, preview, manager UI (super:blueprint_marketplace) implemented; pack versioning (applied_pack, applied_pack_version, update_bundle_for_schools) in place.
- **Next:** Add tenant backend entry (e.g. “Get blueprints” or “Blueprint gallery”) and, if needed, tenant-facing pack version/compatibility UI. See phase6_marketplace.md.

## 1.8 Secure app sandbox

- **Goal:** iframe/CSP and safe execution for installed apps (tenant-facing and developer sandbox).
- **Current:** Tenant-facing `marketplace.views.sandbox_embed` at `/siteconfig/app-sandbox/?app_slug=...&widget_id=...`; iframe with sandbox attribute and CSP; developer_sandbox (public) present. **Checklist:** `docs/architecture/sandbox_hardening_checklist_1_8.md` (CSP, postMessage contract, embed points, sandbox attribute).
- **Next:** Implement CSP and origin checks per checklist where not yet applied; run security pass on embed points.

## 26.5 UX rules

- **Goal:** Consistently add search/filters/export to key lists; form autosave/draft where critical.
- **Current:** **Audit doc:** `docs/architecture/ux_rules_audit_26_5.md` — list standards (search/filter/export) and form standards (autosave/draft) with status table. Student list export and some list views exist.
- **Next:** Prioritise search/filter/export on remaining lists and draft/autosave on long forms per audit table.

## Control plane maturity

- **Goal:** Incrementally improve superadmin toward “AWS console for schools” (health, rollout, support).
- **Current:** Dashboard, command center, billing, marketplace, support, pulse, tenant-health, migration cloud entry, AI model hub. **Health dashboard:** `super_control_health_dashboard` at `/super/health/` (super_urls name=`control_health`); template `schools/super_control_health.html`; links to Tenant health, Incident console, SLO dashboard (API), Runbooks (when CONTROL_PLANE_RUNBOOKS_URL set). Linked from super dashboard.
- **Next:** Refine SLO/incident data and runbooks URL; rollout/canary per preview_release_canary; support queue integration.

---

**References:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md, PLAN_AUDIT_DONE_VS_PARTIAL_VS_NOT_DONE.md, phase8_migration_cloud_and_marketplaces.md.
