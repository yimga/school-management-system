# AI Auto-Migration + Customer Success (Phase 9)

**Batch:** 1488 · **Verdict:** AI_AUTO_MIGRATION_REPO_SCOPE_PASS

## Floor at Open
- [apps/migration_cloud/](../../apps/migration_cloud/) + [apps/customersuccess/](../../apps/customersuccess/)
- Companion siblings: [companion-extension/](../../../companion-extension/) (MV3) + [companion-tauri/](../../../companion-tauri/) (Rust desktop) + [companion-docker/](../../../companion-docker/) (FastAPI in-DMZ)
- Canonical-CSV intake: `canonical_csv.{rs,py}`
- Vendor preprocessors: PowerSchool / Blackbaud / Veracross / Alma / FACTS / Skyward (read-only)
- AI field mapping routes through [services/ai_helpers.py](../../services/ai_helpers.py) — NEVER direct `services.ai_gateway`
- Secrets handling: Rust `ZeroizeOnDrop`, Python `httpx verify=True` no cookie jar, constant-time token compare
- `scan_pii_logging_smell` baseline 0

## Pipeline Status
| Stage | Status |
|---|---|
| Drag-drop legacy file ingestion | shipped |
| Excel/CSV parser | shipped |
| Raw DB backup intake | contract (counsel-pending Wave E) |
| Source system detection | shipped (`detect_vendor()` ≥3-hit threshold) |
| Field auto-detection | shipped |
| AI-assisted field mapping | shipped via `services.ai_helpers` |
| Confidence scoring | shipped |
| Human approval before import | shipped |
| Visual data cleanup dashboard | contract |
| Row-level error highlighting | contract |
| Duplicate detection | shipped |
| Migration readiness score | contract |
| Customer success handoff | shipped |
| Pre-commit quarantine | shipped |
| Rollback posture | shipped |

## Tests Added (Phase 18)
- `apps/migration_cloud/tests/test_ai_field_mapping_contract.py`
- `apps/migration_cloud/tests/test_legacy_file_ingestion.py`
- `apps/migration_cloud/tests/test_migration_data_cleanup_dashboard.py`
- `apps/migration_cloud/tests/test_visual_data_cleanup_contract.py`
- `apps/customersuccess/tests/test_auto_onboarding_from_migration.py`

## External Blockers (Honest)
- FACTS/Skyward write paths (CFAA/DMCA counsel docket — preserved)
- MAA v2.0 promotion (counsel signoff PDF pending)
- Production LiteLLM keys for live AI field-mapping smoke (Lane 2)

**Verdict:** AI_AUTO_MIGRATION_REPO_SCOPE_PASS
