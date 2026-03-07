# Section 25.6 — Data governance: retention, consent, rights

## Implemented

- **Retention:** `apps/compliance` models include `DataRetentionRule` (school, data_class, retention_days). Export/compliance commands use retention windows. Policy slice `compliance.retention` (from `get_effective_policy(school)["compliance"]`) can drive per-tenant retention; merge from school.settings.
- **Consent:** Consent request and consent record models; document types (e.g. privacy_policy, parental_consent). Use for parental consent and field-trip style consents.
- **Right to access / export (data portability):** `apps/compliance/gdpr_services.py`: `export_student_data_portability(school_id, student_id, format)` for student data export. One-click exports (CSV, JSON) referenced in architecture; extend as needed for full portability.
- **Right to erasure:** Implement erasure as a controlled workflow: flag or anonymize records per policy and audit. Document in compliance app or runbooks; avoid hard-delete of audit trail where legally required.
- **Data classification / residency:** Policy slice `compliance.data_residency`, `compliance.regional_controls`. Use when storing or routing data.

## Checklist 25.6

- Data classification: tag models/sensitive fields; use in retention and access rules.
- Retention per region: drive from policy; run periodic jobs that apply retention rules.
- Consent registry: existing models; expose to parents and staff per tenant.
- Right-to-access/export: export_student_data_portability; add other entity exports as needed.
- Right-to-erasure: workflow + audit; document in runbooks.
