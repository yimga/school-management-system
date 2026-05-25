# Live / External Claim Boundary Cleanup (Batch 1506)

All overclaim language localized. New scope vocabulary:

- `REPO SCOPE` — passing in-repo verifiers/tests
- `INTERNAL PILOT SCOPE` — passing internal Lane 2 evidence harness
- `PUBLIC LIVE PENDING` — public/Render evidence not yet captured
- `EXTERNAL VENDOR BLOCKED` — credential / counsel / vendor approval pending
- `PWA PROOF PARTIAL` — artifacts present; browser certification pending
- `NATIVE DEFERRED` — explicitly not built; PWA-first
- `COUNSEL PENDING` — counsel signoff PDF / docket open

## Downgraded / clarified claims

| Where | Honest reading | Scope label |
| --- | --- | --- |
| GEOS matrix composite=100 | Repo verifiers green; live/public/external unproven | REPO SCOPE |
| PWA strategy | Artifacts present; install/offline/isolation pending browser | PWA PROOF PARTIAL |
| Native mobile apps | Not built; deferred until ≥100 schools stable | NATIVE DEFERRED |
| PSP live settlement | Manual fallback registered; live rails need creds | EXTERNAL VENDOR BLOCKED |
| GraphQL production | Narrow schema + introspection-off + throttle; no native depth/cost gate | REPO SCOPE READY |
| Multi-corridor pilots | Slot infra present; live data pending field operators | INTERNAL PILOT SCOPE |
| LiteLLM / Render SHA | Harness present; live verification external | EXTERNAL VENDOR BLOCKED |
| FACTS / Skyward write | Counsel docket open; write paths remain honest-stub | COUNSEL PENDING |
