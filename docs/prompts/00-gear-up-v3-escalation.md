# Gear-Up V3 — Platform Escalation

**Pack:** `2026-05-20-orchestrator-v4`

## GEAR-UP V3 — PLATFORM ESCALATION (all agents)

**Pack:** `2026-05-20-orchestrator-v3` — supersedes v2 execution bar. **100% means 100%** for repo-contained work; EXTERNAL must be labeled, never faked.

### Cross-cutting quality bar (every stage)

1. **Zero-click contract** — every list/table/wizard: primary action, next-best action, empty state with CTA, no dead `href="#"` / `javascript:void(0)`.
2. **Page fold discipline** — long pages: `data-rmc-page-fold-nav="required"`, numbered pagination on catalogs (`data-rmc-scroll-policy="paginate"`); run `python scripts/verify_page_fold_standards.py` when templates change.
3. **Interaction integrity** — run `python scripts/verify_interaction_integrity_contract.py` on touched portal/control-plane templates.
4. **Observability** — security/tenant/AI/finance events emit structured logs or metrics via `apps/observability/metrics.py` (no PII in labels).
5. **Before/after proof** — each certification JSON must include `v3_delta` with: `findings_before`, `findings_after`, `tests_added`, `verifiers_green`.
6. **Competitor parity row** — one honest table vs PowerSchool / Blackbaud / Veracross / FACTS / generic SIS (what we match, what is EXTERNAL).
7. **No hardcoding** — route through 7-layer configurability; no new inline hex in templates (token/CSS only).
8. **Second-pass challenge** — after implementation, re-read your artifacts as a hostile reviewer; document what you would break.

### V3 verifier additions (run when in scope)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/verify_platform_chromatic_compliance.py
```

North Star target: **75/75 ELITE** (not 71/75) before Stage 10 can claim READY.

