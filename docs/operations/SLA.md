# RunMyCampus Service Level Agreement (in-repo SOT)

**SOT batch 1212** — AWS-pillar push (operations score).
**Audience:** prospective buyer, procurement reviewer, operator on-call.

This is the **in-repo source of truth** for the SLA. It is honest by default — it states what we commit, what we do not commit, and what is external-blocker. Live SLA dashboards become operationally meaningful only once there are paying tenants — until then this document is a contract template.

---

## 1. Uptime commitment

| Surface | Target | Measurement window | Penalty (credit) |
|---|---|---|---|
| Tenant authenticated workspace | 99.5% | Calendar month | 1 day credit per 0.1% miss, capped at 30 days |
| Platform configuration center (`/configuration/`, `/super/`) | 99.5% | Calendar month | 1 day credit per 0.1% miss |
| Public marketing pages (`/`, `/pricing/`, `/trust/`, `/demo/`) | 99.0% | Calendar month | None — informational |
| Webhook delivery latency | p99 < 30s | Rolling 24h | Replay queued + automatic retry policy |
| Offline sync acceptance | 100% | Per submission | Conflict UI is treated as success — capture is durable |
| Audit-log integrity (HMAC verified) | 100% | Always | Any failure is SEV-1 |

External dependencies are excluded from the uptime number. Stripe / Paystack / Flutterwave / MoMo / Orange / SEPA / sponsor-bank / IdP / SMS / email outages are tracked but do not count against RunMyCampus uptime.

---

## 2. Response times

(Already defined in `SUPPORT_PLAYBOOK.md` §1; restated here for completeness.)

| Severity | First response | Resolution target |
|---|---|---|
| SEV-1 | 30 min, 24/7 | Best effort, hourly updates |
| SEV-2 | 4 business hours | 2 business days |
| SEV-3 | 1 business day | 5 business days |
| SEV-4 | 1 business day | Roadmap / next sprint |

---

## 3. Data durability and recovery

- **RPO (recovery point objective):** ≤ 1 hour for tenant data once production hosting is contracted.
- **RTO (recovery time objective):** ≤ 4 hours.
- Tenant exports available on demand via governed analytics + compliance exports.
- Audit-log HMAC integrity continuously verified by `verify_compliance_evidence`.

External-blocker note: RPO/RTO commitments are conditional on the cloud provider contract being signed — see `external_dependencies_register.json` row `cloud_dns_placeholder` (currently `verified_live`).

---

## 4. Maintenance windows

- Scheduled maintenance is announced ≥ 72 hours in advance via email + in-product banner.
- Default maintenance window: Sundays 02:00–04:00 in the tenant's primary timezone.
- Zero-downtime deploys are the default; multi-tenant rolling deploys via Render.
- Schema migrations run with `--noinput --keepdb` semantics where possible; otherwise a heads-up is published.

---

## 5. Security commitments

- Tenant isolation is mechanically verified (`audit_tenant_isolation`, broken_count tracked).
- Sensitive actions are HMAC-bound in the audit timeline.
- Impersonation requires reason capture and creates an AuditLog row (peer + actor).
- No tenant data is shared cross-tenant. No cross-tenant queries are issued by application code.
- Vulnerability reports go to `security@runmycampus.com` (external contact).
- SOC 2 Type 1 attestation is **in motion**, not certified — `external_dependencies_register.json` row `soc2_pci_placeholder` status `in_progress`.

---

## 6. Privacy commitments

- Tenant-scoped data paths only.
- Operator access requires impersonation flow with reason; never silent.
- Subprocessors disclosed in the procurement packet.
- Data localization claims are deployment-conditional — see register row `data_localization_placeholder`.

---

## 7. Termination & exit

- 30-day notice (self-serve), 90-day notice (guided), 180-day notice (assisted enterprise).
- Tenant data export bundle on termination (governed analytics + compliance pack).
- 90-day archive retention after termination, then secure delete with audit certificate.

---

## 8. Honest carve-outs

These are explicitly **not** committed in this repo SLA until externally evidenced:

- Live PSP availability (depends on Stripe/Paystack/Flutterwave/MoMo/Orange status).
- Settlement timing (depends on sponsor bank).
- Custom SLA terms negotiated in a Master Services Agreement.
- Performance under load profiles RunMyCampus has not yet measured at scale.

---

## 9. Change history

This document changes only via SOT §11.4 batch entries. Prior versions remain in git history.
