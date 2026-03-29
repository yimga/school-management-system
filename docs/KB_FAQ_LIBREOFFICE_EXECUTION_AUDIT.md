# KB/FAQ + LibreOffice Execution Audit

**Status:** BLOCKED (T4: Collabora hostname must reach Collabora service, not Django)

## Evidence matrix

| Tier | Evidence | Status |
|---|---|---|
| T0 Safety | `apps/portal/document_conversion.py` safe path check + timeout | DONE |
| T1 Headless suite | Writer/Calc/Impress conversion helpers in `document_conversion.py` + `document_service.py` | DONE |
| T2 KB pipeline | `generate_kb_odt`, runbook update, ODT+DOCX flow | DONE |
| T3 Runtime centralization | `document_service.py`; callsites routed (`views_kb`, `views_documents`, `siteconfig/views.py`) | DONE |
| T4 In-browser editing | `views_office.py` + `/kb/office/*` + `/kb/wopi/*` + `HostedOfficeDocument` + `docker-compose.collabora.yml` | BLOCKED until WOPI host routes correctly (discovery `200`); code paths shipped |
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

1. **DNS / reverse-proxy:** `COLLABORA_BASE_URL` host must terminate on **Collabora** (OSS self-hosted), not the Django app. Verify: `curl -I https://<collabora-host>/hosting/discovery` → `200`.  
   - Owner: Platform Ops  
2. WOPI security hardening (ingress constraints, token rotation, monitoring).  
   - Owner: Platform Security  
3. End-to-end browser validation (operator + tenant) after discovery is `200`.  
   - Owner: Release Manager / QA  

## Policy note (OSS vs “outside codebase”)

Tier 4 does not require proprietary SaaS: **Collabora Online** is open source (MPL). “Outside the git repo” is normal — the WOPI server runs as **another process** on **your** account (second Render service, k8s pod, or VM). If policy forbids any second service, T4 stays blocked until that policy changes; T0–T3 remain valid.

## Tenant deployments (`django-tenants`)

`HostedOfficeDocument` may exist only in **tenant** schemas. Seed with:

`python manage.py tenant_command seed_office_documents --schema=<tenant_schema>`


## Blocker reduction in this loop

- WOPI endpoint auth moved to signed token flow (no session-bound server calls).
- Added manual staging automation: `.github/workflows/collabora-wopi-smoke.yml`.
- Added seed command: `python manage.py seed_office_documents` for stable smoke doc IDs.
