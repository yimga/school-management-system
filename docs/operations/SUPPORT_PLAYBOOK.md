# RunMyCampus Support Playbook

**SOT batch 1211** — Amazon-pillar push.
**Audience:** support engineer + on-call + customer success.
**Promise:** every ticket has a known owner, a response SLA, an escalation path, and a closure audit.

---

## 1. Tiered support model

| Tier | Audience | Response SLA | Resolution SLA | Channels |
|---|---|---|---|---|
| **T0 self-serve** | Self-serve track schools | n/a | n/a | In-product help, runbook, knowledge base |
| **T1 standard** | All paying schools | 1 business day | 5 business days for non-critical | Email, in-product ticket |
| **T2 priority** | Guided / assisted enterprise | 4 business hours | 2 business days | Slack-shared channel + ticketing |
| **T3 critical** | Production-down or data-loss risk | 30 minutes (24/7) | Best-effort, communicated hourly | On-call phone bridge + war room |

External-blocker reminder: the SLA does NOT cover external dependencies (PSP outage, bank settlement, IdP outage). Those are tracked separately and communicated honestly.

---

## 2. Severity classification

| Severity | Definition | SLA |
|---|---|---|
| **SEV-1** | Production-down. ≥ 1 tenant cannot serve users. Data integrity at risk. | T3 |
| **SEV-2** | Major feature broken for ≥ 1 tenant; workaround is painful. | T2 |
| **SEV-3** | Minor feature broken; workaround easy. | T1 |
| **SEV-4** | Cosmetic / documentation / polish. | T1 |

SEV-1 examples that are RunMyCampus-side (and therefore covered): authentication broken, role-call cannot be saved, tenant isolation suspected breach, kill-test critical_count > 0 in production.

SEV-1 examples that are external-blocker (NOT covered, but communicated): Stripe outage, sponsor bank settlement delay, regional PSP gateway downtime, customer's IdP unavailable.

---

## 3. Escalation matrix

```
T1 ticket → support engineer
   ↓ (if not resolved within SLA, OR SEV ≥ 2)
T2 → senior support engineer + customer success contact
   ↓ (if not resolved, OR SEV = 1)
T3 → on-call platform engineer + incident commander
   ↓ (if data integrity / security)
SEV-0 → CTO + security lead + legal lead
```

Every escalation step writes an AuditLog row with actor, timestamp, severity at escalation, and reason.

---

## 4. Standard runbooks (10 most common tickets)

### 4.1 "I cannot log in"
1. Confirm tenant subdomain is correct.
2. Check `tenant_lifecycle_state_machine` for tenant status (suspended? dormant?).
3. Check IdP/SSO health if enterprise.
4. Reset via `/authentication/password-reset/`.
5. If still stuck, escalate to T2 with screenshot + tenant subdomain + role.

### 4.2 "Imports failed validation"
1. Open `/school/setup/imports/`.
2. Read data quality meter score and quarantine list.
3. Fix invalid rows in source data.
4. Re-run preview before apply.
5. If field mapping is wrong, escalate to T2 — implementation engineer will tune the mapping.

### 4.3 "Payment did not go through"
1. Check `/school/money/payment-readiness/`.
2. If PSP says "external_required", **this is expected** — live PSP is not yet in repo scope. Use manual receipt + reconciliation flow.
3. If PSP credentials are configured and gateway fails, run `manage.py check_payment_gateways --mode=metadata` first, then `--mode=production_ping`.
4. Capture transaction ID, tenant, amount, gateway → escalate to T2.

### 4.4 "Roll-call did not save (offline)"
1. Open `/school/offline/`.
2. Check sync queue for the action.
3. If conflict: use the conflict UI (`keep_mine` / `use_latest` / `review_manual`).
4. Verify resolution_audits row was written.
5. If stuck > 24h, escalate to T2 with offline_sync_dashboard screenshot.

### 4.5 "Workflow did not fire"
1. Open `/configuration/workflow-packs/` or tenant equivalent.
2. Check workflow run logs (`workflow_run_logs` governed dataset).
3. Check trigger catalog: which trigger should have fired?
4. Run `simulate_pack` on the affected pack.
5. If trigger fired but no action, escalate to T2 with the run log.

### 4.6 "Report exports show wrong totals"
1. Open governed analytics builder.
2. Re-run report with explicit tenant scope.
3. Compare to AuditLog export rows.
4. If totals diverge, escalate to T2 — likely a tenant filter regression; collect dataset name and parameters.

### 4.7 "Domain event delivery failed"
1. Open `/domain-events/dlq/`.
2. Inspect failed delivery: status, last_error, attempt_count.
3. Use bulk remediation (retry selected / retry all / resolve / ignore + reason).
4. If retries exhaust, the webhook subscriber is at fault — communicate to subscriber owner.

### 4.8 "Marketplace install blocked"
1. Confirm install impact + scope review was acknowledged.
2. Check `marketplace_settlement_truth` for settlement_blocked_detail.
3. If "external PSP required", that is honest — install can proceed with a sandbox app or a free SKU.
4. For paid SKUs without PSP, escalate to T2 — settlement is external-blocker.

### 4.9 "Audit timeline cannot be exported"
1. Verify role permission on the export action.
2. Check AuditLog HMAC integrity tokens — if any row fails verification, halt export and escalate SEV-1.
3. Otherwise, retry from `/super/security-command-center/export-timeline/`.

### 4.10 "Render is slow / 5xx errors"
1. Check `/-/version/` and `/version.json` — does deployed SHA match expected?
2. Check public health endpoint.
3. Open Render dashboard logs (operator-only).
4. If a tenant is unreachable AND the deployed SHA is older than 1 hour from main, the deploy may be incomplete — escalate to T3.

---

## 5. Defect closure & continuous improvement

Every closed ticket writes:
- Resolution category: code-fix | configuration-fix | tenant-data-fix | external-blocker | duplicate | not-a-bug
- Time-to-first-response
- Time-to-resolution
- Linked SOT batch (if a code fix shipped)

Weekly support review:
- Top 5 ticket categories
- Mean / p50 / p99 time-to-resolution per tier
- External-blocker tickets — track which dependency keeps generating tickets and prioritise activation.

---

## 6. Communication discipline

We never:
- Promise certifications we don't have.
- Promise live PSP we haven't onboarded.
- Promise SLAs we cannot meet.
- Communicate about another tenant to a tenant that does not own those records.

We always:
- Tell schools when an issue is on our side.
- Tell schools when an issue is external-blocker and what the next step is.
- Write an AuditLog row when we communicate with a school about an incident.
- Cite proof artifact paths instead of marketing claims.
