# RunMyCampus Customer Success Motion

**SOT batch 1217** — Salesforce + Amazon pillar push.
**Audience:** customer success engineer, founders during the first-100-schools phase.
**Promise:** every paying school has a known health score, a named owner, a defined cadence, and a concrete next step.

---

## 1. Why customer success exists

The Salesforce pillar is not closed by workflow packs alone — it requires a **delivery org**: humans who own the relationship after go-live. The Amazon pillar is not closed by SOT discipline alone — it requires the school to actually run on the platform without daily support fires.

Until paying schools exist, this is a contract template that the founders execute personally. Once the first school goes live, the rows in `apps/customersuccess/` become the operating ledger.

---

## 2. The four-stage customer journey

### Stage 1 — Pre-go-live (implementation track)
Owned by the implementation engineer (see `IMPLEMENTATION_PLAYBOOK.md`).

### Stage 2 — Go-live week
Owned by both implementation engineer and customer success contact. Daily check-in. Health score is monitored hourly via `tenant_lifecycle_engine`. No silent failures.

### Stage 3 — First 90 days
Owned by customer success engineer (named for the account).

Cadence:
- Day 7 post-go-live: usage check, blockers list, top 3 wins.
- Day 30: first quarterly business review (compressed to 30 minutes).
- Day 60: payment readiness review + roadmap intent.
- Day 90: health score gate — green / yellow / red. Red triggers escalation to founders.

### Stage 4 — Steady state
Owned by customer success engineer; automated + scheduled.

Cadence:
- Monthly: usage report, ticket summary, health score trend.
- Quarterly: business review (45 min) — usage, value, gaps, roadmap.
- Annually: contract renewal review + procurement packet refresh.

---

## 3. Health score

Driven by `customer_health` + `tenant_lifecycle_state_machine`. Composed of:

| Signal | Weight | Source |
|---|---|---|
| Auth activity (last 7 days) | 15% | AuditLog logins |
| Roll-call submission rate | 15% | offline action queue + workflow logs |
| Invoices generated vs paid | 15% | finance.invoices |
| Open critical defects | 15% | configuration_change_requests |
| Apple-class UX axe findings on tenant subdomain | 10% | apple_class_authenticated_browser_report |
| Tenant kill-test verdict | 10% | run_kill_test |
| Renewal proximity (last 90 days of contract) | 10% | contract metadata |
| Operator escalations in window | 10% | escalation_history |

**Green:** ≥ 80. **Yellow:** 60–79. **Red:** < 60.

Red triggers a defined escalation path:
1. Customer success contacts the school within 1 business day.
2. Implementation engineer is re-engaged for ≤ 5 business days.
3. If health does not return to ≥ 70 after 14 days, founders are informed and a save plan is written.

---

## 4. The first-100-schools cohort tracker

`apps/customersuccess/models.py` is the source of truth. The dashboard is wired and ready; rows arrive only when a school goes live.

Required columns per row:
- `cohort_number` (1–100)
- `school_name`
- `track` (self_serve | guided | assisted_enterprise)
- `target_go_live_date`
- `actual_go_live_date`
- `tier` (free pilot | paid pilot | paid enterprise)
- `region` (CM / GH / NG / KE / US / GB / EU / other)
- `health_score`
- `north_star_at_go_live`
- `apple_class_axe_findings_at_go_live`
- `first_paid_invoice_date`
- `first_settlement_date` ← THE single most important field
- `assigned_cs_engineer`
- `escalation_history`
- `renewal_decision_date`

The dashboard answers four questions instantly:
1. How many schools are live? (`count(actual_go_live_date is not null)`)
2. How many are paying? (`count(first_paid_invoice_date is not null)`)
3. How many are settled? (`count(first_settlement_date is not null)`)
4. What is the median health score?

**The first row with `first_settlement_date != NULL` is the moment we move from "CATEGORY DEFINING — REPO SCOPE" to "CATEGORY DEFINING — LIVE PROVEN".**

---

## 5. The save play

A red-health school gets a save play written by the customer success engineer:

1. Diagnose (in writing, blameless): what changed?
2. Fix (within 14 days): what code/config/process change resolves it?
3. Communicate: weekly status to the school until green.
4. Audit: a SOT batch entry per save play, even if the fix is purely operational.

A red-health school that does not return to green within 30 days is reviewed by founders for either contract restructuring or graceful exit. **We never let a school stay unhappy silently.** Hidden churn destroys the Amazon pillar.

---

## 6. The implementation partner network

Eventually, customer success scales by enabling implementation partners (regional consultants, education-IT firms). Each partner is certified through:

1. Successful completion of an assisted-enterprise implementation under our supervision.
2. Sign-off on `IMPLEMENTATION_PLAYBOOK.md` and `PARTNER_APP_CERTIFICATION.md`.
3. Access to a dedicated developer/operator account on the platform.
4. Quarterly partner business review.

Until then, RunMyCampus is its own implementation partner. That is the right scope for the first 10 schools; partners enter at school 11–100.

---

## 7. Honest carve-outs

We never:
- Promise outcomes we cannot deliver because of external blockers.
- Sell more aggressively to a yellow/red-health school.
- Hide health from a school's leadership.
- Recommend our own apps as a workaround when the school's actual problem is different.

We always:
- Tell schools what we see.
- Tell schools what we are doing.
- Tell schools what they need to do.
- Audit every health change, escalation, save play, and renewal decision.
