# GraphQL Production Safety Hardening (Batch 1506)

View: `config/graphql_view.py` → `/graphql/` (schema in `config/schema.py`).

| Control | Posture |
| --- | --- |
| Authentication | Per-resolver `request.user.is_authenticated`; mutations require auth |
| Introspection in production | **Disabled by default** (`GRAPHQL_INTROSPECTION_ENABLED=0`) |
| Rate limit GET | 60 / minute / IP |
| Rate limit POST | 120 / minute / IP |
| Content-Type POST | `application/json` only (415 otherwise) |
| Query depth limit | Not native in graphene-django — mitigated by deliberately narrow schema |
| Query complexity limit | Same — narrow schema is the gate |
| Tenant scoping | Per-resolver via `request.school`; staff-only resolvers explicit |
| Audit log | `op` + `is_authenticated` only — never query body or variables |

## Env-var contract

| Variable | Effect |
| --- | --- |
| `GRAPHQL_INTROSPECTION_ENABLED=1\|true\|yes` | Enables introspection |
| `GRAPHQL_INTROSPECTION_ENABLED=0\|false\|no` | Disables introspection |
| (unset) | Falls back to `DEBUG` |

## Tests

- `apps/api/tests/test_graphql_security_review.py` (existing)
- `apps/api/tests/test_graphql_security_contract.py` (NEW batch 1506)
- `apps/security/tests/test_graphql_tenant_safety.py` (NEW batch 1506)

## Honest limitations

`graphene-django` does not ship native depth/cost limits. Mitigated by the deliberately narrow schema surface (health, me, schoolCount, schools — 5 fields, no nested traversal beyond first-level). Future schema expansions must add depth + complexity guards before merge — this is the explicit forward gate.

**Verdict:** GRAPHQL PRODUCTION SAFETY HARDENED — REPO SCOPE.
