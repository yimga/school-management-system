# SOT Plan vs Code — Gap Audit

**Purpose:** Items that appear in the plan documents (SOT and referenced docs) but are **not implemented**, **only partially implemented**, or **stub/placeholder** in the codebase. This supports the single source of truth and release readiness.

**Scope:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) and its referenced plans: PATH_TO_100_PERCENT_EXECUTION_PLAN.md, CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md, RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md, ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md, OPERATING_DISCIPLINE_LAYERS.md, DECISION_ARCHITECTURE_CHECKLIST.md, public_endpoint_audit.md, BACKLOG_AND_DEFERRED_CLOSURE.md.

**Date:** 2026-03-16 (audit run).

---

## 1. Marketing & scroll-storytelling

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md** (§2, §4) | Sticky/pinned **product frame** on desktop; **visual updates as user scrolls through chapters**; one pinned frame that **updates content per chapter**. | **Partially coded:** `marketing_product_page.html` has one section with `.mkt-chapter-pinned` and sticky visual (Studio OS). There is **no** single pinned product frame that **changes content/state per chapter** (chapters 1–10). `marketing-product-scroll.js` only does scroll progress + reveal (IntersectionObserver for `.mkt-reveal`); it does **not** wire `data-chapter` to a pinned frame or swap frame content per chapter. |
| **CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md** §4 | Scroll-storytelling: "Remaining: **pinned product frame per chapter**, **visual updates per chapter**." | Same as above: layout/CSS support one pinned section; JS does not implement chapter-driven pinned frame or per-chapter visual updates. |
| **ADMIN_SUPER_SINGLE_ENTRY_AND_MARKETING_PRODUCT_PAGE.md** §2 | Product page: **pinned product frame per chapter**; **scroll-driven dark-mode**; in `marketing-product-scroll.js` wire **chapter progress** to **pinned product frame** and **update frame content or state per chapter**. | Pinned frame that updates per chapter is not implemented in JS. Dark tokens and scroll progress exist; chapter-to-frame binding is missing. |

---

## 2. Control plane — one shell (manage.runmycampus.com)

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md** §0, §2 | **One shell:** Every page under manage.runmycampus.com (`/super/*`, **`/studio/*`**, Theme & Experience, etc.) must render inside **one** base: same top bar, **one** left sidebar. | **Partially coded:** `/super/*` uses `control_plane_base.html` (one sidebar). **Studio OS** and **Theme & Experience** use `portal_base.html` (e.g. `templates/studio_os/shell.html` extends `portal_base.html`; most Studio and siteconfig theme templates extend `portal_base` or `backend_base`). So on the manager host, Studio and Theme & Experience show the **portal** header/sidebar, not the control-plane bar/sidebar. Only `shell_control_plane.html` extends `control_plane_base`; the main Studio shell used in app flow is `shell.html` → portal_base. |
| **SOT §8.0.2** | `/studio/control/`, `/admin`, and `/super/` must resolve to the **same design tokens and shell**. | Same gap: Studio (and Theme & Experience) on manager host do not use the same shell as /super/. |

---

## 3. Security — signature/replay where manual_review_required

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **public_endpoint_audit.md**; **PATH_TO_100** II.1 | Add stronger **signature and replay protection** where marked `manual_review_required` (SCIM, Section8 LTI, etc.). | **Documented as DEFERRED:** Billing and Finance webhooks have signature + 401; SCIM and Section8 LTI have rate limit + audit logging; **signature/replay for SCIM and LTI are specified but implementation deferred** to manual security review. So "in plan" = add signature/replay for those endpoints; "in code" = not implemented for SCIM/LTI (by design, per audit). |
| **SOT §11.2 Phase II** | Phase II.1: Add signature/replay where manual_review_required. | Same: remaining manual_review_required endpoints (SCIM, LTI) do not have signature/replay in code. |

---

## 4. PATH_TO_100 / Phase III – app-by-app (examples)

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **PATH_TO_100** III.5 (§6.2 platform_runtime) | **Add runtime tracing** (e.g. span/context for resolver resolution). | **Partial:** request-scoped `runtime_trace_id` on `get_effective_site_settings` and `build_tenant_runtime`; included in structured log context. OpenTelemetry-style spans not present. |
| **PATH_TO_100** III.18 (§6.8 plans_entitlements) | **Why-enabled UI:** Expose "why this entitlement" in runtime inspector or control UI. | No code found for "why_enabled", "why entitlement", or equivalent in runtime inspector or control UI. |
| **PATH_TO_100** III.26–III.29 (§6.11 policies) | Policy **diff engine**, **impact preview**, **sandbox apply** (policy bundle), **dependency graph** for policies. | Policy **diff** exists (`super_policy_diff` view + template). Impact preview, sandbox apply for policy bundle, and policy dependency graph are not verified in code (would need targeted search per item). |
| **PATH_TO_100** III.67 (§6.23 observability) | **Request/runtime/workflow/package/migration tracing**. | No unified tracing implementation found across request/runtime/workflow/package/migration. |
| **PATH_TO_100** III.22–III.25 (§6.10 marketplace) | Richer listing metadata; **previews/screenshots**; **trust markers**; **scope/permission visibility** in app listing and install flow. | Not audited line-by-line; doc says "Implement"; if any of these are missing in marketplace UI, they count as "in doc but not coded." |

*Note:* PATH_TO_100 lists ~100+ items; this table samples high-impact or clearly absent items. A full audit would check each Phase III/IV/V row against code.

