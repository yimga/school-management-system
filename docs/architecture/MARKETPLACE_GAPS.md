# Marketplace — What’s Implemented vs What’s Missing (Phase 11)

This doc aligns the codebase with the RunMyCampus plan Phase 11 (Marketplace and App Ecosystem) and lists gaps.

---

## Implemented

| Item | Status |
|------|--------|
| **Models** | PublisherOrganization, MarketplaceApp, MarketplaceListing, MarketplaceReview, AppScope, AppInstallation, ScopeGrant, AppBillingLedger, AppAuditLog, AppVersionCompat, **CapabilityRegistry** |
| **App kinds** | First-party, third-party, **premium**, **tenant_private**, **connector** (MarketplaceApp.AppKind) |
| **Capability registry** | **CapabilityRegistry** model; **seed_capability_registry** management command (dashboard_widget, workflow_action, workflow_condition, integration_adapter) |
| **Listing lifecycle** | Draft → Pending review → Approved; kill_switch_active; security/certification review status |
| **Scopes** | AppScope (requested, **sensitive** flag), ScopeGrant (granted per installation, **status** pending/granted, **elevated_approved_at/by**) |
| **Installation** | AppInstallation (school, app, status ACTIVE/SUSPENDED/UNINSTALLED; **install_phase** sandbox/active; **last_health_at**, **health_status**; **uninstalled_at**); install_app(), uninstall_app(), activate_sandbox_installation(), record_installation_health(), **refresh_installation()** |
| **Compatibility** | MarketplaceListing.compatibility; check_app_compatibility(school, app); install_app() checks compatibility unless skip_compatibility=True |
| **Billing** | AppBillingLedger (install_fee, subscription, proration, usage) |
| **Runtime** | runtime.marketplace from AppInstallation (install_phase=ACTIVE); granted_scopes only where status=GRANTED; widget_registry, workflow_actions, workflow_conditions, integration_adapters from manifest |
| **Control plane** | Governance console, review queue, app catalog; compatibility matrix, sandbox inspector, installation health (**Refresh** button), **incident dashboard** (recent marketplace audit events); activate sandbox, **refresh installation** |
| **Tenant** | Installed apps (list, sandbox, uninstall, activate); App catalog (browse/install); Scope consent (pending, approve); **tenant role checks** (ADMIN, IT_ADMIN, LEADERSHIP, staff) for all marketplace actions |
| **Health** | **marketplace_health_check** management command; **marketplace.marketplace_health_check** Celery task (scheduled every 6h in CELERY_BEAT_SCHEDULE) |
| **Update flow** | **marketplace_report_updates** management command (report installations, optional version spread); **refresh_installation()** + super **Refresh** button to re-apply manifest (widget_config) |
| **Sandbox** | Tenant URL app-sandbox/ for embedding installed app widgets (iframe + CSP) |
| **Version compat** | AppVersionCompat (platform min, app version min/max) |

---

## Remaining (future / as needed)

| Area | Note |
|------|------|
| **integration_adapters** | Runtime already populates from manifest; extend if more adapter metadata is needed. |
| **Versioning policy** | Full “update app version” flow (e.g. prompt tenant to upgrade) can be added when versioning policy is defined. |

Phase 11 marketplace and all previously optional items are implemented.
