# Beyond-reach (BR) implementation audit

**Purpose:** Single checklist against §0.3.3 and related hooks. Re-run when shipping BR-adjacent work.

## Verification commands

| Check | Command / action |
|-------|------------------|
| Pillar file registry | `python scripts/verify_sot_pillar_evidence.py` |
| BR automated slice | `bash scripts/run_br_regression_tests.sh` (uses `DJANGO_TEST_DB_FILE=.django_test_dbs/br_regression.sqlite3`; delete that file if migrations fail mid-run) |
| BR-13 luxury pass | `docs/PREMIUM_UX_MANUAL_PASS_BR13.md` — **manual per release** |
| BR super tools | `python manage.py test apps.schools.tests.test_super_beyond_reach` |
| BR-05 strict attendance | `python manage.py test apps.compliance.tests.test_attendance_region_br05` |
| BR-05 enrollment audit/strict | `python manage.py test apps.compliance.tests.test_enrollment_region_br05` |
| BR-06 interventions | `python manage.py test apps.analytics.tests.test_at_risk_intervention_br06` |
| BR-08 comms retention + locale | `python manage.py test apps.communication.tests.test_thread_locale_retention_br08` |
| Migrations | `python manage.py migrate communication` (includes `locale_target` on `ThreadMessage` + `Message`) |

## BR-by-BR status (code truth)

| ID | Shipped surface | Tests / evidence | Honest gaps |
|----|-----------------|------------------|-------------|
| BR-01 | SLO doc, trust center SLO link | SOT paths | Perf strict gate optional |
| BR-02 | `action_registry.py` intents, TOP_20 doc | SOT paths | Nav dedupe not fully automated |
| BR-03 | Manifest, parent SW when `enable_portal_pwa` | MOBILE_PWA doc | Phase-2 offline queue depth |
| BR-04 | `super:migration_csv_diff`, runbook | `test_super_beyond_reach` | Connector docs per SIS vary |
| BR-05 | Attendance: `attendance_region_packs` + `live_compliance_attendance*`. Enrollment: `enrollment_region_packs` + `live_compliance_enrollment*` | `test_attendance_region_br05`, `test_enrollment_region_br05` | — |
| BR-06 | At-risk UI, `at_risk_intervention_action`, `ews_intervention_started` | `test_at_risk_intervention_br06` | Nightly job + ML depth |
| BR-07 | `super:governed_data_query` | `test_super_beyond_reach` | More governed intents over time |
| BR-08 | `ThreadMessage` + `Message.locale_target` on DM, group threads, **communication API**, **portal support/student preview**, **requests notify_requester**, **finance access confirmation** | `test_thread_locale_retention_br08`, `test_message_locale_wiring` | MT / auto-translate optional |
| BR-09 | Legacy CSV preview super | `test_super_beyond_reach` | Lawful-use only (doc) |
| BR-10 | Billing SKUs doc | SOT path | Entitlement wiring ongoing |
| BR-11 | OneRoster substitute | trust doc | Clever native blocked |
| BR-12 | Mega-file lint @ 4500 | `lint_mega_files.py` | Lower threshold over time |
| BR-13 | Premium checklist doc | Manual | Sign-off per release |

## Inconsistencies resolved in SOT

- §0.3.3 table rows for BR-05/06/08 point to **concrete modules** (this file + packs + intervention URL).
- §0.2.1 “Premium / luxury” row **[ ]** is **process debt** (manual pass); BR-13 **[x]** means checklist exists—not that every page passed UX review.

## Event catalog

- `live_compliance_attendance`, `nl_governed_query_executed`, `ews_intervention_started` registered in `apps/platform_runtime/events.py`.
