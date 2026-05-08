# RunMyCampus Incident Runbook

**SOT batch 1213** — AWS/Amazon-pillar push (operations score).
**Audience:** on-call platform engineer, incident commander, customer-comms lead.
**Promise:** every SEV-1 incident has a known role taxonomy, a clear runbook, an audited post-mortem, and a public communication.

---

## 1. Roles during a SEV-1

| Role | Responsibility |
|---|---|
| **Incident commander (IC)** | Owns the incident timeline, decides priorities, calls escalations, runs the bridge. |
| **Comms lead** | Writes status-page updates, customer-facing tweets (if any), and direct emails to affected tenants. Never speculates. |
| **Operations lead** | Hands on the system: deploys, rollbacks, DB ops, rate limiting. |
| **Scribe** | Writes the timeline in real time. Captures every decision with a timestamp. |
| **Customer success contact** | Liaison with affected paying tenants. |

For SEV-2 the IC and operations lead can be the same person. SEV-1 always has at least three distinct people.

---

## 2. The first 15 minutes (SEV-1)

1. **Acknowledge** — page noted within 30 minutes. IC says "I have it."
2. **Establish bridge** — phone bridge or chat war-room created.
3. **Snapshot** — record the time, the symptom, the affected tenant(s), the deployed SHA from `/-/version/` or `/api/system/version/`.
4. **Stop the bleeding** — if a recent deploy caused it, prepare a rollback. Don't deploy a fix yet.
5. **Comms cycle** — first public update within 15 minutes: "we are aware, we are investigating." Honest. No estimates yet.
6. **Decide blast radius** — single tenant, multi-tenant, or platform-wide? Tenant-isolation guard means most incidents are blast-bounded.

---

## 3. Common SEV-1 runbooks

### 3.1 "Tenant subdomain returns 500"

(Reference incident: `gilead-school.runmycampus.com/school/settings/` returning 500 on live, observed 2026-05-07.)

1. Confirm reproducibility: hit the URL anonymously and authenticated.
2. Hit `/-/version/` on the affected host — confirm the deployed SHA matches expected.
3. Check Render logs for the worker that served the failing request.
4. Look for recent migrations that may have left tenant data in a transitional state.
5. Run `python manage.py check --settings=config.settings` against the tenant DB.
6. If the cause is a recent deploy, **roll back** to the previous known-good SHA.
7. If the cause is a tenant-data drift, fence the tenant: set `tenant.status = 'maintenance'` temporarily; communicate to the school admin; resolve via guided data-fix.
8. Write an AuditLog row at every action.
9. Post-mortem within 5 business days; SOT batch entry citing the root cause + the regression test added.

### 3.2 "Render parity outage — deployed SHA cannot be verified"

1. Hit `/-/version/`, `/api/system/version/`, `/version.json` — at least one should return JSON.
2. If all three return marketing HTML, a CDN or static layer is intercepting. Check Render service config for a recently-added rewrite rule.
3. If the deploy itself is incomplete (worker hasn't rolled), wait one full deploy cycle and recheck.
4. Communicate to procurement reviewers waiting on parity proof: "our verification endpoint is currently routed incorrectly; we are restoring access."

### 3.3 "Audit-log HMAC verification fails"

This is **always SEV-1** and may be SEV-0 if it implicates tampering.

1. Halt all export-timeline operations.
2. Snapshot the AuditLog rows for forensics.
3. Compare HMAC keys in deployment secrets against expected.
4. If keys rotated unexpectedly, restore from the previous known-good key.
5. If keys did not rotate but tokens still fail, escalate to security lead + CTO + legal counsel.
6. Customer comms: tell affected tenants, don't speculate on cause.

### 3.4 "Tenant isolation suspected breach"

SEV-0. Treat as tampering until proven otherwise.

1. Halt cross-tenant operations.
2. Run `audit_tenant_isolation`.
3. Snapshot affected DB rows with timestamps.
4. Notify CTO + security lead + legal lead within 30 minutes.
5. Plan customer comms with legal review before publishing.

### 3.5 "Webhook delivery DLQ overflow"

Usually SEV-2. Becomes SEV-1 if it persists > 4 hours and starves downstream tenant workflows.

1. Open `/domain-events/dlq/`.
2. Inspect failure cluster — single subscriber? Multiple?
3. If single subscriber is down, communicate to subscriber owner and pause delivery.
4. Use bulk remediation: retry-selected with backoff, or resolve-with-reason.
5. Capture the count + reason in EventSystemRemediationAudit.

### 3.6 "Kill-test critical_count > 0 in production"

This blocks deploys until resolved. Treat as SEV-1.

1. Read `docs/generated/kill_test_report.json`.
2. The critical-list names the failure path.
3. Roll back to last known kill-test PASS deploy.
4. Open a config-change-request to fix; ship via normal change governance.

---

## 4. Timeline discipline

The scribe writes a real-time timeline like:

```
13:42 IC: declared SEV-1; symptom = tenant settings 500
13:43 Ops: deployed SHA 0b4ee86 — matches main
13:46 Comms: first public update posted
13:51 Ops: rollback to SHA 7f12a3c initiated
13:58 Ops: rollback complete; symptom resolved
14:05 Comms: resolved update posted
14:30 IC: post-mortem scheduled for 2026-05-12
```

The timeline is appended to the AuditLog at incident close.

---

## 5. Post-mortem template

Every SEV-1 produces a post-mortem within 5 business days, in `docs/post_mortems/YYYY-MM-DD-<slug>.md`:

1. **Summary** (1 paragraph, blameless).
2. **Timeline** (from scribe).
3. **Root cause** (in plain English).
4. **Contributing factors** (process, code, infrastructure).
5. **What went well.**
6. **What went badly.**
7. **Action items** (each with an owner and a SOT batch number for the code fix).
8. **Customer impact summary** (which tenants, what duration, what manual mitigations).

Post-mortems are linked from the SOT and from the procurement packet.

---

## 6. Honest carve-outs

We never:
- Hide an incident.
- Speculate on cause in public comms before forensics.
- Promise a fix timeline before we know.
- Discuss another tenant's incident with a tenant that isn't affected.

We always:
- Communicate scope honestly.
- Distinguish "RunMyCampus-side" from "external-blocker" (PSP outage, IdP outage, bank delay).
- Update the public status page within 15 minutes of acknowledgement.
- Tag the incident in the SOT once resolved.
