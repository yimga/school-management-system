# Bounded Consoles Inventory (IV.27)

**Purpose:** Single list of bounded-console surfaces that replace or wrap giant admin/settings pages. Authority: [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) IV.27, [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §6.1, §5.9.

**Definition:** A bounded console is a single-purpose UI (decision console or operational workbench) for one settings/operations domain, with clear entry from Control Studio or shell nav — not a sprawling admin page.

---

## Current bounded consoles

| Console | Entry point | View / URL | Notes |
|--------|-------------|------------|--------|
| **Configuration Control Center** | Control Studio rail **Config center** | studio_os:system_config_console (embed) → studio_os:system_config_console; shell also siteconfig:console_domains_hub | Domains link to Experience, Automation, Output, feature control; control_plane sidebar **Config center**. |
| **Feature control** | Control Studio rail "Capabilities" | siteconfig:feature_control_panel (embed) | Feature toggles; in-shell or embed; audit link in rail. |
| **Experience Studio** | Studio OS Experience mode | studio_os:experience | Theme, branding, experience packs; hub + rail. |
| **Automation Studio** | Studio OS Automation mode | studio_os:automation | Workflow hub, flow gallery, approval hub, outcomes console; hub + rail. |
| **Output Studio** | Studio OS Output mode | studio_os:output | Report library, document library, report card builder; hub + rail. |
| **Launch Studio** | Studio OS Launch mode | studio_os:launch | Guided onboarding, create school, blueprint gallery, launch checklist; hub + rail. |
| **Control Studio** | Studio OS Control mode | studio_os:control | Capabilities, runtime inspector, blueprints & policy, metadata governance, API Center, etc.; hub + rail. |
| **Outcomes console** | Automation Studio rail "Outcomes" | automation:outcomes_console | MigrationRun, AutomationExecutionLog; staff-only. |
| **API Center** | Control Studio rail "Integrations" | apicenter:dashboard | Integrations, rate limits, audit; integration governance. |
| **Metadata governance** | Control Studio rail "Metadata governance" | metadata:metadata_governance | Catalog, lineage, governance UI. |
| **Blueprint gallery / policy** | Control Studio rail "Blueprints & policy packs" | siteconfig:get_blueprints (embed) | Blueprint and policy pack management. |
| **Runtime inspector** | Control Studio rail "Runtime inspector" | super:runtime_inspector | Runtime resolution, flags, entitlements, blueprint. |

---

## Decomposition status

- **Done:** Configuration Control Center (console_domains_hub), feature control panel, all five Studio OS mode hubs, outcomes console, API Center, metadata governance, blueprint/policy, runtime inspector. Control Studio rail links to each.
- **Incremental:** Further replacement of Django admin or legacy siteconfig pages with bounded consoles per product; see siteconfig_remediation_ledger and LEGACY_PATH_INVENTORY.

---

## Verification

- **Control Studio:** Open Studio OS → Control; every rail entry resolves to a bounded console or embed (no 404).
- **Configuration Control Center:** `/siteconfig/console/` or Studio OS Control → rail **Config center** → domains hub with links to Studio modes and feature control.

---

*SOT ref: §6.1 III.3, §5.9 IV.27; NA_REGISTER §6.1 DONE.*
