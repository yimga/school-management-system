# §0.1.5 evidence register (waves 1–8)

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **§0.1.5** and **§0.1.5.1**. **Internal repo closure** and **external-only OPEN** rows: [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md).

**Rule:** This file is an **evidence index** (tests, scripts, runbooks). It is **not** a second status tracker. Checkbox truth for Wave 8 lives **only** in the SOT. Rows below use:

- **Repo** — evidence exists in-repo for the §0.1.5 deliverable (per SOT `[x]`).
- **Ext** — continuation is **external / product / multi-sprint** — [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) **External** table (or phased product work), **not** an open §0.1.5 internal queue item.

| Wave | Item | Evidence (test / script / runbook) | §0.1.5 |
|------|------|-------------------------------------|--------|
| 1 | Payment webhook CSRF + security | `apps/finance/tests/test_sot_0155_payment_webhook_posture.py`; `WebhookSecurityValidator` | Repo |
| 1 | Secrets / tenant isolation / rollback / fallback / RPO / edge | `lint_secret_exposure.py`; tenant tests; migration cloud rollback; `WAVE_EXECUTION_RUNBOOKS.md`; OneRoster throttle tests | Repo |
| 2 | Internal API, REDUCE_APIS, SMS fallback, N19, Kong | `INTERNAL_API_STANDARDS.md`; `test_internal_api_wave_smoke.py`; `test_sot_0155_sms_fallback.py`; event catalog tests | Repo |
| 3 | OSS spine, adapters, supply chain, Temporal, search, degradation | `open_source_spine.md`; `test_search_read_layer_helpers.py`; runbooks | Repo |
| 4 | POS / fiscal (first-party) | `views_tenant_ops.py`; `test_tenant_ops_wave18_pos`; CSV/JSON exports | Repo |
| 4 | Other operational depth (transport, library, clinic, …) | Connector-first posture: `SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md` / extended ops runbooks | Ext |
| 4 | HR, statutory, rollover, partner/services, ops spine, teaching, HE, community, geography, UK statutory, HE months, ministry | Wave 4 runbooks + compendium links in SOT §0.1.5 | Repo |
| 4 | Advancement / wedge surfaces | Tenant donor/gift paths; `NORTH_STAR_WAVE8_CLOSURE.md` | Repo |
| 5 | Migration playbooks, MigrationProfile, diff schedule, exception queue, OneRoster, MaaS, paper SKU, scorecard, legacy audit, roster webhook | Tests + commands in SOT Wave 5 rows | Repo |
| 5 | Per-vendor automated validation reports at scale | Product increment beyond structural registry | Ext |
| 6 | Paper→digital phases; roll-call drafts | Compendium + `test_roll_call_draft_wiring.py` | Repo |
| 6 | Mobile | Web shell + manifest + drafts (SOT Wave 6); **native store apps** | Repo + **Ext** |
| 7 | Credential, AI,interop, exit, retention, climate, demographics | APIs + runbooks in SOT | Repo |
| 8 | N1–N29 + foundation (repo scope) | [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md); `docs/runbooks/N1_N29_WAVE8_VERIFICATION_POSTURE.md` (methodology); portal + pillar tests | Repo |
| 8 | Formal WCAG audit, native offline, full locale packs, vendor NOC, analytics depth, … | [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md) | Ext |

**Serious / tail (§0.1.5):** OpenAPI — `OPENAPI_SCHEMA_ACCESS.md` + `test_sot_0155_openapi_schema_access.py`; `check --deploy` in CI; 404/500 Phase H tests; pip-audit; SLO/health docs + smoke URLs.

**Regression bundle:**

```bash
python scripts/verify_sot_pillar_evidence.py
python -m pytest apps/portal/tests/
```
