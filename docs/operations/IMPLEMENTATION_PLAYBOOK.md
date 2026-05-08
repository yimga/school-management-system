# RunMyCampus Implementation Playbook

**SOT batch 1210** — Salesforce/Amazon-pillar push.
**Audience:** implementation lead + tenant operator + first-100-schools success engineer.
**Promise:** a school can be live on RunMyCampus in 14 days for self-serve, 30 days for guided, 60 days for assisted enterprise. No partial implementations.

---

## 0. Honesty boundary

This playbook is the in-repo source of truth for *implementation process*. It does NOT claim:

- Live PSP merchant onboarding (external — see `docs/generated/external_dependencies_register.json`)
- SOC 2 / ISO 27001 / PCI attestations (external — auditors)
- Sponsor bank / SEPA contracts (external — banking partners)
- Production reference customers at scale (in motion — pilots tracked in `customersuccess`)

When a step requires external evidence we say so explicitly and link the register row.

---

## 1. The three implementation tracks

| Track | Promise | Suitable for | Days | Owner |
|---|---|---|---|---|
| **Self-serve** | School onboards itself with the in-product wizard, blueprint marketplace, and offline-first capture. We respond async to support tickets in 1 business day. | Single-campus schools, ≤ 1,500 students, low integration complexity | 14 | School admin |
| **Guided** | Implementation engineer pairs daily with the school for setup, blueprint apply, pack install, payment readiness, role training, and parent comms. Live walkthrough at day 7 and day 14. | Multi-program schools, 1,500–5,000 students, moderate integration | 30 | RunMyCampus implementation engineer |
| **Assisted enterprise** | Multi-tenant district / network rollout with bespoke blueprint, custom workflow packs, governed change control, and a named customer success engineer. Quarterly business review. | District networks, ≥ 5,000 students, complex regulatory or finance posture | 60 | RunMyCampus customer success engineer + partner |

---

## 2. The 14-day self-serve path (day-by-day)

**Day 1 — Account & tenant boot.** Admin signs up, picks region, language, term cycle. Blueprint preview runs. Tenant lifecycle state machine begins (`tenant_lifecycle_engine`). North Star score initialises.

**Day 2 — Imports & data quality.** Admin uses `/school/setup/imports/` migration center. Field mapping, duplicate warnings, invalid rows, and rollback posture are visible before apply. Data quality meter must hit ≥ 70% before continue.

**Day 3 — Blueprint apply.** Admin selects a blueprint from `/configuration/blueprints/`. Preview → impact → apply with rollback snapshot. Linked packs install in dependency order.

**Day 4 — Roles & permissions.** Default roles seeded by blueprint. Admin reviews `RolePermission` matrix and approves additional staff invites. Apple-class inline-edit fields for tenant display name, support contact, branding.

**Day 5 — Money setup.** Admin configures invoice templates, payment policy, regional rail. **Live PSP requires merchant onboarding outside the repo** — until then, manual receipt + reconciliation flow is wired and audited.

**Day 6 — Workflow packs.** Admin picks 1–2 workflow packs (attendance escalation, fee reminder, parent comms). Pack simulation runs without side effects.

**Day 7 — Apple-class checkpoint.** Admin completes school readiness score ≥ 80%. Apple-class authenticated route smoke runs against tenant. Any axe-serious findings on the tenant subdomain block the next milestone.

**Day 8–10 — Communications + parent portal.** SMS / email integration credentials (or manual fallback). Parent invites batch-sent. Parent portal accessible.

**Day 11–13 — Teacher onboarding.** Teacher dashboards activate. Roll-call, marks-entry, and notes capture (offline-first). Bulk teacher invite + role accept flow.

**Day 14 — Go-live + first-100-schools record.** Tenant is added to `customersuccess` first-100-schools tracker. Go-live AuditLog row written. Procurement packet exported. Northstar audit run against tenant.

**Pause condition:** any kill-test failure or northstar score drop below 70/75 halts go-live until resolved.

---

## 3. The 30-day guided path

Self-serve days 1–14, **plus**:

