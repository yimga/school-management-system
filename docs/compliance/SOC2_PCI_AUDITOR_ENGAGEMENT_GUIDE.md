# SOC 2 / PCI Auditor Engagement Guide

The repo contains the *technical evidence* — control documentation, audit log primitives, tenant isolation tests, evidence ledger generators. The *attestation* is an external workstream that no amount of code can replace. This guide is the operator's path from "code is ready" to "auditor signs the report".

Cross-reference: `docs/compliance/CONTROL_MATRIX.md`, `docs/compliance/SOC2_READINESS_MAP.md`, `docs/compliance/policies/`, `docs/generated/compliance_evidence_ledger.{json,md}`.

## Choose an auditor track

| Auditor / Tool | Best for | Typical cost | Time-to-Type-1 |
|---|---|---|---|
| **Vanta** | First-time SOC 2 (Type 1 + 2) | $15k–35k/yr | 8–14 weeks |
| **Drata** | Engineering-heavy orgs | $15k–40k/yr | 8–14 weeks |
| **SecureFrame** | Mid-market with custom needs | $15k–35k/yr | 8–14 weeks |
| **Direct CPA firm** (Schellman / BDO / Prescient Assurance) | Want auditor relationship without GRC tool | $30k–60k engagement | 12–24 weeks |

The GRC tools (Vanta / Drata / SecureFrame) include a marketplace of pre-vetted auditors. For first SOC 2, this is usually the right pick.

## SOC 2 Type 1 vs Type 2

- **Type 1:** point-in-time attestation that controls are *designed* properly. ~3 months. Required as a stepping stone.
- **Type 2:** observation period (typically 6 months) that controls are *operating effectively*. ~9 months from start. Required for most enterprise sales.

Plan: Type 1 in 2026 Q3 → Type 2 in 2027 Q1.

## Day-zero checklist (do these before kicking off)

- [ ] Decide trust services criteria scope: minimum is **Security**; recommended for K-12 SaaS is **Security + Availability + Confidentiality + Privacy**.
- [ ] Confirm legal entity and audit period (organization legal name, fiscal year alignment).
- [ ] Designate **Security Officer** (signs the management assertion).
- [ ] Inventory cloud accounts in scope (Render, AWS if any, payment processors).
- [ ] Inventory data classifications (student PII, health, financial — see DPA template).
- [ ] Run `python scripts/generate_observability_ledger.py` and `python scripts/build_phase8_security_ledger.py` to refresh evidence ledgers.

## Repo evidence already in place

| SOC 2 Common Criteria | Repo evidence |
|---|---|
| CC1 Control environment | `docs/compliance/CONTROL_MATRIX.md`, `docs/compliance/policies/` |
| CC2 Communication | `docs/operations/INCIDENT_RUNBOOK.md`, `docs/operations/SUPPORT_PLAYBOOK.md` |
| CC3 Risk assessment | `docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md`, `docs/external_dependencies_register.json` |
| CC4 Monitoring | `apps/observability/`, `docs/generated/observability_ledger.{json,md}` |
| CC5 Control activities | `scripts/audit_*.py`, `scripts/verify_*.py` (40+ verifiers) |
| CC6 Logical access | `audit_security_surface.py`, MFA, SCIM, role/permission system |
| CC7 System operations | `kill_test_report.json`, `northstar_audit.json`, `INCIDENT_RUNBOOK.md` |
| CC8 Change management | HMAC-bound audit timeline, `configuration_change_requests.py` |
| CC9 Risk mitigation | `external_dependencies_register.json`, vendor list |
| Availability | `docs/operations/SLA.md`, `audit_route_surface.py` |
| Confidentiality | `audit_tenant_isolation.py`, encryption-at-rest, TLS-in-transit |
| Privacy | DPA template, data retention, deletion runbook |

## PCI

If RunMyCampus never touches card data (the recommended posture — Stripe / Paystack / Flutterwave handle it), scope is **SAQ A**: a self-attestation, not a full audit.

Document the integration as iframe / redirect / hosted-checkout (not direct card capture) and complete the SAQ A questionnaire with the customer's acquirer or PSP.

If a customer requires direct card capture, scope explodes to **SAQ D / Level 1** — multi-month, multi-hundred-thousand-dollar engagement. Do not commit to this without auditor consultation.

## What this guide does NOT cover

- Negotiation with auditors — commercial.
- Customer-specific compliance (HIPAA, FERPA — separate posture per customer).
- ISO 27001 — adjacent but separate audit. Most SOC 2 evidence reuses cleanly.
