# Universal Schema Mapping Audit (Phase 7)

**Batch:** 1488 · **Verdict:** UNIVERSAL_SCHEMA_MAPPING_REPO_SCOPE_PASS

## Floor at Open
- [apps/global_registries/](../../apps/global_registries/) + [apps/interop/](../../apps/interop/) + [apps/metadata/](../../apps/metadata/) + [apps/student360/](../../apps/student360/)
- 20-domain `DOMAIN_CANONICAL_HEADERS` in [apps/migration_cloud/](../../apps/migration_cloud/) (mirrored in companion-tauri + companion-docker; drift detector at `scan_companion_canonical_headers_drift.py`)
- OneRoster integration: [api/oneroster_roster_webhook.py](../../apps/api/oneroster_roster_webhook.py)
- SCIM 2.0: [api/scim_views.py](../../apps/api/scim_views.py)
- Vendor field mappings per [VENDOR_COVERAGE.md](../../apps/accounts/legacy_hashes/VENDOR_COVERAGE.md)

## Global Field Classes
| Class | Status |
|---|---|
| Identity | shipped |
| Demographic | shipped |
| Contact | shipped |
| Enrollment | shipped |
| Guardian/custody | shipped |
| Academic record | shipped |
| Attendance | shipped |
| Finance summary | shipped |
| Medical/safeguarding | shipped (privacy-gated) |
| Compliance | shipped |
| Consent | shipped |
| Curriculum track | shipped |
| Academy dual profile | contract |

## Transfer Envelopes
- Student transfer envelope contract documented
- Teacher transfer envelope contract documented
- ConsentRecord + audit event gate every transfer
- Finance record portability: legally-allowed subset only

## Tests Added (Phase 18)
- `apps/global_registries/tests/test_universal_schema_mapping.py`
- `apps/metadata/tests/test_custom_field_global_mapping_required.py`
- `apps/interop/tests/test_student_transfer_envelope.py`
- `apps/interop/tests/test_teacher_transfer_envelope.py`
- `apps/interop/tests/test_schema_mapping_validation.py`
- `apps/student360/tests/test_dual_identity_profile_contract.py`

## External Blockers (Honest)
- OneRoster receiving school registry (vendor onboarding)
- MoE/government schema mapping per country (Phase 14 stakeholder OS)
- FACTS/Skyward write paths (CFAA/DMCA counsel docket — preserved)

**Verdict:** UNIVERSAL_SCHEMA_MAPPING_REPO_SCOPE_PASS
