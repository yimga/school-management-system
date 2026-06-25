# Pillar E — Offline-first / local-first CI matrix (batches 1732–1742)

Canonical platform docs: `docs/OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md`, `docs/LOCAL_HUB_MODE.md`, `docs/AI_DEPLOYMENT_POSTURE.md`.

## Gate split

| Tier | Command | Requires network | Covers |
| --- | --- | --- | --- |
| **Online golden path** | `python apps/schools/tests/test_provisioning_golive_e2e.py` | Django test DB only | Full provision → setup → launch ceremony |
| **Pillar E program** | `python scripts/verify_tenant_lifecycle_world_class_program.py` | No | Artifacts, Dexie stores, offline workflows, HTML labs |
| **Provisioning program** | `python scripts/verify_provisioning_golive_program.py` | No | 1731 + extended Pillar E wiring |
| **Offline workflow apply** | `python scripts/verify_offline_workflow_apply.py` | No | field_capture dispatch incl. tenant journey handlers |
| **Local-first wiring** | `python scripts/verify_local_first_surface_wiring.py` | No | Portal field_capture baseline surfaces |
| **Offline-sim E2E** | `TENANT_E2E_BASE_URL=… npm run test:e2e:tenant-readiness-offline` | Live tenant URL | Readiness stale banner + cache scripts |
| **Combined armed** | `npm run test:e2e:tenant-journey-pillar-e:armed` | Django + seed | Online go-live + offline-sim in one npm script |
| **Pillar E bundle gate** | `python scripts/verify_pillar_e_ci_matrix.py` | No | Runs all Pillar E verifiers + npm script presence |

## Classroom-critical paths (must pass offline-sim)

- Teacher discipline refer (`/api/discipline/` SW queue + `discipline_refer` field_capture)
- Readiness train stale banner (`RMCSchoolReadinessCache` + Dexie `school_readiness`)
- Launch +7 ack (`launch_playbook_ack` workflow)
- Year-close confirm (`year_close_ack` workflow)
- Partial-failure banner (`data-page-critical-read` + offline hint)

## Honest online-only (labeled in UI)

- Manager Workflow Flight Deck bulk apply / cancel / apply fix
- Live payment authorize, cold signup, webhook mint
- Discipline Master analytics (list mirrors offline; charts online-only)

## Service worker

Bump `static/js/service-worker.js` `CACHE_VERSION` when JS/CSS/offline config changes on journey surfaces.
