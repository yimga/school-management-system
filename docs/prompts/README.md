# RunMyCampus orchestrator prompt pack (100% complete)

**Version:** `2026-05-20-orchestrator-v5`  
**Plan:** [9-agent moderator wave](.cursor/plans/9-agent_moderator_wave_11e58d68.plan.md) + seven-pillar audit  
**Verifier:** `python scripts/verify_orchestrator_prompt_pack.py --strict`  
**Regenerate:** `python scripts/generate_orchestrator_prompt_pack.py`

## Gear-up layers (every agent — non-optional)

Each stage prompt and worker paste includes three stacked bars:

| Layer | File | Bar |
|-------|------|-----|
| V3 | [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md) | North Star 75/75, admin-gravity strict, gap burndown |
| V4 | [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md) | Ollama live, category-defining wins, competitive proof |
| V5 | [`00-gear-up-v5-transformational.md`](00-gear-up-v5-transformational.md) | 27 journeys, dual-host sweep, nav ledger, measurable wins |

Recovery checklist: [`recovery-wave-v5.md`](recovery-wave-v5.md)

## How to use

### Fast path (recommended)

Paste **one file** from [`worker-paste/`](worker-paste/) per agent — each bundle includes global rules, platform clause, moderator addendum, **v3+v4+v5 gear-up**, stage prompt, pillar excerpt, and report-back footer.

Example: Agent 1 → [`worker-paste/agent1-stage-1.md`](worker-paste/agent1-stage-1.md)

Regenerate: `python scripts/generate_orchestrator_prompt_pack.py`

### Manual path

1. Open **one Cursor/Claude session per agent** (or sequential waves per dependency).
2. Paste in order:
   - [`00-global-execution-rules.md`](00-global-execution-rules.md)
   - [`00-platform-wide-clause.md`](00-platform-wide-clause.md)
   - [`00-moderator-addendum.md`](00-moderator-addendum.md)
   - [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md)
   - [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md)
   - [`00-gear-up-v5-transformational.md`](00-gear-up-v5-transformational.md)
   - Stage file for assigned agent (below)
   - Pillar bundle from [`pillar-prompts-01-07.md`](pillar-prompts-01-07.md) when mapped
3. End every worker session with **REPORT BACK TO ORCHESTRATOR** (see global rules).
4. Moderator session uses [`00-moderator-chief-orchestrator.md`](00-moderator-chief-orchestrator.md) or [`worker-paste/moderator.md`](worker-paste/moderator.md).

## Agent → prompt file map

| Agent | Stage | Primary prompt | SOT batch | Pillars |
|-------|------:|----------------|-----------|---------|
| **Moderator** | — | `00-moderator-chief-orchestrator.md` | 1319–1329, 1354 | CTO |
| **Agent 0** | 0 | `stage-00-current-state-validation.md` + `phase-0-p0-deploy-gate.md` | 1319 | P6 |
| **Agent 1** | 1 | `stage-01-core-runtime.md` | 1320 | P6, P7 |
| **Agent 2** | 2 | `stage-02-tenant-isolation.md` | 1321 | P3, P7 |
| **Agent 3** | 3 | `stage-03-edge-routing-branding.md` | 1322 | P1, P3 |
| **Agent 4** | 4 | `stage-04-policy-entitlements.md` | 1323 | P3 |
| **Agent 5** | 5 | `stage-05-finance-ledger.md` | 1324 | P5 |
| **Agent 6** | 6 | `stage-06-academics-operations.md` | 1325 | P4 |
| **Agent 7** | 7 | `stage-07-migration-cloud.md` | 1326 | — |
| **Agent 8** | 8 | `stage-08-workspace-ux.md` | 1327 | P1, P2 |
| **Agent 9** | 9 | `stage-09-ai-center-expanded.md` (NOT `stage-09-api-automation-base.md` alone) | 1328 | P4 |
| **Agent 10** | 10 | `stage-10-final-certification.md` | 1329 | All |

## Dependency order (mandatory)

```text
Phase 0 → Stage 0 → Stage 1 → Stage 2 → Stage 3
→ Stage 4 → (5,6 parallel) → Stage 7 → Stage 8 → Stage 9 → Stage 10
→ second-pass review → CTO synthesis
```

## 100% completeness checklist (verifier enforces)

- [x] Global rules + platform clause + moderator addendum
- [x] Gear-up v3 + v4 + v5 on every stage, phase-0, moderator, and worker paste
- [x] Moderator chief orchestrator prompt (full)
- [x] Phase 0 P0 deploy gate prompt
- [x] Stages 0–10 individual prompt files
- [x] Stage 9 expanded (19 phases, Modelfile, 14+ proof artifacts, security tests)
- [x] Seven-pillar prompts 1–7 + CTO synthesis (gear-up prerequisite)
- [x] Journey manifest 27 + coverage verifier
- [x] Standard verifier stack documented
- [x] A–L (Stage 9: A–U) final report format
- [x] `agent-assignment-index.json` machine manifest
- [x] `worker-paste/*.md` one-shot bundles (11 agents + moderator)
- [x] CI gate `orchestrator-prompt-pack` in `architectural-boundaries.yml`

## Tracking artifacts (moderator maintains)

- `docs/generated/orchestrator_execution_matrix.json`
- `docs/generated/orchestrator_gap_burndown.json`
- `docs/generated/orchestrator_journey_manifest.json`
- `docs/generated/orchestrator_journey_coverage.json`
- `docs/generated/aggressive_stage_execution_readiness.json`
- `docs/generated/orchestrator_prompt_pack_audit.json` (from verifier)
- `docs/generated/ten_x_platform_certification.json` (v3/v4/v5 compliance pct)
