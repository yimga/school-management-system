# Procurement Packet Guide

How to assemble and send the buyer-grade procurement packet for an enterprise prospect.

Cross-reference: `apps/platform_runtime/procurement_packet.py` (the builder), `docs/compliance/ENTERPRISE_REVIEW_CHECKLIST.md`, `docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md`.

## The builder

```bash
python -c "import json; from apps.platform_runtime.procurement_packet import build_procurement_packet; print(json.dumps(build_procurement_packet(), indent=2, default=str))" > /tmp/packet.json
```

The packet bundles:
- Security / data-handling / tenant-isolation / offline / audit posture
- Proof summaries from `docs/generated/` (kill_test, northstar, route_surface, system_closure_map, category_scope_review, external_dependencies_register, render_parity, apple_class_authenticated_browser, proof_integrity)
- Programmatic five-pillar honest scoring with explicit `external_blockers` per pillar
- Locked honesty gates: `psp_live_ready_claim_allowed` requires both `psp_live_verified` AND `psp_evidence_path`. `full_market_category_defining_claim_allowed` additionally requires `pilots_live` AND `SOC 2 certified` in `certifications`.

## What to send to a buyer

| Document | Purpose | Source |
|---|---|---|
| Procurement packet JSON | Single-shot architecture + posture summary | `build_procurement_packet()` |
| Five-pillar certification | Honest scoring against AWS/Shopify/Salesforce/Linux/Amazon claim | `docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md` |
| Control matrix | SOC 2 control to repo evidence mapping | `docs/compliance/CONTROL_MATRIX.md` |
| External dependencies register | What is repo-side vs external | `docs/external_dependencies_register.json` |
| SLA spec | Uptime targets, response times, RPO/RTO | `docs/operations/SLA.md` |
| Incident runbook | SEV-1 response posture | `docs/operations/INCIDENT_RUNBOOK.md` |
| Implementation playbook | 14/30/60-day onboarding | `docs/operations/IMPLEMENTATION_PLAYBOOK.md` |
| Support playbook | Tiered support model | `docs/operations/SUPPORT_PLAYBOOK.md` |
| Customer success motion | Pilot-to-renewal motion | `docs/operations/CUSTOMER_SUCCESS_MOTION.md` |

## Honesty gates the builder enforces

Before claiming any of these, the builder requires the matching label:

- **"FULL MARKET CATEGORY DEFINING"** → `psp_live_verified=True` AND `pilots_live=True` AND `SOC 2 certified` in certifications.
- **"PCI compliant"** → PCI auditor sign-off (label must be present).
- **"SOC 2 certified"** → SOC 2 auditor sign-off (label must be present).
- **"100 schools"** → `customersuccess.first_100_schools.count() >= 100` (queried at packet build time).

Without the label, the corresponding claim string is replaced with the in-progress evidence path. The buyer sees what is true, not what we want to be true.

## How to update the packet

Update happens automatically — the builder reads from current state every time. If a piece of state is stale (e.g. `kill_test_report.json` is from last month), regenerate it first:

```bash
python scripts/run_kill_test.py
python scripts/run_northstar_audit.py
python scripts/audit_route_surface.py
python scripts/audit_security_surface.py
python scripts/audit_tenant_isolation.py
python scripts/generate_external_dependencies_register.py
python scripts/generate_system_closure_map.py --write
```

Then rebuild the packet.

## What this guide does NOT cover

- MSA / DPA template negotiation — commercial.
- Customer-specific NDA before sending the packet — sales process.