- **Days 15–17:** Blueprint customisation. Implementation engineer authors a custom blueprint preview/impact/apply for school-specific overrides. Change request flows through `configuration_change_requests`.
- **Days 18–20:** Pack authoring. Implementation engineer + school staff co-author 1–2 custom workflow packs. Pack simulation + dry-run + audit before apply.
- **Days 21–24:** Money + reconciliation. Tenant receipt upload UX, manual reconciliation, payment readiness dashboard. PSP credentials onboarded if available; otherwise external_required label preserved.
- **Days 25–28:** Reporting. Governed analytics builder + saved reports. NL governed-intent assistant configured. Compliance exports tested.
- **Day 29:** Pre-go-live audit — kill-test + northstar + audit_route_surface + audit_security_surface + audit_tenant_isolation against the live tenant subdomain.
- **Day 30:** Go-live + customer success handoff. Tenant transitions to `tenant_lifecycle_state_machine` "live" stage. Quarterly business review scheduled.

---

## 4. The 60-day assisted enterprise path

Guided days 1–30, **plus**:

- **Days 31–35:** Multi-tenant districting. Parent district + child schools provisioned. Cross-tenant policy bundles applied with explicit scope.
- **Days 36–42:** Integration & API center. Webhook subscribers configured. Developer API tokens issued via apicenter OAuth. SDK quickstart sandbox proven by the customer's own developer.
- **Days 43–50:** Compliance evidence. SOC 2 / ISO / GDPR / FERPA / regional packs assembled. Procurement packet (`build_procurement_packet`) exported and shared with district legal.
- **Days 51–56:** Failover & rollback rehearsal. Operator runs `apply` → `rollback` cycle on a non-production tenant; rollback snapshot proves clean. Render-side incident runbook walkthrough.
- **Day 57:** Final pre-go-live audit. All verifiers PASS. Kill-test critical_count = 0. Apple-class authenticated browser cert ≥ 95% pass.
- **Day 58–59:** Pilot week. Limited classes go live; staff run full day; defects logged as configuration change requests.
- **Day 60:** Full district go-live + named customer success engineer assigned. First QBR scheduled at day 90.

---

## 5. The first-100-schools engine

Track status of every school in `apps/customersuccess/` (already wired). Each school carries:

- `cohort_number` (1–100)
- `track` (self_serve | guided | assisted_enterprise)
- `target_go_live_date`
- `actual_go_live_date`
- `north_star_at_go_live`
- `apple_class_axe_findings_at_go_live`
- `first_paid_invoice_date` (NULL until external PSP processes payment)
- `first_settlement_date` (NULL until external bank settles)
- `health_score` (driven by `customer_health` + `tenant_lifecycle_engine`)
- `escalation_history`

The first-100-schools dashboard is the **single most important commercial proof** RunMyCampus will produce. One row of `first_settlement_date != NULL` is worth more than a thousand additional repo batches.

---

## 6. Defect closure discipline

Every defect found during implementation files a configuration change request. The change request must reference:

- Affected route(s)
- Defect severity (critical / high / medium / low)
- Whether it is a **repo-defect** (we fix in code), an **external blocker** (we annotate and wait), or a **configuration miss** (we adjust the tenant blueprint).
- A SOT §11.4 batch row when a code fix lands.

Critical defects pause go-live. High defects must be fixed within 48h. Medium defects can ship into go-live with a tracked next-batch hint. Low defects are deferred to roadmap.

---

## 7. Pause / abort conditions

These halt implementation regardless of track:

1. Kill-test critical_count > 0
2. Northstar score < 70/75
3. Tenant isolation audit fails
4. Render parity verdict is OUTAGE (not PARTIAL — partial is acceptable for self-serve / guided tracks; assisted enterprise must reach CERTIFIED)
5. PSP credentials claimed live but `psp_evidence_path` is missing — packet builder will refuse to claim live readiness.

---

## 8. Linkages

- `docs/operations/SUPPORT_PLAYBOOK.md` — escalation matrix once a school is live.
- `docs/operations/SLA.md` — uptime, response, and resolution commitments.
- `docs/operations/INCIDENT_RUNBOOK.md` — production incident response.
- `docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md` — honest scoring against AWS/Shopify/Salesforce/Linux/Amazon-of-education claim.
- `apps/platform_runtime/procurement_packet.py` — buyer evidence packet builder.
- `apps/customersuccess/` — first-100-schools tracker.
