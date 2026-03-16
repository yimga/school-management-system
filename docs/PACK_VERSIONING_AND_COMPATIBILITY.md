# Pack versioning and compatibility discipline

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.2. Packs are governed by semantic versioning, dependency graph, compatibility matrix, safe upgrade/downgrade, tenant impact preview, rollback behavior, deprecated-pack handling, and ownership/provenance.

**Authority:** This doc defines the discipline; implementation lives in `apps/packages`, marketplace, and Studio OS/control plane. Completion gate: versioning and compatibility doc; upgrade/downgrade/rollback rules in place; tenant impact preview available for pack changes; deprecated-pack handling defined.

**Related:** [package_engine_ledger.md](package_engine_ledger.md), [architecture/PACKAGE_FORMAT.md](architecture/PACKAGE_FORMAT.md), [MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md).

---

## 1. Semantic versioning (semver)

- **Format:** `MAJOR.MINOR.PATCH` (e.g. `2.1.0`).
- **MAJOR:** Breaking change (e.g. remove or rename required field, change contract).
- **MINOR:** New backward-compatible capability (e.g. new optional section, new workflow).
- **PATCH:** Backward-compatible fix (e.g. bug fix, copy fix, non-breaking validation).
- **Rule:** New pack versions must have a version string; catalog and InstalledPackage must store and display it. Upgrade from 1.x to 2.x may require migration or compatibility check.

---

## 2. Dependency graph

- **Goal:** Before apply, validate that all required dependencies (other packs or platform version) are present and at a compatible version.
- **Current:** Package engine validates dependencies before apply ([package_engine_ledger.md](package_engine_ledger.md) §1). Extend to all pack types (blueprint, workflow, dashboard, policy, report, theme) where applicable.
- **Rule:** Dependency graph is maintained per pack (declared in package manifest or PackageVersion metadata). Apply fails with clear message if dependency missing or version incompatible.

---

## 3. Compatibility matrix

- **Dimensions:** Platform version (min/max), plan/entitlement, region/locale, tenant schema version.
- **Goal:** Only offer or allow install of a pack when compatibility matrix allows it.
- **Current:** Plan/blueprint compatibility exists; extend to min_platform_version, allowed_regions, and plan constraints in [architecture/PACKAGE_FORMAT.md](architecture/PACKAGE_FORMAT.md) `compatibility` object.
- **Rule:** Studio OS / marketplace / control plane must not offer “Install” when matrix says not compatible; show “Not compatible” with reason (e.g. “Upgrade platform to X” or “This plan does not include this pack”).

---

## 4. Safe upgrade path

- **Rule:** Upgrade from version A to B is allowed only if B is backward-compatible (same MAJOR, or migration path documented) or if explicit “breaking upgrade” is acknowledged by operator with impact preview.
- **Action:** Before applying upgrade: run impact preview (see §6); show diff and blast radius; require confirm. For MAJOR upgrade, document migration steps and runbook.

---

## 5. Downgrade rules

- **Rule:** Downgrade (B → A where A < B) is allowed only if data and config written by B are compatible with A, or if rollback path is defined (e.g. rollback to previous InstalledPackage snapshot).
- **Current:** Rollback in package engine deactivates current InstalledPackage and sets reconciliation_status=rolled_back; PackageChangeLog records change ([package_engine_ledger.md](package_engine_ledger.md)).
- **Rule:** Document which pack types support downgrade and which require “replace with older version” re-apply; avoid data loss.

---

## 6. Tenant impact preview

- **Goal:** Before apply/upgrade/downgrade, show tenant what will change: which entities, settings, workflows, dashboards, policies are added/removed/changed; which roles are affected.
- **Current:** Impact preview and dependency warnings exist (validate_package, _compatibility_report, preview_diff, _build_impact_summary). Expose in Studio OS or control plane so operator sees impact before confirming.
- **Rule:** Every apply/upgrade/downgrade flow must offer impact preview where technically feasible; at minimum, show dependency and compatibility result.

---

## 7. Rollback behavior

- **Goal:** After apply, operator can rollback to previous state; rollback is documented and audited.
- **Current:** Package engine rollback() implemented; InstalledPackage reconciliation_status; PackageChangeLog. See [package_engine_ledger.md](package_engine_ledger.md) §2.
- **Rule:** Rollback must be explicit (no silent rollback); audit log must record who rolled back and when; blast radius in result.

---

## 8. Deprecated-pack handling

- **Definition:** A pack version or pack line is deprecated when it is no longer recommended for new installs or will stop receiving fixes.
- **Policy:** (1) Mark deprecated in catalog (deprecated_at, deprecation_message). (2) Marketplace/Studio OS show “Deprecated” and recommend replacement if any. (3) Existing installs continue to work until end-of-support date; (4) no new installs of deprecated version unless override (e.g. super). (5) Document end-of-support and migration path.
- **Rule:** Deprecated-pack handling policy and UI (warning, no new install, replacement suggestion) defined; implement in catalog and marketplace.

---

## 9. Ownership and provenance

- **Goal:** Every pack has an owner (platform, partner, tenant) and provenance (first-party, certified, community).
- **Fields:** owner_id or owner_type; provenance (e.g. first_party | certified | community); optional certification_level and signed_at.
- **Rule:** Catalog and InstalledPackage record ownership and provenance; marketplace and control plane display them; trust product may use for “Certified” or “Signed” badges.

---

## 10. Signed/certified pack levels (optional)

- **Goal:** Optional levels: unsigned, signed (integrity), certified (platform or partner verified). Enables “Certified” filter and trust UI.
- **Rule:** Optional; implement when trust product and marketplace require it. Document in trust product and marketplace docs.

---

## Implementation status

| Item | Status | Notes |
|------|--------|------|
| Semver for packs | Partial | version in PACKAGE_FORMAT; enforce in PackageVersion and catalog. |
| Dependency graph | Partial | Engine validates; extend to all pack types. |
| Compatibility matrix | Partial | Plan/blueprint; add min_platform_version, region, plan. |
| Safe upgrade path | Partial | Impact preview; document MAJOR upgrade runbook. |
| Downgrade rules | Partial | Rollback exists; document downgrade policy per pack type. |
| Tenant impact preview | Present | preview_diff, _build_impact_summary; expose in UI. |
| Rollback behavior | Present | rollback() in engine; audit log. |
| Deprecated-pack handling | Defined | Policy above; implement in catalog + marketplace. |
| Ownership/provenance | Partial | Add to Package/PackageVersion if not present; display in UI. |
| Signed/certified levels | Optional | Roadmap. |

*Update this table as implementation completes. Completion gate per §10.5.2: versioning and compatibility doc (this doc); upgrade/downgrade/rollback rules in place; tenant impact preview available; deprecated-pack handling defined.*
