# Compatibility matrix (non-negotiable)

Tested and supported versions for the RunMyCampus stack. All items due and in scope.

## Core

| Component | Minimum / tested version | Notes |
|-----------|-------------------------|--------|
| Python | 3.11+ | Pin in deployment; 3.12 tested |
| Django | 5.2.x | Pin major.minor in requirements |
| PostgreSQL | 14+ | Primary data store; RLS used |
| Redis / Valkey | 6+ | Optional; Celery broker and cache |

## Async and search

| Component | Version | Notes |
|-----------|---------|--------|
| Celery | 5.x | Task queue; version pinned in requirements |
| OpenSearch | 2.x (optional) | Search read layer when `OPENSEARCH_DSN` set; client opensearch-py |

## External adapters (no direct SDK in app code)

| Capability | Adapter | Config |
|------------|---------|--------|
| SMS | Twilio, AfricasTalking | SiteSettings.sms_provider, api_key, sender_id |
| Email | Django backend | EMAIL_*; SiteSettings.email_from_address |
| Payments | Finance gateways | Policy payment_gateways |
| AI | Ollama, Gemini (REST) | AI_PROVIDER_PREFERENCE, GEMINI_API_KEY, OLLAMA_* |

## Pinning policy

- Production dependencies MUST be pinned (exact or min version with upper bound).
- No bare `*` in production requirements.
- CI must run vulnerability check (e.g. pip-audit); failures must be triaged or waived with ticket.

## References

- `docs/architecture/open_source_spine.md`
- `docs/architecture/SERVICE_CATALOG.md`