---

## 5. Phase IV – toolset (sampled)

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **PATH_TO_100** IV.2–IV.3 (§5.1) | **Move theme/experience ownership into brand_experience**; **unify** theme/layout/portal/dashboard visual systems. | SOT marks behavioral ownership and bounded-context surfaces as DONE; "real" model ownership in brand_experience and single token/layout system may still be partial (not fully verified in this audit). |
| **PATH_TO_100** IV.4–IV.5 (§5.2) | **Feature toggle → capability registry**; **owner/expiry/source/scope** on flags; expose in runtime inspector. | feature_control_ledger and runtime inspector exist; full migration of long-lived toggles to registry and full metadata on every flag may be partial. |

---

## 6. Operating discipline & decision architecture

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **OPERATING_DISCIPLINE_LAYERS.md** 10.5.3–10.5.8 | **Service/support** layer, **dashboard taxonomy**, **content/terminology**, **design system behavior**, **boring excellence** — surfaces and implementation. | **Phase I** is doc + code evidence. `scripts/verify_section10_5_layers.py` exists and checks doc + code; 10.5.3 uses a loose check (support/customer in URLs or "doc defines surfaces"). Full rollout of 10.5.3–10.5.8 is **incremental** per BACKLOG; not every layer has full implementation (e.g. dedicated service/support dashboard, full dashboard registry population). |
| **DECISION_ARCHITECTURE_CHECKLIST.md** | Every important page/dashboard/workflow must **declare seven answers** (who, what question, state, next action, confidence, wrong-path, fallback). | **Partially coded:** `data-page-archetype` appears on many templates (role-home, operational-workbench, catalog, etc.); the checklist also allows declaration in **DASHBOARD_TAXONOMY_AND_REGISTRY** or in-code **decision_architecture** dict. No grep for full seven-answer declaration in code; many pages have archetype only, not the full seven-question declaration. |

---

## 7. Pack provenance and metadata

| Document (section) | What the doc says | Why "not coded" / gap |
|--------------------|-------------------|------------------------|
| **SOT §6.3** / PATH_TO_100 III.7 | **Pack provenance** (e.g. pack_id, version) on metadata entities; expose in lineage/UI. | **Coded:** `EntityCatalogEntry` has `source_pack_id` and `source_pack_version`; lineage API exposes them. No gap for this item. |

---

## 8. Summary table (quick reference)

| Area | In doc | In code | Gap |
|------|--------|--------|-----|
| Pinned product frame **per chapter** + chapter-driven visual updates | Yes (scroll directive; CONTROL_PLANE §4; ADMIN_SUPER §2) | **Yes** (`marketing-product-scroll.js` + `#mkt-product-pinned-frame` / `data-chapter` panels) | **No** (verify on `/product/` if regressions) |
| One shell for Studio/Theme on manager host | Yes (CONTROL_PLANE §0, §2; SOT §8.0.2) | **Partial:** `use_control_plane_shell` → **`studio_os/shell_control_plane.html`** for manager host; Theme & Experience paths may still use portal shell — verify per URL | **Partial** |
| Signature/replay for SCIM/LTI (manual_review_required) | Yes (PATH_TO_100 II.1; public_endpoint_audit) | Deferred (rate + audit done) | **Yes** (by design) |
| Runtime tracing (resolver span/context) | Yes (PATH_TO_100 III.5) | **Partial:** `set_runtime_trace_context` on `get_effective_site_settings` + `build_tenant_runtime` (incl. cache hit); `runtime_trace_id` in `request_context_for_log` (`apps/platform_runtime/tracing.py`, `helpers.py`, `structured_logging.py`; tests `test_runtime_contract`, `test_structured_logging`) | **Partial** (OpenTelemetry spans / distributed trace not wired) |
| Why-enabled entitlement UI | Yes (PATH_TO_100 III.18) | No | **Yes** |
| Policy impact preview / sandbox apply / dependency graph | Yes (PATH_TO_100 III.27–29) | Policy diff only | **Partial** |
| Request/runtime/workflow/package tracing | Yes (PATH_TO_100 III.67) | No | **Yes** |
| Pack provenance (metadata) | Yes (SOT §6.3) | Yes | **No** |
| Decision architecture (seven answers) | Yes (DECISION_ARCHITECTURE_CHECKLIST) | data-page-archetype only in many places | **Partial** |
| Operating discipline layers 10.5.3–10.5.8 | Yes (OPERATING_DISCIPLINE_LAYERS) | Incremental; verify script passes | **Partial** |

---

## 9. How to use this audit

- **Runbook (mandatory):** Every gap in this audit must be closed as part of the runbook. See **[IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md) §2.1 Phase GAP** for the ordered list (GAP.1–GAP.15). Implement each in order without skipping; update [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md) "Gap audit progress" after each. Run uninterrupted until all gaps are closed.
- **Prioritization:** Within the runbook, Phase GAP follows Phase V; work GAP.1 → GAP.15 in order.
- **SOT alignment:** Do not claim "all plan items coded" while these gaps remain; SOT §11.4 and §12 remain the authority.
- **Updates:** When a gap is implemented and verified, update session state "Last closed gap" / "Next gap to close"; optionally add a one-line note in this doc §8 that the gap is closed.

---

*Generated from plan vs code comparison; see RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md and referenced docs. Implementation: IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md Phase GAP (§2.1).*
