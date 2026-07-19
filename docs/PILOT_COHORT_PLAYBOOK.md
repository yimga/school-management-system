# S8: Pilot Cohort Playbook

> Document: `docs/PILOT_COHORT_PLAYBOOK.md`
> Status: Scaffold — beachhead selection criteria defined; register at
> `docs/generated/pilot_cohort_register.json` (empty template until first
> signed cohort entry)

## Purpose

This playbook operationalizes the S3 beachhead selection criteria from the
CURSOR_A_PLUS_MANDATE. It defines:
1. Which schools qualify as pilot candidates
2. What the signup + activation path looks like
3. What metrics we collect from the pilot cohort
4. How we classify pilot readiness vs EXTERNAL dependencies

---

## 1. Beachhead Selection Criteria

A school qualifies for the pilot cohort when it meets ALL of:

| Criterion | Threshold | Why |
|-----------|-----------|-----|
| **Student count** | 50–500 | Small enough for tight support; large enough for meaningful data |
| **Digital readiness** | Has stable internet >=4h/day OR uses mobile money | Platform requires periodic sync |
| **Admin champion** | Named individual with decision authority | Feature adoption needs an internal driver |
| **Fee collection pain** | Currently uses cash/manual ledger | Strongest value proposition = digital fee collection |
| **Geographic diversity** | >=2 regions in first cohort | Proves cross-region viability |
| **Language match** | School operates in EN or FR (platform L10n coverage) | No unsupported-locale risk |

### Disqualifiers

- School has no legal registration (compliance risk)
- School is already on a competitor SaaS (switching cost too high for pilot)
- Admin champion leaves before activation (restart selection)

---

## 2. Signup Checklist

Each pilot school goes through:

- [ ] **Interest expressed** — inbound or outbound contact
- [ ] **Qualification call** — verify criteria above
- [ ] **Data readiness assessment** — what student/staff data exists digitally?
- [ ] **Agreement signed** — pilot terms (free tier, data ownership, exit clause)
- [ ] **Tenant provisioned** — subdomain created, admin account issued
- [ ] **Onboarding session** — 1h video call: dashboard tour, fee setup, attendance
- [ ] **First week active** — at least 1 attendance mark OR 1 fee recorded
- [ ] **30-day checkpoint** — NPS + feature usage review

---

## 3. Activation Metrics to Collect

| Metric | Collection method | Target |
|--------|-------------------|--------|
| **Time to first value** | Timestamp diff: tenant created → first meaningful action | < 48h |
| **Weekly active users** | Django session / login count per tenant | >= 3 distinct users/week |
| **Feature breadth** | Count of distinct feature modules touched (attendance, fees, grades, messaging) | >= 2 modules in week 1 |
| **Offline resilience** | Count of offline-queued actions successfully synced | > 0 (proves offline path works) |
| **Fee collection rate** | Invoices issued vs payments recorded | Track trend, no target yet |
| **NPS score** | In-app survey at day 7 and day 30 | >= 7 (0-10 scale) |
| **Support ticket volume** | GlobalSupportTicket count per tenant per week | Decreasing trend |
| **Churn signal** | No login for 7+ consecutive days | Flag for intervention |

---

## 4. Pilot Register

Machine-readable register at `docs/generated/pilot_cohort_register.json`.

Schema:
```json
{
  "schema_version": "1.0",
  "cohort_id": "S8-beachhead-2026",
  "entries": [
    {
      "school_slug": "example-school",
      "school_name": "Example School",
      "region": "CM-LT",
      "student_count": 250,
      "admin_champion": "Name (role)",
      "signed": false,
      "signed_at": null,
      "tenant_provisioned": false,
      "provisioned_at": null,
      "first_value_at": null,
      "status": "candidate",
      "notes": ""
    }
  ],
  "metadata": {
    "created_at": "2026-07-19",
    "last_updated": "2026-07-19",
    "selection_criteria_version": "1.0"
  }
}
```

Status values: `candidate` | `qualified` | `signed` | `provisioned` | `active` | `churned` | `graduated`

---

## 5. Verification

```bash
python scripts/verify_pilot_cohort_scaffold.py
```

The verifier:
- PASS: playbook exists + register JSON has valid schema
- Reports `EXTERNAL_PILOT_UNSIGNED` until a real cohort entry with `signed=true` exists

---

## 6. EXTERNAL Dependencies

| Item | Why external | Resolution |
|------|-------------|-----------|
| School identification | Requires outbound sales / community outreach | Operator task |
| Agreement signing | Legal document exchange | Operator + school admin |
| Tenant provisioning | Triggered by operator after agreement | Operator runs `ensure_tenant` |
| Onboarding call | Synchronous human interaction | Scheduled by operator |
| Metrics collection (real) | Requires active tenants with real data | Blocked until `status=active` |
