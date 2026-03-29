# Collabora Production Rollout Checklist

## Scope

Production rollout checklist for LibreOffice Online (Collabora) + WOPI routes in RunMyCampus.
Use with:
- `deploy/collabora/k8s/*`
- `docker-compose.collabora.yml`
- `scripts/release/verify_collabora_wopi.sh`

### OSS and “your infrastructure”

Collabora Online is **open source** (MPL). The WOPI editor requires a **document server process** — typically a second service on the same cloud account as Django (Render private service, k8s Deployment, or VM), **not** a requirement to use closed-source SaaS. Code stays in git; runtime topology is ops.

### Tenant DB note

If `seed_office_documents` fails on `public` with missing table but tenant schema has the table, run:

`python manage.py tenant_command seed_office_documents --schema=<tenant_schema>`.

## 1) Configuration

- [ ] `COLLABORA_BASE_URL` set on web service (public HTTPS URL).
- [ ] `WOPI_SHARED_SECRET` set (strong random; different per env).
- [ ] Application host allowlists and CSRF trusted origins reviewed for manager/tenant domains.
- [ ] Confirm Collabora host DNS points to ingress/reverse proxy.
- [ ] Env contract check passes: `python scripts/verify_env_contract.py --profile render-core --profile render-collabora`.

## 2) Infrastructure

### K8s path
- [ ] Apply namespace and secret (`deploy/collabora/k8s/namespace.yaml`, `secret.example.yaml` adjusted).
- [ ] Apply deployment/service/ingress manifests.
- [ ] TLS certificate bound to `collabora.<domain>`.
- [ ] Ingress websocket/proxy timeouts set to >= 3600s.

### Non-k8s proxy path
- [ ] Reverse proxy uses `deploy/collabora/nginx.collabora.conf` equivalent.
- [ ] TLS termination enabled.
- [ ] Upgrade headers and long timeouts configured.

## 3) Security hardening

- [ ] WOPI endpoints protected by auth + token verification.
- [ ] `csrf_exempt` allowlist row present and reviewed.
- [ ] Collabora ingress restricted to required domains/paths.
- [ ] App logs monitored for failed WOPI writes and token mismatch spikes.

## 4) Functional smoke (staging before prod)

Set env and run:

```bash
APP_BASE_URL=https://<app-staging-host> COLLABORA_BASE_URL=https://<collabora-staging-host> WOPI_OFFICE_DOC_ID=<seeded_doc_id_optional> APP_SESSION_COOKIE="sessionid=<cookie>" bash scripts/release/verify_collabora_wopi.sh
```

- [ ] Collabora discovery = 200.
- [ ] `/kb/office/` reachable (200 or auth redirect as expected).
- [ ] WOPI metadata/content routes reachable for seeded doc.
- [ ] Edit-save roundtrip verified manually from one tenant and one operator account.

### Troubleshooting: discovery returns 302

If `verify_collabora_wopi_smoke.py` reports `collabora discovery ... got 302` with redirect to `school-not-found` or app host:

- `collabora.<domain>` is routed to the Django app instead of Collabora.
- Fix DNS/proxy/ingress host routing so `collabora.<domain>` targets Collabora service directly.
- Re-test with:

```bash
curl -I https://collabora.<domain>/hosting/discovery
```

Expected: `200`.

## 5) Release gate integration

- [ ] `python scripts/verify_kb_libreoffice_stack.py` PASS.
- [ ] `python scripts/lint_csrf_exempt_usage.py` PASS.
- [ ] Targeted tests PASS (`test_document_service`, `test_kb_manager_route`, `test_kb_audience_filters`).
- [ ] Include smoke output in release notes / verification run log.

## 6) Operational readiness

- [ ] Alerting: 5xx rate on Collabora ingress and app WOPI endpoints.
- [ ] Capacity: memory/cpu limits tested under concurrent edits.
- [ ] Backup/restore process documented for hosted office docs storage.
- [ ] Incident rollback documented (disable editor link, preserve download access).


## 7) GitHub smoke workflow

- [ ] Run **Actions -> Collabora WOPI smoke** (`.github/workflows/collabora-wopi-smoke.yml`) with staging URLs.
- [ ] Provide `APP_SESSION_COOKIE` secret for authenticated route checks (optional but recommended).


## 8) Render staging quickstart (copy/paste)

### Environment matrix

| Variable | Where | Example | Required |
|---|---|---|---|
| `COLLABORA_BASE_URL` | Render web env var | `https://collabora-staging.runmycampus.com` | Yes |
| `WOPI_SHARED_SECRET` | Render web secret env var | random 32+ char secret | Yes |
| `APP_BASE_URL` | local shell / CI input | `https://staging.runmycampus.com` | Yes (smoke) |
| `WOPI_OFFICE_DOC_ID` | local shell / CI input | `1` | Optional (recommended) |
| `APP_SESSION_COOKIE` | local shell / GitHub secret | `sessionid=...` | Optional (recommended) |

### Deploy + smoke sequence

1. Set `COLLABORA_BASE_URL` and `WOPI_SHARED_SECRET` in Render web service env.
2. Deploy app service.
3. Seed smoke docs in staging shell:

```bash
python manage.py seed_office_documents
```

4. Run smoke from local shell:

```bash
APP_BASE_URL=https://staging.runmycampus.com \nCOLLABORA_BASE_URL=https://collabora-staging.runmycampus.com \nWOPI_OFFICE_DOC_ID=1 \nAPP_SESSION_COOKIE="sessionid=<cookie>" \nbash scripts/release/verify_collabora_wopi.sh
```

5. Run smoke from GitHub Actions (manual dispatch):
   - Workflow: `Collabora WOPI smoke`
   - Inputs: app/collabora URLs + optional `office_doc_id`
   - Secret: `APP_SESSION_COOKIE`

### Exit criteria to mark blocker cleared

- Smoke script returns PASS for discovery + WOPI endpoints.
- One operator and one tenant account complete manual edit/save in browser.
- Evidence appended to `docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`.
- SOT row updated from PARTIAL -> DONE only after above evidence is attached.

See also: [RENDER_ENV_OPERATIONS.md](RENDER_ENV_OPERATIONS.md).
