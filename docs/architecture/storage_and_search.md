# Storage and search (internal-first)

## Storage abstraction

- **Contract:** Use `apps.platform_runtime.storage` for programmatic file operations: `save_to_storage(path, content)`, `get_storage_url(path)`, `delete_from_storage(path)`, `storage_exists(path)`.
- **Backend:** Django `DEFAULT_FILE_STORAGE`. Default is local filesystem (`MEDIA_ROOT`). For S3-compatible (e.g. MinIO, AWS S3), set:
  - `DEFAULT_FILE_STORAGE` to a backend such as `storages.backends.s3boto3.S3Boto3Storage`
  - Configure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL` (for MinIO) as needed.
- **Tenant paths:** Prefer paths under `tenants/{school_id}/...` for tenant-scoped files (see siteconfig `_tenant_upload_to`).
- **No direct boto3** in app code; all access via Django storage API or `platform_runtime.storage`.

## Search read layer

- **Current:** `apps/api/search_api.py` uses DB queries (PostgreSQL) for global search.
- **Target:** OpenSearch (or Elasticsearch-compatible) as read layer for search and observability. When `OPENSEARCH_DSN` (or equivalent) is set, search can be routed to OpenSearch; otherwise fallback to DB.
- **Integration:** Add `apps.api.opensearch_client` (or `apps.search`) that:
  - Exposes `search(q, type, school_id, limit)` returning same shape as current API.
  - If OpenSearch is configured, query the index; else call current DB search.
  - Index updates: via domain events (e.g. `student.created`, `invoice.created`) or periodic sync.
- **References:** `apps/api/search_api.py`, `docs/architecture/domain_events.md`.
