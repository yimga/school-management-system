# Certified Administrator Program — Operator Guide

**Wave L · v3.95.0 · 2026-05-26**

A Salesforce/Shopify-style certification program for RMC. Three flywheel effects:

1. **Switching cost moat** — certified admins are personally invested.
2. **Talent supply** — districts hiring certified admins prefer RMC schools.
3. **Lead pool** — every certified admin is a named contact we can reach.

## Tracks (v3.95.0 seed)

| Track | Audience | Level | Modules | Exam |
|---|---|---|---|---|
| `rmc-tenant-admin-foundational` | Tenant-Admin | Foundational | 6 (Setup, Users, Calendar, Enrollment, Comms, Fees) | 60 Q / 90 min / 75% |
| `rmc-tenant-admin-professional` | Tenant-Admin | Professional | 5 (Approvals, Integrations, Marketplace, Analytics, Automation) | 80 Q / 120 min / 80% |
| `rmc-bursar-specialist` | Bursar | Professional | 4 (Fees, PSPs, Reconciliation, Tax) | 60 Q / 90 min / 80% |
| `rmc-teacher-champion-foundational` | Teacher-Champion | Foundational | 4 (Roster, Daily Ops, Grading, Parent Comms) | 50 Q / 75 min / 75% |
| `rmc-migration-specialist-concierge` | Migration-Specialist | Expert | 4 (Audit, Adapters, Cutover, Validation) | 80 Q / 150 min / 85% |

**Totals: 5 tracks, 23 modules, 5 exams, ~32 estimated hours of curriculum.**

Each track has a `badge_slug`, `renewal_months` (24 for most; 18 for Migration Specialist — source systems change fast), and a prerequisite graph between modules.

## Registry API

```python
from apps.customersuccess.certified_administrator import (
    list_tracks, get_track, tracks_for_audience, summary,
)

list_tracks()                              # tuple[CertificationTrack, ...]
get_track("rmc-tenant-admin-foundational") # CertificationTrack | None
tracks_for_audience("Bursar")              # tuple[..., ...]
summary()                                  # {"track_count": 5, "module_count": 23, ...}
```

## Learner state (deferred — Wave L+1)

Who's enrolled, who's passed, when their badge expires — these live in a separate model that the v3.95.0 registry does not create. Wave L+1 lands:

- `CertificationEnrollment(learner, track, started_at)`
- `CertificationModuleCompletion(enrollment, module, completed_at, score)`
- `CertificationCredential(enrollment, issued_at, expires_at, badge_url)`

The registry-only-for-now design lets us iterate the curriculum without migration risk.

## Tests

[apps/customersuccess/tests/test_certified_administrator.py](beta/school-management-system/apps/customersuccess/tests/test_certified_administrator.py) — 15 unit tests covering registry shape, prerequisite validity, summary correctness.
