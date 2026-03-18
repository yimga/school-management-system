# BEYOND_REACH — Blocked items and measurement (go-live proven)

**Purpose:** Single place for items that cannot be implemented until unblocked, and for measurement processes that require real-school go-lives. Status stays in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md); this doc is the reference.

---

## Blocked (vendor / API unblock required)

| Item | Why blocked | When unblocked |
|------|-------------|----------------|
| **Clever/ClassLink (Wedge 4)** | District roster + SSO as product requires vendor API/partnership. | When vendor/API allows; then implement roster sync + SSO connector per WEDGES_7_13 and SOT §0.4.1. |

**Rule:** Do not implement stub integrations that imply certification until unblocked. Document in Trust center "District & ERP" as "Clever/ClassLink on roadmap."

---

## Proven with real usage (measurement process)

These items require **measured** go-lives or baselines; code is in place; proof is via measurement.

| Item | What to measure | How |
|------|-----------------|-----|
| **Go-live &lt;2 weeks (Wedge 1)** | Time from signup to first meaningful use (teacher/parent/admin). | Run 2–3 real-school go-lives; record calendar days; document in SOT §0.2.1.2. |
| **Months-not-years HE (Wedge 6)** | HE implementation timeline (signup → go-live). | Run 1+ HE go-lives; record months; document. |
| **Setup in minutes, not days (N29)** | School creation + integration + first use in minimal steps. | Human click-through per [CLICK_REDUCTION_BASELINE.md](CLICK_REDUCTION_BASELINE.md); fill Baseline and Final for Create school and onboarding flows; target ~50% reduction. |

**Checklist when measuring:** (1) Use CLICK_REDUCTION_BASELINE.md for admin/tenant flows. (2) For go-live timelines, record in SOT or a short GO_LIVE_MEASUREMENT.md (date started, date first use, role). (3) Update BEYOND_REACH §11 and SOT when proven.
