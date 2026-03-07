# Government / District Intelligence Layer (Section 14.5)

EMIS-style reporting and secure aggregation for ministries and districts. School data stays tenant-scoped; aggregation is permission-gated and optionally region-resident.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 14.5; phase14_through_phase20_sections_14_to_26.md.

---

## 1. Purpose

- **Ministries / districts** need aggregated, non-PII (or controlled PII) views across schools.
- **Security:** Only authorized roles (e.g. ministry admin, district admin) can access aggregate APIs; data residency and encryption as per region.
- **Product roadmap:** Full EMIS/reporting extensions and secure aggregation pipelines are documented here; implementation is phased.

---

## 2. Contract

- **Aggregate API (stub):** `GET /api/government/aggregates/` (or equivalent) — returns counts/sums by region, level, or district when the requesting user has `government_aggregate` (or similar) capability. No student-level PII in response.
- **Data residency:** Aggregation can be scoped by `compliance_region` or `regional_cluster`; document in security/compliance.
- **Subprocessor / DPA:** When government data is processed, document in DPA and subprocessor list (Section 17.3).

---

## 3. Implementation status

| Item | Status |
|------|--------|
| Architecture doc | Done (this doc) |
| Permission-gated aggregate API stub | Done (api view or stub that checks capability and returns empty/placeholder) |
| Full EMIS pipeline | Product roadmap / deferred |
