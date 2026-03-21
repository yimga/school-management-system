# OpenAPI / schema access (§0.1.5 Serious B2)

## Policy

- **`GET /api/schema/`** (JSON OpenAPI) and **`GET /api/schema/ui/`** (Redoc-style UI) require an authenticated user who is **staff, superuser, or role in** `ADMIN`, `IT_ADMIN`, `LEADERSHIP`.
- Feature flags (`enable_api_schema_ui`, `allowed_roles_api_schema`) may further restrict the UI path.
- **Anonymous** clients are redirected to login or denied — the schema is **not** a public endpoint.

## Dependencies

- **`PyYAML`** is required so `GET /api/schema/` (DRF OpenAPI renderer) does not fail at runtime.

## Evidence

- Tests: `apps/schools/tests/test_sot_0155_openapi_schema_access.py`
- Implementation: `config/urls.py` — `_is_schema_allowed`, `schema_view`, `api_schema_ui`

## Operations

- To disable schema UI entirely: set `enable_api_schema_ui` to false in effective feature flags (SiteSettings / runtime flags path used by `get_effective_flags`).
