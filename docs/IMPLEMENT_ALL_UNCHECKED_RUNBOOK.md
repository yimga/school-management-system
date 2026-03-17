# Implement All Unchecked SOT Items — Runbook

**Purpose:** Implement **every** remaining `[ ]` in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) and mark each as `[x]` **only after verification**. **All plans referenced in the SOT must be implemented; nothing missed.** Those plans include: SOT itself, [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md), [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [docs_truth_ledger.md](docs_truth_ledger.md), [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md), [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md), [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md), [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md), [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md), SOT §12 evidence table, and **[SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md](SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md)**. **Every gap in the gap audit must be closed** — implement each gap item in §2 "Phase GAP" below; do not skip any. **Do not leave any item as N/A.** Items annotated "N/A — product 2026-03-12" are in scope—implement them. **Do not just mark [x]:** every item must be **verified, audited, tested, and confirmed working** before marking; **nothing can be assumed.** Run **uninterrupted** until everything is **completely done** (or context limits, then resume via session state). Verify the codebase first, then work section by section; fix issues and continue until every [ ] is [x], each [x] has been verified, and **every gap in the gap audit is closed**. **Resumable:** Use [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md) so each run continues from where the last one stopped.

**Authority:** SOT is the single source of truth. This runbook is the procedure only. Do not create new plan files; update only SOT, BACKLOG, docs_truth_ledger, NEXT_50, and N/A_BLOCKERS_AND_RESOLUTION.

---

## 1. How to run (uninterrupted until complete)

- **Verify codebase first:** Before implementing, run `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` or `bash scripts/run_phase_h_verification.sh` and fix any failures so the codebase is in a known-good state.
- **Uninterrupted run:** Do not stop until every [ ] is implemented, **verified** (test/audit/manual), and marked [x]. For each item: implement in the codebase → run relevant tests/lint → verify (UI, API, or doc/audit) → confirm working → **only then** change [ ] to [x] in SOT. Do not leave as N/A. If blocked by a dependency, do the "Unblock by" steps in N/A_BLOCKERS_AND_RESOLUTION, then implement the item. After each phase run verification. **Nothing can be assumed:** if you did not run a test or check, do not mark [x].
- **Resumable (when context limits):** At the start of each run, read `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`. Continue from the "Next section" listed there. At the end of each phase (or every N sections), update SOT_IMPLEMENTATION_SESSION_STATE.md with "Last completed: §X.Y; Next: §X.Y+1" and what was done. Resume the next run from that point until everything is completely done.

---

## 2. Order of work (do not skip)

Follow SOT §11.3 logical order **and** close every item in **Phase GAP** (nothing missed).

| Phase | Sections | What to do |
|-------|----------|------------|
| **Phase II** | §2.4, §3.2 | Any remaining [ ] (signature/replay, raw SQL wrap, SiteSettings in tenant paths). Implement → verify/test → then [x]. If none left, skip. |
| **Phase IIb** | **§10.5 (operating-discipline layers)** | **Run code verification:** `python scripts/verify_section10_5_layers.py`. Must exit 0. For each of 10.5.1–10.5.8 the script checks: doc exists + code evidence (e.g. 10.5.1 structured_logging, 10.5.2 packages/engine rollback, 10.5.4 trust/audit URLs, 10.5.5 data-page-archetype, 10.5.8 phase_h_audit + lints in gate). Fix any failure (add missing doc or implement missing code); do not mark layers done until script passes. No extra doc—code and script only. |
| **Phase III** | §6.1 → §6.24 | For each [ ]: implement (including "N/A — product 2026-03-12") → run tests/lint → verify/audit → confirm working → then [x]. If blocked, do "Unblock by" in N/A_BLOCKERS first. Nothing assumed. |
| **Phase IV** | §4.5, §5.1 → §5.9 | Same: implement → verify/test → confirm working → then [x]. Use N/A_BLOCKERS when needed. Nothing assumed. |
| **Phase V** | §7, §11 Phase H | §7: run `python scripts/verify_section7_gate.py`; implement → verify → [x]. Phase H: run scripts (run_phase_h_verification.sh, pre_deploy_gate.sh); implement and verify any remaining Phase H items; document manual pass if still needed. |
| **Phase GAP** | **SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md** | **Close every gap in the gap audit.** Work through §2.1 below in order (GAP.1 → GAP.N). For each: implement in code → verify (test/lint/UI) → mark done in session state and (optionally) in gap audit §8/§9. Do not skip any gap. Run uninterrupted until all gaps are closed. |

---

### 2.1 Phase GAP — Gap audit closure (every item; do not skip)

**Authority:** [SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md](SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md). Implement each item below in order. After each: verify (test, lint, or UI/API check) → update session state "Last closed gap" / "Next gap to close" → continue. **Nothing can be assumed;** only mark a gap closed after verification.

| # | Gap ID | What to implement | Verify by |
|---|--------|-------------------|-----------|
| GAP.1 | **Marketing: pinned product frame per chapter** | In `static/marketing/js/marketing-product-scroll.js` (and product page): add one **pinned product frame** (desktop) that stays visible; wire **scroll/chapter** (e.g. `data-chapter`) so the **frame content or state updates per chapter** (chapters 1–10). Reuse `.mkt-chapter-pinned` / sticky layout; ensure JS updates the frame when the user scrolls into each chapter. Respect `prefers-reduced-motion`. | Load `/product/`; scroll through chapters; confirm one frame updates (image/section/state) per chapter. |
| GAP.2 | **Marketing: scroll-driven dark-mode and chapter visuals** | Confirm `marketing-product-page.css` and tokens (`--mkt-product-bg`, `--mkt-product-surface`) for dark-first; add or align scroll-driven reveal/stagger for product page sections. | Visual check: dark sections and reveal behavior on product page. |
| GAP.3 | **Control plane: one shell for Studio/Theme on manager host** | When on **manager host** (e.g. manage.runmycampus.com), Studio OS and Theme & Experience must render inside **control_plane_base** (same top bar and sidebar as `/super/`). Either: (a) serve Studio/Theme from a base that extends `control_plane_base` on manager host, or (b) include same navbar/sidebar partials so header and IA match. Update `studio_os/shell.html` (or routing) so manager-host requests use control-plane shell. | On manager host: open Studio and Theme & Experience; confirm same top bar and left sidebar as `/super/`. |
| GAP.4 | **Security: signature/replay for SCIM and Section8 LTI** | Per `docs/public_endpoint_audit.md`: add signature verification and/or replay protection (e.g. HMAC, timestamp/nonce) for SCIM and Section8 LTI endpoints where marked `manual_review_required`. Add tests; update ledger. | Run tests for SCIM/LTI auth; confirm ledger updated; security review note if deferred by product. |
| GAP.5 | **Runtime tracing (platform_runtime)** | Add tracing (e.g. span/context) for resolver resolution in `apps/platform_runtime` (e.g. in resolver_registry or get_effective_site_settings path). Optional: integrate with observability app. | Code: span or context set in resolver path; optional test or log assertion. |
| GAP.6 | **Why-enabled entitlement UI** | Expose "why this entitlement" (e.g. which plan/rule enabled it) in runtime inspector or Control Studio UI. Add field or section in runtime inspector (and/or plans_entitlements) that shows why an entitlement is on/off. | Open runtime inspector or Control Studio; confirm "why enabled" visible for at least one entitlement. |
| GAP.7 | **Policy: impact preview** | Implement impact preview for policy bundle changes (e.g. affected tenants, features). Can be in super_policy_diff or a separate view. | UI or API: trigger preview; confirm affected tenants/features shown. |
| GAP.8 | **Policy: sandbox apply (policy bundle)** | Implement apply policy bundle to sandbox; staged rollout; document in policy ledger or CONTROL_PLANE. | Apply to sandbox from UI or API; verify behavior. |
| GAP.9 | **Policy: dependency graph** | Policy bundle dependency graph (which blueprints/workflows depend on bundle). Expose in Control or get_blueprints. | View in UI or API; confirm graph or list of dependents. |
| GAP.10 | **Observability: request/runtime/workflow/package tracing** | Implement or wire tracing across request, runtime resolution, workflow, package, migration (e.g. trace_id/span_id in logs or observability app). | Trace ID present in logs or observability dashboard for at least one path. |
| GAP.11 | **Marketplace: previews/screenshots, trust markers, scope visibility** | Per PATH_TO_100 III.22–III.25: add preview/screenshot fields and UI; trust badges (verified, security review); show required permissions/scopes in app listing and install flow. | Marketplace catalog and install flow show screenshots, trust markers, and scopes. |
| GAP.12 | **Theme/Experience: ownership in brand_experience; unified visual system** | Per PATH_TO_100 IV.2–IV.3: move theme/experience ownership into brand_experience (models/resolvers); unify theme/layout/portal/dashboard visual systems (single token/layout system). | Resolvers and models in brand_experience; portal and dashboard use same design system. |
| GAP.13 | **Feature Control: registry + metadata on flags** | Per PATH_TO_100 IV.4–IV.5: convert long-lived toggles to capability registry entries; add owner/expiry/source/scope to flags; expose in runtime inspector. | Runtime inspector shows flag metadata; registry used for at least one capability. |
| GAP.14 | **Operating discipline: full rollout 10.5.3–10.5.8** | Complete implementation for service/support (10.5.3), dashboard taxonomy (10.5.5), content/terminology (10.5.6), design system behavior (10.5.7), boring excellence (10.5.8) per OPERATING_DISCIPLINE_LAYERS.md. Ensure verify_section10_5_layers.py still passes; add code evidence where script expects it. | `python scripts/verify_section10_5_layers.py` exits 0; each layer has doc + code evidence. |
| GAP.15 | **Decision architecture: seven answers declared** | For every important page/dashboard in scope: declare the seven answers (who, what question, state, next action, confidence, wrong-path, fallback) either in DASHBOARD_TAXONOMY_AND_REGISTRY.md or via in-code `decision_architecture` dict / data attributes. Extend data-page-archetype where needed; add registry rows or template context for key pages. | Key dashboards/pages have seven answers in registry or in code; DECISION_ARCHITECTURE_CHECKLIST satisfied. |

**After each GAP.n:** Update `docs/SOT_IMPLEMENTATION_SESSION_STATE.md` under "Gap audit progress": set "Last closed gap" to GAP.n and "Next gap to close" to GAP.n+1 (or "All gaps closed"). Optionally update SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md §8 summary or §9 to mark the gap closed.

---

## 3. For each unchecked `[ ]` (loop) — implement, then verify, then mark

1. **Locate** the item in SOT (section and line) or in **Phase GAP** (§2.1: GAP.1–GAP.15). Items annotated "N/A — product 2026-03-12" are **in scope**—implement them. Cross-check [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md), [SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md](SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md), and any plan referenced in that section so **nothing is missed**.
2. **Implement:**
   - Implement the item in the codebase (code, config, tests, or docs as appropriate). Use [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for detail and [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) for "Unblock by" steps if the item depends on something else. If blocked by a dependency, implement the dependency first, then this item.
   - **Verify:** Run relevant tests and/or lint for this item (or the area it touches). If the item is UI/API, run the test or a quick manual check; if doc/ledger, confirm the doc exists and is accurate. **Do not mark [x] until you have run a verification step.**
   - **Audit/test:** Confirm the change is working (test pass, lint pass, or explicit manual/audit check). **Nothing can be assumed**—if you did not verify, do not mark [x].
   - **Only then** change `[ ]` to `[x]` in SOT and add a short "DONE: …" or verification note if helpful.
   - If you hit an issue you cannot fix in this run, note it briefly and continue to the **next** item so nothing is skipped; return when unblocked.
3. **Reference other docs** when implementing (all referenced plans must be implemented; nothing missed):
   - [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for implementation detail.
   - [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) for "Unblock by" and concrete steps.
   - [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §1 and §2e for closure and next steps.
   - [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md), [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md), [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md) when the item references them.
4. **Phase-level verify:** After implementing a batch, run `bash scripts/run_phase_h_verification.sh` or `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` so nothing is broken. Fix any failures before proceeding.

---

## 4. Session state (resumable runs)

- **File:** `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`
- **At start of run:** Read it. If "Next section" is set, start from that section; otherwise start from Phase II (§2.4).
- **At end of each phase (or every 2–3 sections):** Update the file:
  - `Last completed:` §X.Y (and one-line summary)
  - `Next section:` §X.Y+1 (or next phase)
  - `Date (UTC):` and optional `Done this session: [list]`

This way the next agent run (or new chat) can continue without redoing work and without you having to remember where you stopped.

---

## 5. Rules (do not break)

- **Ultra high-end without compromise:** Every implementation must be **ultra high-end** — no shortcuts, no "good enough," no placeholder-quality UI or copy. If something would lower the bar (e.g. generic styling, weak empty states, inconsistent tokens, or non-responsive layout), improve it to meet the bar; do not ship it as-is. SOT §8.0 and §8.0.11 define this bar; apply it to every page and surface.
- **Single tracking:** Status and "what's left" stay in SOT only (§11.4). Do not add status to PATH_TO_100, PLAN_AND_BACKLOG_STOCK_TAKE, or other plan docs.
- **No new plan files:** Do not create new strategy/roadmap/remediation plan files. All updates go to SOT, BACKLOG, docs_truth_ledger, NEXT_50, N/A_BLOCKERS.
- **Do not mark [x] without verification:** Every [x] must be backed by a run test, lint, or explicit manual/audit check. Confirm the item is working before marking. **Nothing can be assumed.**
- **Visible after deploy:** Every [x] you add must be verifiable (UI, API, or doc/lint/test). Add a short note if not obvious.
- **Implement all; no N/A:** Every [ ] must be implemented, verified, and then marked [x]. Do not leave items as N/A. Use N/A_BLOCKERS only for unblock steps (implement dependency, then item).
- **All referenced plans implemented:** Every item that maps from SOT to PATH_TO_100, BACKLOG, OPERATING_DISCIPLINE_LAYERS, CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL, DECISION_ARCHITECTURE_CHECKLIST, §12 evidence, or **SOT_DOCUMENTS_VS_CODE_GAP_AUDIT** must be implemented and verified; nothing missed.
- **All gap audit items closed:** Complete Phase GAP (§2.1) in order (GAP.1 → GAP.15). Do not skip any gap; update session state after each.

---

## 6. When "everything" is done

- Every `[ ]` in SOT is `[x]`, and **each [x] has been verified** (test, lint, or audit/manual check)—nothing assumed.
- **Every gap in [SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md](SOT_DOCUMENTS_VS_CODE_GAP_AUDIT.md) is closed** (GAP.1–GAP.15 implemented and verified).
- Run full gate: `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` (and optionally E2E when available). Fix any failures.
- Record gate output per RELEASE_CHECKLIST: `bash scripts/record_pre_deploy_gate_output.sh`.
- Update SOT §11.4 "What's left for 10/10" and "Last run" if needed.
- Update `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`: set "Next section" to "All phases complete", "Next gap to close" to "All gaps closed", and date.

**Runbook completion checklist (tick before release):**

| Step | Action | Done when |
|------|--------|-----------|
| 1 | Verify codebase | `bash scripts/run_phase_h_verification.sh` passes (or `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh`) |
| 2 | **§10.5 layers (code)** | `python scripts/verify_section10_5_layers.py` exits 0 (all 8 layers: doc + code). |
| 3 | All SOT [ ] → [x] | No unchecked items in SOT; each [x] verified (test/lint/audit). |
| 4 | **All gap audit items closed** | GAP.1–GAP.15 in §2.1 implemented and verified; session state "Next gap to close" = "All gaps closed". |
| 5 | Full gate | `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` passes. |
| 6 | Record gate output | `bash scripts/record_pre_deploy_gate_output.sh`; output in docs/generated/pre_deploy_gate_run.txt. |
| 7 | Release sign-off | Launch 10-point run in staging; launch_studio_checklist.md §4 + RELEASE_CHECKLIST filled. |
| 8 | Session state | SOT_IMPLEMENTATION_SESSION_STATE.md "Next section" = "All phases complete" (and date). |

**Gap closure tick list (use with §2.1; tick when verified):**

| GAP.1 | GAP.2 | GAP.3 | GAP.4 | GAP.5 | GAP.6 | GAP.7 | GAP.8 | GAP.9 | GAP.10 | GAP.11 | GAP.12 | GAP.13 | GAP.14 | GAP.15 |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|--------|--------|--------|--------|--------|--------|
| [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] |

**Continuous improvement (after runbook complete):** Use SOT §1.8 "Principle compliance and gaps" to drive ongoing improvements: runtime strictness (1.1), metadata expansion (1.2), pack versioning/rollback uniformity (1.3), outcome-driven config UX (1.4), low-click/sidebar/responsive (1.5), security hardening of manual_review endpoints (1.6), legacy removals and retire legacy URLs (1.7). Update SOT §11.4 and BACKLOG as improvements are completed.

---

## 7. Prompt to start a run

Use this prompt to have an agent (or yourself) implement and verify everything without skipping and without assuming:

---

**Prompt:**

Execute docs/IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md against docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md. All plans referenced in the SOT (PATH_TO_100, N/A_BLOCKERS, BACKLOG, docs_truth_ledger, NEXT_50, OPERATING_DISCIPLINE_LAYERS, CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL, DECISION_ARCHITECTURE_CHECKLIST, RunMyCampus_Enterprise_Architecture_Audit, §12 evidence, and **SOT_DOCUMENTS_VS_CODE_GAP_AUDIT**) must be implemented and verified; nothing missed.

(1) **Verify codebase first:** Run `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` or `bash scripts/run_phase_h_verification.sh` and fix any failures before implementing.

(2) **§10.5 operating-discipline layers (do not skip):** Run `python scripts/verify_section10_5_layers.py`. Must pass (exit 0). The script checks all eight layers (10.5.1–10.5.8): doc exists + code evidence. If it fails, fix the missing code or doc; do not add unnecessary doc—implement what the script expects (see OPERATING_DISCIPLINE_LAYERS.md completion gates). Then proceed.

(3) **For each [ ] in SOT** (in order: §2.4, §3.2, §6.1→§6.24, §4.5, §5.1→§5.9, §7, §11 Phase H):  
- Implement the item in the codebase (use docs/PATH_TO_100_PERCENT_EXECUTION_PLAN.md and docs/N/A_BLOCKERS_AND_RESOLUTION.md for "Unblock by" when blocked).  
- **Verify:** Run the relevant tests, lint, or a manual/audit check.  
- **Confirm working:** Do not mark [x] until you have verified the item is working. Nothing can be assumed.  
- Only then change [ ] to [x] in the SOT. Items annotated "N/A — product 2026-03-12" are in scope—implement and verify them the same way.

(4) **Phase GAP — close every gap in SOT_DOCUMENTS_VS_CODE_GAP_AUDIT (do not skip):** Work through runbook §2.1 in order (GAP.1 → GAP.15). For each: implement in code → verify (test/lint/UI) → update docs/SOT_IMPLEMENTATION_SESSION_STATE.md "Last closed gap" / "Next gap to close". Do not skip any gap. All 15 gaps must be closed before "everything" is done.

(5) **After each phase** run verification (run_phase_h_verification.sh or pre_deploy_gate.sh) and fix failures. Update docs/SOT_IMPLEMENTATION_SESSION_STATE.md so the next run can resume.

(6) **Run uninterrupted** until every [ ] is [x], each [x] has been verified, and **all GAP.1–GAP.15 are closed**. Do not stop until everything is completely done unless you hit context limits—then update session state and resume in the next run. When all phases and all gaps are complete, run the full gate once and record output per docs/RELEASE_CHECKLIST.md.

---

*Cross-reference: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.3–11.4, [REDUNDANCY_AND_PLAN_INDEX.md](REDUNDANCY_AND_PLAN_INDEX.md), [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md).*
