# Graphql Security Review

- Generated: `2026-05-19T09:03:42.563907+00:00`
- Regenerate: `python scripts/generate_certification_artifacts.py --write`

## Verdict

**ACCEPTABLE — query-only, staff-gated registry, rate-limited.**

| Control | Status |
| --- | --- |
| Mutations | none |
| Introspection | enabled (disable in production via GRAPHQL_INTROSPECTION_ENABLED=0) |
| CSRF | csrf_exempt with IP rate limits |
