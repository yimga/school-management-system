# Commercial Platform (Section 29.10)

Self-serve trials, quote-to-contract, and partner tooling for RunMyCampus.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 29.10.

---

## 1. Self-serve trials

- **School.trial_end_date:** Already exists; when set, school is in trial until that date. Billing processors and super dashboard use it.
- **TenantSubscription.trial_end_date:** Synced from school for processor.
- **Behavior:** Trial schools can be limited in features via plan or `is_feature_enabled`; when trial ends, subscription can move to paid or suspend.

---

## 2. Quote-to-contract

- **Quote model (billing.Quote):** Stores draft/sent quotes for a plan and school; status (DRAFT, SENT, ACCEPTED, EXPIRED, DECLINED). When ACCEPTED, create or update TenantSubscription and BillingAccount.
- **Workflow:** Create Quote → send to prospect → on accept, create subscription (or link to existing school). Partner/reseller tooling can create quotes on behalf of schools.

---

## 3. Partner / reseller tooling

- **Deferred:** Full partner portal and reseller dashboards. Document as roadmap.
- **Stub:** RevenueSharePayout and partner-related metadata on BillingAccount/Subscription can support revenue share; partner IDs in metadata.

---

## 4. Implementation status

| Item | Status |
|------|--------|
| Trials (trial_end_date) | Done |
| Quote model | Done (billing.Quote) |
| Quote-to-contract flow (accept → subscription) | Partial (model in place; accept API/action can be added) |
| Partner tooling | Doc / deferred |
