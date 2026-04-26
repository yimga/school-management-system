# Enterprise rollout checklist

Use as a field worksheet. No check is “theatre”: each item should have an owner and date.

## 1. Discovery

- [ ] Student count, campuses, and **current** SIS/communications stack.  
- [ ] Compliance constraints named (e.g. residency expectations)—**no legal guarantees** in this doc.  
- [ ] Success definition for phase 1 (3 bullets max).

## 2. Tenant setup

- [ ] School / tenant + plan / entitlements in **data** (not slides).  
- [ ] `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` for real browser origins.  
- [ ] Operator access path documented (impersonation or dedicated operator policy).

## 3. Admin training (CP-first)

- [ ] CCC / domains walkthrough.  
- [ ] Where academic structure is changed vs **evidence** pages.  
- [ ] When to use **Advanced/Admin** fallback.

## 4. Teacher onboarding

- [ ] Login, class context, and first actions they need weekly.  
- [ ] One **office hour** and async channel.

## 5. Report setup

- [ ] Which report types are in v1.  
- [ ] If scheduled: **process** (worker/cron) ownership on customer side.  
- [ ] Evidence page optional review for sign-off.

## 6. Support cadence

- [ ] Weekly 15 min in pilot; then biweekly.  
- [ ] Escalation: who is paged and when.

## 7. Go / no-go

| Gate | Met? |
|------|------|
| Smoke path subset green on customer host | |
| At least one end-to-end academic + people path | |
| Named support path live | |
| Stakeholder sign-off | |

## Related

- `FIRST_CUSTOMER_ONBOARDING.md` · `docs/growth/OUTREACH_PLAYBOOK.md`
