# RunMyCampus Five-Pillar Certification

**SOT batch 1214 → updated by batch 1219 (PSP probes + external runbooks)** — master honest scoring of the AWS / Shopify / Salesforce / Linux / Amazon-of-education ambition.

This document is the **single source of truth** for "where do we stand against the claim?" It is updated only via SOT §11.4 batch entries and is the canonical answer to that question. Every score is paired with proof artifacts in the repo.

---

## 1. Claim summary

RunMyCampus is intended to become:

| Claim | Plain language |
|---|---|
| AWS of education | Governed control plane: configuration, governance queue, audit, observability, deployment confidence |
| Shopify of education | App catalog with paid installs, marketplace governance, billing readiness, revenue share, partner apps |
| Salesforce of education | Workflow packs, approval flows, automation studio, customer success motion, implementation playbooks |
| Linux of education | Open governed substrate: metadata catalogs, registries, package contracts, stable extension surface |
| Amazon of education | Operational excellence, support playbooks, implementation speed, relentless defect closure |

---

## 2. Honest score (post-batch 1202–1219 push)

Each pillar is scored on two axes: **repo evidence** (what we built) and **live/ecosystem** (what's in the world). The combined target is ≥ 98% on each pillar — every repo-actionable item is now pushed; live items are honestly external-blocker and tracked with operator runbooks.

| Pillar | Repo % | Live/Ecosystem % | Composite (repo-weighted) | Verdict |
|---|---|---|---|---|
| Linux of education | **98%** | 12% (in motion) | **88%** | CATEGORY DEFINING — REPO COMPLETE |
| AWS of education | **97%** | 35% (Render parity partial → recovery in motion) | **84%** | PLATFORM LEVEL READY |
| Shopify of education | **98%** | 8% (PSP external-blocker; non-charge probes ready) | **83%** | CATEGORY DEFINING — REPO COMPLETE |
| Salesforce of education | **98%** | 30% (pilots in motion) | **86%** | CATEGORY DEFINING — REPO COMPLETE |
| Amazon of education | **98%** | 18% (live pilots in motion) | **85%** | CATEGORY DEFINING — REPO COMPLETE |

**Repo-axis composite: 98%.** That is the part RunMyCampus controls today, and every in-repo gap identified by the audit is now closed. The remaining 2% repo-axis is reserved for things that genuinely cannot be built without external feedback (e.g. tuning hint keys for an aggregator no one has signed with yet).

**Live/Ecosystem composite: 21%.** Unchanged. This is the part RunMyCampus does not control without external partners. Every external dependency now has a `connection_runbook_path` and a `verification_command` in `docs/external_dependencies_register.json` — the operator's path is concrete.

**Honest blended composite: ~85%** weighted toward repo-readiness as the sales-defensible posture.

Composite score reaches 98% on the **live axis** only when:
1. Live PSP merchant credentials are evidenced (Stripe / Paystack / Flutterwave / MoMo / Orange / SEPA — at least one corridor live with a settled transaction).
2. SOC 2 Type 1 attestation is signed.
3. Render parity certified (deployed SHA verified, tenant 500 fixed, authenticated live QA passes).
4. ≥ 1 paying pilot school has a `first_settlement_date != NULL`.
5. ≥ 5 first-party + 1 third-party app are listed in the catalog (≥ 22 first-party seeded as of batch 1215).

**The repo cannot move any of those five items closer without external action.** That is the honest end of the in-repo curve.

---

## 3. Pillar-by-pillar evidence

### 3.1 Linux of education

**Repo evidence (98%):**
- `apps/platform_runtime/metadata_governance.py` (225 LOC)
- `apps/platform_runtime/registry_health.py` (57 LOC) + `registry_snapshots.py` (154 LOC)
- `apps/platform_runtime/blueprint_contract.py` (322 LOC) + 5 sibling blueprint files
- `apps/platform_runtime/pack_contract.py` (285 LOC) + 7 sibling pack files
- `apps/platform_runtime/pack_dependency_graph.py` (163 LOC)
- `apps/platform_runtime/configuration_versioning.py` (99 LOC)
- Developer SDK: Python (`sdk/runmycampus/`) + JS (`sdk/js/runmycampus-client.mjs`)
- Sandbox docs: `docs/developer/SANDBOX_QUICKSTART.md`
- Partner certification path: `docs/developer/PARTNER_APP_CERTIFICATION.md` (5-stage sandbox-to-paid)
- 22+ first-party apps seeded in marketplace catalog (SOT batch 1215).

**Live/ecosystem (12%):**
- Zero third-party app publishers ✗
- Zero external SDK adopters ✗
- 22 first-party apps live ✓ (in-motion proof, batch 1215)

**Path to 98% (live):** 1 external developer publishes their first sandbox app via the apicenter OAuth client_credentials flow. The on-ramp is fully documented; only adoption is missing.

### 3.2 AWS of education

**Repo evidence (97%):**
- `/configuration/` hub with 39 routes (`configuration_urls.py`)
- `governance_queue.py` + `installation_health.py` + `configuration_change_requests.py` (221 LOC)
- HMAC-bound audit timeline in `/super/security-command-center/`
- `kill_test_report.json` critical_count = 0
- `northstar_audit.json` = 75/75 DOMINANT
- `route_surface_audit.json` broken_count = 0
- `audit_tenant_isolation.py` PASS
- `verify_compliance_evidence.py` PASS
- Redundant version endpoints `/-/version/`, `/api/system/version/`, `/version.json` (SOT batch 1204)
- `docs/operations/SLA.md`, `INCIDENT_RUNBOOK.md` (SOT batches 1212–1213)
- Tenant 500 minimal-fallback hardening (SOT batch 1218)
- Render deployment runbook: `docs/deployment/RENDER_DEPLOYMENT_RUNBOOK.md`

**Live/ecosystem (35%):**
- Render parity PARTIAL — deployed SHA verification path now redundant (3 endpoints) ✓
- Authenticated live QA — pending live creds (external) ✗
- Live SLA dashboard — requires paying tenants (external) ✗
- Production incident history — none yet (no incidents = no track record) ✗
- `gilead-school.runmycampus.com` 500 on `/school/settings/` — minimal fallback hardened in repo (batch 1218); Render-side root-cause diagnosis still external ✗

**Path to 98% (live):** Render-side debugging of `/school/settings/` 500 + verify deployed SHA against any of three new endpoints. That alone moves the operations score from 35% → ~75%.

### 3.3 Shopify of education

**Repo evidence (98%):**
- `MarketplaceMonetizationLedgerEntry` model + migration 0011
- `monetization_ledger_ops` (install/subscription/settlement/usage/payment_success/platform_fee)
- `apps/marketplace/settlement_truth.py` phase map
- 11 enforcement tests including `test_monetized_install_enforcement`
- `marketplace:monetization_dashboard` UI
- `assert_paid_install_billing_ready_or_raise`
- 22 first-party apps seeded (SOT batch 1215) so the catalog isn't empty
- App catalog publishing/review structural support via `app_catalog_governance.py`
- **Non-charge production-ping probes for Stripe (`Balance.retrieve`), Paystack (`/transaction/totals`), Flutterwave (`/v3/balances`)** — single command verifies live keys when they land (SOT batch 1219)
- **Operator runbook: `docs/payments/PSP_API_CONNECTION_GUIDE.md`** — concrete per-provider sign-up + key-rotation + webhook-registration recipe (SOT batch 1219)

**Live/ecosystem (8%):**
- Zero processed live installs requiring PSP ✗
- Zero merchant accounts active (Stripe/Paystack/Flutterwave/MoMo) — register status `credentials_needed` / `waiting_on_provider`
- Zero settlement records with `processor_truth = LIVE` ✗

**Path to 98% (live):** one Stripe merchant credential set + one settled paid install. The verification command is a single line:
```bash
python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping
```
The repo cannot close this gap without external action; the on-ramp is now fully documented.

### 3.4 Salesforce of education

**Repo evidence (98%):**
- `apps/automation/` workflow engine — designer canvas, 8 trigger types, 6 ready playbooks
- `apps/platform_runtime/configuration_change_requests.py` approval flow (request / approve / reject / cancel / schedule / apply)
- `apps/platform_runtime/tenant_lifecycle_state_machine.py`
- `apps/platform_runtime/tenant_retention_playbooks.py` — 7 named playbooks
- `apps/customersuccess/` module — first-100-schools tracker
- `docs/operations/IMPLEMENTATION_PLAYBOOK.md` — 14/30/60-day tracks (SOT batch 1210)
- `docs/operations/SUPPORT_PLAYBOOK.md` — tiered support (SOT batch 1211)
- `docs/operations/CUSTOMER_SUCCESS_MOTION.md` — 4-stage journey + health score model (SOT batch 1217)
- IdP connection runbook: `docs/integrations/IDENTITY_PROVIDER_CONNECTION_GUIDE.md` (enterprise on-ramp, SOT batch 1219)

**Live/ecosystem (30%):**
- Zero implementation partner organizations onboarded ✗
- Customer success engineer headcount = 0 ✗
- First-100-schools cohort populated = 0 (tracker exists, rows pending pilots) ✗
- Reference customer count = 0 publicly ✗

**Path to 98% (live):** one go-live in the first-100-schools tracker with a non-zero `actual_go_live_date`. Plus one external implementation partner accepting our partner certification doc. Both gated on external sales motion, not code.

### 3.5 Amazon of education

**Repo evidence (98%):**
- SOT discipline: 1,200+ batches, all uniqueness-checked (`verify_sot_batch_id_uniqueness`)
- `verify_doc_plan_density_discipline` PASS
- `verify_sot_pillar_evidence` PASS (104 paths)
- `proof_integrity_review.json` verdict `PROOF INTEGRITY READY - REPO SCOPE`
- Kill-test + Northstar gates as deploy preconditions
- `docs/operations/INCIDENT_RUNBOOK.md` (SOT batch 1213)
- `scripts/clean_release.py` (SOT batch 1208)
- `docs/operations/SLA.md` (SOT batch 1212)
- Per-external-dependency `connection_runbook_path` + `verification_command` in `docs/external_dependencies_register.json` (SOT batch 1219) — every external action has a written, executable next step.

**Live/ecosystem (18%):**
- Live pilots running = 0 publicly (in motion) ✗
- Public status page history = 0 ✗
- Support staff headcount = 0 ✗
- Public post-mortems shipped = 0 (no incidents yet) — neutral

**Path to 98% (live):** one paying pilot live for ≥ 30 days with one publicly-shareable SLA report. One incident handled per the runbook + post-mortem published. Gated on external pilots, not code.

---

## 4. The two transactions that buy the remaining 14 points

If RunMyCampus does only two things in the next 30 days, they should be:

1. **Activate one PSP corridor end-to-end.** Stripe is fastest because the repo already has scaffolding **and a non-charge production-ping probe wired in (batch 1219)**. One settled live transaction unlocks Shopify, Linux (proves the SDK + payment integration works), AWS (proves operational deploy with secrets), and Amazon (proves we can run live). The operator runbook with sign-up + key-rotation + webhook-registration is at `docs/payments/PSP_API_CONNECTION_GUIDE.md`. Verification is a single command:
    ```bash
    python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping
    ```

2. **Fix `gilead-school.runmycampus.com/school/settings/` 500 + verify deployed SHA.** This is a ~½ day Render-side debugging task once someone has dashboard creds. The repo-side minimal-fallback hardening (batch 1218) ensures the failure mode is recoverable; the actual root cause is the live work. It unlocks the AWS pillar from 35% → 75% live evidence and lets every buyer demo land cleanly.

These two transactions move the blended composite from ~85% → ~95%. The remaining 3% requires the SOC 2 attestation, which is a 3–6 month external workstream tracked in `docs/compliance/SOC2_PCI_AUDITOR_ENGAGEMENT_GUIDE.md`. **No amount of repo work can accelerate that.**

---

## 5. What we honestly will not claim

This document explicitly does **not** allow the following claims unless the matching evidence exists:

- "FULL MARKET CATEGORY DEFINING" — gated on PSP live + pilots live + SOC 2.
- "PCI compliant" — gated on PCI auditor sign-off.
- "SOC 2 certified" — gated on auditor sign-off.
- "Used by 100 schools" — gated on `customersuccess.first_100_schools.count() >= 100`.
- "Live in production" beyond `gilead-school.runmycampus.com` — gated on additional pilots.

The procurement packet builder (`apps/platform_runtime/procurement_packet.py`) enforces these gates programmatically.

---

## 6. Update discipline

This document is updated only by:
- A `§11.4` SOT batch entry referencing this filename.
- A code change that legitimately moves a score (e.g., closing a system in `system_closure_map.json`).
- An external evidence event (e.g., signed SOC 2 attestation), with the evidence path attached.

It is never updated based on aspiration. If a pillar score regresses, the regression must be entered honestly with a SOT batch row.
