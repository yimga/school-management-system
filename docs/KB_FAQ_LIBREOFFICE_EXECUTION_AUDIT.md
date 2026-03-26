# KB/FAQ + LibreOffice Execution Audit

**Status:** BLOCKED (external rollout/sign-off pending)

## Evidence matrix

| Tier | Evidence | Status |
|---|---|---|
| T0 Safety | `apps/portal/document_conversion.py` safe path check + timeout | DONE |
| T1 Headless suite | Writer/Calc/Impress conversion helpers in `document_conversion.py` + `document_service.py` | DONE |
| T2 KB pipeline | `generate_kb_odt`, runbook update, ODT+DOCX flow | DONE |
| T3 Runtime centralization | `document_service.py`; callsites routed (`views_kb`, `views_documents`, `siteconfig/views.py`) | DONE |
| T4 In-browser editing | `views_office.py` + `/kb/office/*` + `/kb/wopi/*` + `HostedOfficeDocument` + `docker-compose.collabora.yml` | PARTIAL (prod infra pending) |
| T5 Consistency | KB home entry to office docs; portal templates | PARTIAL |
| T6 Observability | structured logging + verifier script | PARTIAL |

## KB/FAQ acceptance

- Operator vs tenant audience split enforced in host-aware filters (`kb_context.py`).
- FAQ parity with KB regional/plan/role filtering implemented.
- Manager `/kb/` now resolves to KB namespace (no super dashboard redirect).
- Per-tenant mode decision: **global-only + region/plan/role** (no school-specific overrides yet).

## Verification run

- `python scripts/verify_kb_libreoffice_stack.py` → PASS
- `python scripts/lint_csrf_exempt_usage.py` → PASS
- `python -m pytest apps/portal/tests/test_document_service.py apps/portal/tests/test_kb_manager_route.py apps/portal/tests/test_kb_audience_filters.py -q` → PASS (8)

## Open items (external / blocked)

Follow [execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md](execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md).

1. Production Collabora rollout (TLS, ingress, scaling, persistent storage, backup, DR).  
   - Owner: Platform Ops
2. WOPI security hardening (server-to-server validation and dedicated service account flow).  
   - Owner: Platform Security
3. End-to-end browser validation on manager + tenant in staging with real Collabora service (workflow + script now in repo; env credentials still required).  
   - Owner: Release Manager / QA


## Blocker reduction in this loop

- WOPI endpoint auth moved to signed token flow (no session-bound server calls).
- Added manual staging automation: `.github/workflows/collabora-wopi-smoke.yml`.
- Added seed command: `python manage.py seed_office_documents` for stable smoke doc IDs.
