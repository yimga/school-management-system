# RunMyCampus — agent execution contract

This repository is **not** a greenfield project. Use the **existing** enforcement layer as the primary control framework.

## Control framework (read before large edits)

| Artifact | Role |
| --- | --- |
| [docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) | Single execution source of truth; forward queue in §11.4 |
| [docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) | Wave-by-wave implementation log |
| [docs/phase_checklists/](docs/phase_checklists/) | Phase checklists + gate crosswalk ([README](docs/phase_checklists/README.md)) |
| [docs/SITECONFIG_OWNERSHIP_MIGRATION.md](docs/SITECONFIG_OWNERSHIP_MIGRATION.md), [docs/site_settings_usage_inventory.md](docs/site_settings_usage_inventory.md) | SiteSettings / siteconfig ownership |
| `scripts/verify_*.py`, `scripts/lint_*.py` | Mechanical gates; `verify_phases_3_11_gates.py` bundles many |
| `scripts/generated/*.json`, `docs/generated/*` | Regenerated ledgers and inventories — run writers when verifiers say stale |

## Autonomous slice loop (every deliverable)

1. **Inspect** — Scope files, routes, templates, and which verifier(s) apply.
2. **Map** — Phase checklist entry, SOT §11.4 row if shipping a batch, generated artifacts touched.
3. **Implement** — Smallest diff; match existing patterns.
4. **Regenerate** — e.g. `scripts/build_phase8_security_ledger.py --write` when allowlists change; `generate_platform_inventory` when the gate requires it.
5. **Validate** — Narrow verifier first, then broader bundle (`verify_phases_3_11_gates.py` or release script per SOT).
6. **Remediate** — Fix failures; do not “declare done” from narrative alone.
7. **Record** — Autonomous log + checklist + §11.4 when the slice closes.

## Slice selection (do not ask the user unless blocked)

Derive the next slice from, in order:

1. Failing or stale gates / generated artifacts / allowlist drift  
2. SOT §11.4 forward queue head and PATH action rows  
3. Architecture gravity (singletons, shell fragmentation, public endpoints, raw SQL)  
4. Operator UX / control plane / Studio OS / dashboards  
5. Docs truth, Gilead residue, contradictory claims  

**Mechanical gate pass ≠ full product maturity.** After gates are green, continue with the next highest-value SOT or PATH slice until blocked or the queue has no next implementable row.

**Multi-batch rule (no early stop):** Stopping after a single “shippable” batch or a “clear handoff” is **not allowed** when more **safely executable repo-contained** slices remain. After each green batch (code + verifiers + support docs as required), **automatically** select and execute the **next** highest-value slice from SOT **section 11.4** / **PATH** until a **true blocker** exists or the run has **exhausted** safely executable work—not when verifiers are merely green or documentation is updated.

**No “pass complete” stop:** Do **not** end a run because a “single autonomous pass” is done, the next tranche would need a **new section 11.4 row**, the wave switched surface (e.g. static/JS to templates/views), or the next chunk is “larger.” If the next work is **known and can be scoped**, **add the section 11.4 row (and PATH/autonomous support lines if required) yourself** and **continue in the same run**. A wave is **not** “exhausted” merely because the next slice is template or inheritance work instead of prior classifier or CSS edits.

## Parallelism

Partition by route family, app, or audit category. One coordinator reconciles and runs verifiers; avoid two agents editing the same hot files without ordering.

## Blockers only

Stop and ask only for: missing secrets, irreversible external decisions, or ambiguity that cannot be resolved from the repo.
