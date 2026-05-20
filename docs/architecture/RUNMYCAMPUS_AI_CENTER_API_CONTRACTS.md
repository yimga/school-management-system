# RunMyCampus AI Center API contracts

**Status:** repo-scope (Stage 9, batch 1328)

## Query response (`POST /super/ai-center/query/`)

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | Markdown/plain answer (redacted) |
| `audience` | `operator` \| `tenant` | Response tier |
| `route_context` | string | Active path context |
| `evidence` | array | `{doc_id, kind?}` metadata only |
| `missing_context` | bool | True when DATA DEFAULTER emitted |
| `feature_absent` | bool | True when FEATURE CODESPACE DISCONNECT emitted |
| `confidence` | float | 0–1 heuristic |
| `safety_flags` | string[] | e.g. `cross_tenant_block`, `ai_disabled` |
| `audit_id` | string | Correlates audit log events |

## KB draft object

| Field | Type | Description |
|-------|------|-------------|
| `draft_id` | string | UUID hex |
| `title` | string | Draft title |
| `body` | string | Draft body |
| `evidence_ids` | string[] | Required — reject if empty |
| `status` | string | Always `draft` until human publish |
| `tenant_visible` | bool | Always false for auto-generated drafts |

## Error prefixes (exact)

- `FEATURE CODESPACE DISCONNECT: …`
- `DATA DEFAULTER: …`

## Security

- No secrets, tokens, or cross-tenant payloads in requests or responses.
- `AI_CENTER_LOG_PROMPTS` defaults to false.
