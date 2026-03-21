# Open-source spine and operational discipline

Internal-first platform relies on open-source infrastructure. This document records the stack, compatibility, and operational requirements (no backlog; all in scope).

## Stack (current and target)

| Component | Role | Current | Target / notes |
|-----------|------|--------|----------------|
| PostgreSQL | Primary data store | In use | Version pin in requirements/compatibility matrix |
| Redis / Valkey | Cache, Celery broker, sessions | Optional (Celery can use DB) | Prefer Valkey for license clarity |
| Celery | Async tasks, event consumers | In use | Version pinned |
| OpenSearch | Search read layer, observability | When OPENSEARCH_DSN set | Document version; index from domain events; required when search scale demands it. |
| Kong (or alternative) | API gateway, rate limit, auth | Not yet | Required for external-facing API; document as target. |
| Keycloak (or equivalent) | IAM / SSO when needed | Not yet | Required when SSO is in scope; document as target. |
| Temporal (or Celery chains) | Durable workflows | Not yet | Required for long-running workflows; document as target. |

## Version pinning and compatibility matrix

- **Python:** Pin in `pyproject.toml` or `requirements.txt` (e.g. `3.11` or `3.12`).
- **Django:** Pin major.minor; document in README or `docs/COMPATIBILITY.md`.
- **PostgreSQL:** Document minimum (e.g. 14+); pin in Docker/deploy if applicable.
- **Redis/Valkey:** Document version used in CI and production.
- **OpenSearch:** When adopted, pin client and server version (e.g. 2.x).

Maintain a single `docs/COMPATIBILITY.md` (or section in README) listing:

- Python, Django, PostgreSQL, Redis, Celery, OpenSearch (if used), and any other spine components with tested versions.

## Dependency and security policy

- **SBOM:** Generate Software Bill of Materials (e.g. `pip cyclonedx -o sbom.json` or use `pip-audit` / Dependabot).
- **Vulnerability scanning:** Run in CI (e.g. `pip-audit`, `safety`, or GitHub Dependabot); fail or warn on known vulnerabilities.
- **Pinning:** Production dependencies must be pinned (exact or minimum version with upper bound where appropriate); no bare `*` in production.
- **Policy:** Document in `docs/SECURITY_POLICY.md` or `docs/execution/SECURITY_PERFORMANCE_NOTES.md`: dependency review frequency, who may approve bumps, and how CVEs are triaged.

## CI gates

- Unit and integration tests must pass.
- Linting (e.g. Ruff, ESLint) and formatting (Black, Prettier) as configured.
- Dependency/vulnerability check (pip-audit or equivalent) must pass or be explicitly waived with ticket.
- **Required:** SBOM generation and store as build artifact (no optional; see `docs/SECURITY_POLICY.md`).

## Runbooks (all required when applicable)

- **Tenancy:** See `docs/RUNBOOK_TENANCY.md`.
- **Deploy:** See `docs/DEPLOY_CHECKLIST.md`, `docs/execution/RELEASE_HARDENING_CHECKLIST.md`.
- **Observability:** See `docs/OBSERVABILITY_SLO.md`.
- **Event outbox:** See `docs/RUNBOOK_EVENT_OUTBOX.md`.
- **Notification queue:** See `docs/RUNBOOK_NOTIFICATION_QUEUE.md`.
- **Storage/backup:** See `docs/RUNBOOK_STORAGE_BACKUP.md` (required when S3 or production media used).

## References

- `docs/WAVE_EXECUTION_RUNBOOKS.md` — Wave 1–8 operator map
- `docs/architecture/KONG_API_GATEWAY_PLAN.md`
- `docs/architecture/TEMPORAL_WORKFLOWS_PLAN.md`
- `docs/architecture/DEGRADATION_LOAD_TEST_PLAN.md`
- `docs/architecture/SERVICE_CATALOG.md`
- `docs/architecture/storage_and_search.md`
- `docs/security_baseline.md`, `docs/execution/SECURITY_PERFORMANCE_NOTES.md`
