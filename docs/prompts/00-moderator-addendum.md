# MODERATOR ADDENDUM

**From:** [9-agent moderator wave plan](.cursor/plans/9-agent_moderator_wave_11e58d68.plan.md)  
Paste with global rules + platform clause on **every worker agent** (not on Moderator chief prompt).

---

## MODERATOR CONTRACT

```text
MODERATOR CONTRACT (worker agents)

- Read docs/generated/aggressive_stage_execution_readiness.json first (includes phase0_deploy + pillar map).
- Read docs/generated/orchestrator_gap_burndown.json for open GAP-* rows assigned to you.
- Do NOT recreate audits that already exist under docs/generated/; extend or supersede with dated section.
- Max report: 40 lines in A–L (Stage 9: A–U), then REPORT BACK TO ORCHESTRATOR footer.
- READY — REPO SCOPE only if stage checklist + pillar DoD + verifiers green.
- FAILURE = exact blocker; no 99%.
- SOT: return "SOT draft: <verdict>" only; Moderator commits §11.4 after gate rerun.
- Windows: python scripts/run_sqlite_memory_tests.py <labels>
- UI fix order: token → meta → theme JS → shell → component
- Claim path prefix in autonomous log before parallel waves to avoid merge collisions.
- Do not stop at "pass complete" if your stage still has open repo-contained gaps in gap burndown.
```

---

## Pillar paste bundles (when assigned)

| Pillar | Agents | Key gates |
|--------|--------|-----------|
| P1 Design tokens | A3, A8 | `scan_inline_style_off_token` 0, `scan_off_token_colors` 0 |
| P2 a11y | A8 | extend `a11y-axe.yml` to manager routes |
| P3 Multi-tenant | A2, A4 | `scan_tenant_queryset_safety` 0, penetration tests |
| P4 Workflows | A6, A9 | workflow loop, webhook idempotency |
| P5 FinTech | A5 | `scan_money_float` 0 |
| P6 DevOps | A0, A1, MOD | `render_predeploy.sh`, migration guard |
| P7 Security | A1, A2 | `security_exception_register`, OIDC/SAML/GDPR |

Full pillar prompts: [`pillar-prompts-01-07.md`](pillar-prompts-01-07.md)

---

## Dependency order (do not skip)

```text
Phase 0 → Stage 0 → Stage 1 → Stage 2 → Stage 3
→ Stage 4 → (5,6 parallel) → Stage 7 → Stage 8 → Stage 9 → Stage 10
→ CTO synthesis → Moderator final cert
```

