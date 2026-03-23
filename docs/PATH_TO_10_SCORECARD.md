# Path to 10/10 Scorecard — Achievable Roadmap

**Short answer: Yes. A scorecard of 10 (and above) is achievable.**

**Completion authority:** **§12 engineering gate (9.5/10)** is **MET** per [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0** / **§12** / **§11.4** (see [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md)). This scorecard describes work to move from **9.5 → 10+** (category polish and north-star depth)—**not** a second gate contradicting §12. Reaching **10/10** means completing the Path-to-10 work in `AUDIT_VS_PLAN_VALIDATION.md` and the toolsets ledger. Nothing is speculative—each item is defined and scoped.

---

## Non-negotiable and advanced-only

- **All Path-to-10 items are non-negotiable.** There are no optional or "nice-to-have" items; every item in this document and in the validation/toolsets ledger must be implemented to spec.
- **Every optional in any plan is also non-negotiable.** Optionals are treated as required (Done or explicitly N/A with justification).
- **Implementation must be to spec and in advanced mode.** No basic coding: edge cases, validation, observability, tests, and docs apply. Basic-only implementations do not satisfy the bar.
- **Code sanitation is non-negotiable.** Before merge or deploy: no `print()` in application code; broad-exception and CSRF/raw-SQL allowlists enforced; repo hygiene and lint gates passing. Run **`bash scripts/code_sanitation.sh`** for the sanitation subset, or **`bash scripts/pre_deploy_gate.sh`** for the full gate.

---

## What "10/10" means

- **Every category** in the dry-run scores **10** (no category still at 9.5).
- **No Path-to-10 item left open:** each item below is either Done or explicitly in progress.
- **Allowlists shrink where possible:** get_solo, broad except, raw SQL, CSRF—continue ratcheting; 10 = no new violations and reduced legacy surface.
- **"10+"** (above 10): industry-leading polish—e.g. performance budgets enforced in CI, full event catalog with replay, external developer portal with certification, AI-generated marketing assets shipped.

---

## Path-to-10 work (by domain)

Execute these to move from 9.5 to 10. Order is logical; dependencies noted.

### 1. Architecture
| Item | Action to reach 10 |
|------|--------------------|
| Giant-file decomposition | Complete decomposition of `siteconfig/models.py`, `accounts/views.py`, `schools/super_views.py`, `portal/views.py`, `finance/views.py`, `api/views_v1.py` per SITECONFIG_OWNERSHIP_MIGRATION; enforce file-line thresholds in CI. |

### 2. Metadata
| Item | Action to reach 10 |
|------|--------------------|
| Full business glossary | Populate and expose BusinessGlossaryEntry (or equivalent) for education terms (class/form/homeroom, term/trimester, levy/tuition, guardian/parent); link to field catalog and show in metadata catalog UI. |

### 3. Runtime & multitenancy
| Item | Action to reach 10 |
|------|--------------------|
| Governor limits | Define and enforce limits (workflow volume, API throughput, dashboard refresh, migration concurrency, dynamic field count, pack complexity); expose in runtime inspector and control plane. |

### 4. Event & orchestration
| Item | Action to reach 10 |
|------|--------------------|
| Event catalog | Formal event catalog (e.g. student_created, applicant_admitted, attendance_marked, grade_published, invoice_created, workflow_activated, blueprint_applied) with payload schemas, tenant context, idempotency; emit from services. |
| Orchestration layer | Long-running process support (admissions, re-enrollment, migration, fee follow-up, approval chains) with state tracking, retries, compensation/rollback, SLA visibility; operator workbench. |

### 5. UX
| Item | Action to reach 10 |
|------|--------------------|
| Empty states = action states | Per-page empty-state treatment: purpose, primary CTA, secondary CTA, optional sample/demo; design system component; apply to catalog, workbench, and list pages. |

### 6. Performance
| Item | Action to reach 10 |
|------|--------------------|
| Performance budgets | Define and enforce (e.g. in CI or deploy gate) response-time and query-count budgets for role homes, critical dashboards, and Setup Studio; fail or warn when exceeded. |

### 7. Marketing
| Item | Action to reach 10 |
|------|--------------------|
| Category-grade AI visuals | Ship AI-generated hero images/videos; migration flow diagrams; setup-studio visuals; ecosystem/marketplace visuals; integrate into marketing_views and templates; keep asset governance (proof_hero_image_key, style tokens). |

### 8. Developer platform
| Item | Action to reach 10 |
|------|--------------------|
| External dev platform | Public API portal (docs, keys, quotas); webhook docs and subscription UI; SDKs or client libs; app certification flow; partner sandbox and scope review. |

### 9. Governance
| Item | Action to reach 10 |
|------|--------------------|
| Management command rationalization | Classify all commands (dev, seed, ops, migration, obsolete); delete obsolete; document and own operational commands; expose critical ops via control-plane UI where appropriate. |

### 10. Toolsets (path-to-10 column)
| Toolset | Action to reach 10 |
|---------|--------------------|
| Theme & Experience | Resolve theme/experience via runtime only; introduce ExperiencePack as packageable unit (theme + layout + dashboard visual + communication style) with compare/rollback. |
| Feature Control | Single capability/flag registry with expiry and review policy; surface in runtime inspector ("why this feature is on"). |
| Report Library | ReportPack model; preview with seeded sample data; dependency mapping (fields, policies, templates). |
| Document Library | Document lifecycle states; retention rules; document packs; search/indexing. |
| Design Studio | Split document vs experience design; layout metadata and layout builder for portal/dashboard. |
| Live Previews | Central preview service; side-by-side before/after where applicable; preview by role/device/tenant in one contract. |
| Workflows | Simulation with impact counts; workflow marketplace cards (outcome-oriented); versioning and replay. |
| AI & API | API contracts and contract tests; AI action audit trail (who invoked what, when, scope). |
| System Config | Migrate remaining get_solo() to runtime resolvers; CI fails on new tenant-facing get_solo (allowlist shrunk to zero or N/A). |

---

## Execution order (recommended)

1. **Quick wins (raise perceived score)**  
   Empty states component; management command index + delete obsolete; performance budget definitions (even if only in docs first).

2. **High leverage**  
   Governor limits; event catalog (core events only); orchestration for migration/approval flows.

3. **Full 10 in each category**  
   Giant-file decomposition; full glossary; ReportPack + preview; ExperiencePack; central preview service; workflow simulation; external API portal.

4. **10+ polish**  
   Performance budgets in CI; AI-generated marketing assets; certification flow; allowlist at zero where feasible.

---

## How to track progress to 10

- **Dry-run table:** When a Path-to-10 item is completed, update `PLATFORM_9.5_SCORE_DRY_RUN.md` Section 1 notes to reflect it and consider raising that category to **10**.
- **Validation doc:** In `AUDIT_VS_PLAN_VALIDATION.md`, change the relevant "Path-to-10" row to **Done** and add evidence.
- **Master checklist:** Add a "Phase 9: Path-to-10" (or equivalent) when you start; list items and check off as done.

---

## Verdict

- **10/10 is achievable:** The work is defined, scoped, and already partially reflected in the codebase (package engine, runtime, Setup Studio, marketplace, control plane).
- **10+ is achievable:** Same list plus stricter enforcement (CI budgets, zero allowlist where possible, shipped AI assets, external dev portal).
- **No new philosophy required:** This is execution of the same north-star standard (Shopify/Salesforce/AWS of education); Path-to-10 is the remaining execution list.

Use this doc as the single roadmap for moving the scorecard from 9.5 to 10 and beyond.

---

## Code sanitation (non-negotiable)

Run before every merge or deploy:

```bash
bash scripts/code_sanitation.sh
```

This runs: `check_repo_hygiene`, `lint_no_print_in_apps`, `check_root_clutter`, `lint_secret_exposure`, `lint_bounded_context_imports`, `lint_siteconfig_legacy_imports`, `lint_tenant_settings --check-get-solo-only`, `lint_csrf_exempt_usage`, `lint_raw_sql_usage`, `lint_broad_except --strict`. All must pass. No basic coding: application code uses structured logging, typed exceptions where appropriate, and allowlisted patterns only.
