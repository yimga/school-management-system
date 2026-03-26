# §5 Toolset remediation — implementation status

**Purpose:** Track implementation evidence for RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §5 (Toolset-specific remediation). Each subsection 5.1–5.9 has current/target scores and actions; this doc records what is implemented and what remains for **continuous** toolset excellence.

**Scores:** Per-subsection **Current → Target** lines mirror SOT §5 **maturity vignettes**. **Authoritative platform gates:** SOT **§0** (9.5/10 §12 **MET**; 11/10 structural **MET**) + **§12** + **§11.4** — not re-proven by this file alone.

**Rule:** Update this file when completing toolset actions; keep in sync with RUNMYCAMPUS §5 and BACKLOG_AND_DEFERRED_CLOSURE.md.

**Status column:** Prefer **DONE**, **NOT DONE**, **BLOCKED**, or **§11.4 depth** (shipped baseline + remaining product excellence). Do **not** use **PARTIAL** as a §12 merge-blocker label — SOT **§12** is **MET**; this table tracks **maturity toward 11/10**, not spine failure.

---

## 5.1 Theme & Experience (Current 6.9/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Move ownership into `brand_experience` | NOT DONE | Pending bounded-context ownership move. |
| Create `ExperiencePack` | NOT DONE | Optional per §11.1; model exists in packages. |
| Unify theme/layout/portal/dashboard visual systems | §11.4 depth | Theme tokens, shell; full unification in progress. |
| Add role/device preview everywhere | DONE | get_studio_role_preview_entries; setup_studio role_previews; theme_studio device preview. |
| Add compare/publish/rollback | §11.4 depth | Theme publish/rollback; package engine preview/apply/rollback. |
| Purge Gilead theme defaults | DONE | Migration 0155; ThemePack runmycampus-gradient. |

---

## 5.2 Feature Control (Current 6.5/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Convert long-lived toggles into capability registry | NOT DONE | feature_control_ledger.md. |
| Add owner/expiry/source/scope to all remaining flags | NOT DONE | In progress. |
| Connect feature state to runtime + entitlements + packs | DONE | get_effective_flags; FeatureToggleDefinition/State; runtime_resolver step6. |
| Show "why enabled?" in runtime inspector | DONE | get_feature_toggle_inspection; super_runtime_inspector.html feature_toggles block. |

---

## 5.3 Report Library (Current 7.1/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Convert into Report Platform inside Output Studio | §11.4 depth | report_library view; Output Studio rail links with embed=1; redirect when not embed. |
| Add ReportPack | DONE | apps.reports.report_packs; list_active_report_packs; build_report_pack_preview. |
| Add sample-data preview | §11.4 depth | report_pack_preview in report_library view. |
| Add dependency mapping | DONE | normalize_report_pack_dependencies; report_pack_dependencies in report_library. |
| Add policy/registry compatibility | NOT DONE | — |
| Add style inheritance/versioning | NOT DONE | — |

---

## 5.4 Document Library (Current 6.9/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Convert into Document & Compliance Content Platform | §11.4 depth | document_library_manage; redirect to Studio Output when not embed; pane=documents. |
| Add lifecycle states | DONE | document_lifecycle.py; DOCUMENT_LIFECYCLE_*; PortalFeatureItem.lifecycle_state; transitions. |
| Add retention/archive policy | DONE | retention_review_at; DocumentPack retention_rule; document_lifecycle normalize_document_retention_rule. |
| Add role-aware access | DONE | PortalFeatureItem.can_view(user); visible_to_roles; manage view docstring. |
| Add signature workflow integration | DONE | FormSignature; requires_signature; signature_request flows. |
| Add search/indexing | DONE | search_index; build_document_search_index; filter by q on title/description/search_index. |
| Add document packs | DONE | DocumentPack; document_pack FK; filter by pack; document_packs in context. |

---

## 5.5 Design Studio (Current 6.8/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Split into Document Design Studio and Experience Design Studio | NOT DONE | — |
| Add layout builder | NOT DONE | — |
| Add section/block system | NOT DONE | — |
| Add responsive preview | §11.4 depth | Theme/setup previews. |
| Add inheritance/versioning | NOT DONE | — |
| Add publish / rollback | §11.4 depth | Theme publish/rollback; package engine. |

---

## 5.6 Live Previews (Current 7.4/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Standardize preview for themes, blueprints, policies, packs, etc. | DONE | studio_preview; get_studio_preview_url; STUDIO_MODE_EMBED_TARGETS; mode=experience delegates to preview_from_form. |
| Add before/after | §11.4 depth | Theme compare; package preview_diff. |
| Add role/device switcher | DONE | get_studio_role_preview_entries; Launch role_previews; theme device preview. |
| Add impact summary | DONE | get_studio_preview_context(mode=launch); studio_preview JSON returns impact_summary, health_summary, recommended_next. |
| Add dependency warnings | DONE | get_studio_preview_context; studio_preview JSON returns dependency_warnings (launch_blockers). |

---

## 5.7 Workflows (Current 7.3/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Build simulation engine | NOT DONE | — |
| Build visual builder | NOT DONE | — |
| Add AI workflow generation | §11.4 depth | AI gateway; workflow clues/suggestions. |
| Add dependency graph | NOT DONE | — |
| Add conflict detection | NOT DONE | — |
| Add staged activation | NOT DONE | — |
| Add replay/rollback | NOT DONE | — |
| Add health analytics | NOT DONE | — |

---

## 5.8 AI and API usage (Current 6.4/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Build backend AI gateway | DONE | services.ai_gateway; AI_GATEWAY_AND_CAPABILITY_FLAGS.md. |
| Add AI permissions/audit | §11.4 depth | AI_audit_trail_and_permissions; services/ai_permissions. |
| Use AI for setup/workflow/migration/policy/search/support | §11.4 depth | AI gateway used in portal/setup/workflow flows. |
| Turn API Center into integration governance console | MET (baseline) | apicenter_integration_governance.md — dashboard + quotas + audit + `test_governance_contract`; interop workbench still NOT DONE. |
| Add contract testing across API/runtime/packages/events | MET (baseline) | test_runtime_contract; test_precedence; platform_runtime tests; broaden per §11.4. |

---

## 5.9 Configuration Control Center / SiteSettings (Current 5.0/10 → Target 11/10)

| Action | Status | Evidence |
|--------|--------|----------|
| Total decomposition into bounded consoles | §11.4 depth | domain_ownership; bounded-context surfaces; SITECONFIG_OWNERSHIP_MIGRATION. |
| Reclassify every settings field | §11.4 depth | Inventory; allowlists. |
| Move tenant behavior out of SiteSettings | DONE | get_effective_site_settings runtime-first; no tenant get_solo in app code; lint_tenant_settings pass; §12 gate MET. RUNMYCAMPUS §5.9 [x]. |
| Add preview/diff/rollback and impact summaries | §11.4 depth | Runtime inspector; package preview. |
| Remove Gilead defaults from settings-driven surfaces | DONE | Migration 0155_normalize_gilead_residue_runmycampus; ThemePack runmycampus-gradient; lint_gilead_residue. RUNMYCAMPUS §5.9 [x]. |

---

## Summary

- **Evidence table:** Use above when updating RUNMYCAMPUS §5 checkboxes or BACKLOG §5/§6 toolset row.
- **Completion gate (11/10):** All actions in a subsection should be DONE or explicitly deferred with a closure note.
- **Cross-ref:** RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §5, BACKLOG_AND_DEFERRED_CLOSURE.md §1 (?5??6), docs_truth_ledger.md.
