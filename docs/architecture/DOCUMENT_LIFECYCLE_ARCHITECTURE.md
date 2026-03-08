# Document and file lifecycle architecture

Governed document classes, versioning, retention, and access for admissions, reports, compliance, and enterprise trust.

## Requirements

- **Document classes:** Official vs internal; per-module (admissions, reports, compliance, HR).
- **Versioning rules:** Immutable versions; audit trail for changes.
- **Secure previews:** No raw file exposure; preview URLs with expiry and scope.
- **Retention and archive:** Policy-driven retention (e.g. compliance.retention_schedule from runtime); archive rules.
- **OCR/AI extraction hooks:** Extension points for document processing pipelines.
- **Document access policy:** Who can view/download; export restrictions (compliance.export_restrictions).
- **Watermark/signature rules:** Policy-driven for official documents.
- **Lifecycle state model:** Draft, pending_review, approved, published, archived, purged.

## Implementation direction

- Central document model (or adapter over existing file/store models) with `document_class`, `lifecycle_state`, `tenant_id`, `scope`.
- Resolve access and retention from `request.tenant_runtime.compliance` and policy; no hardcoded region/tenant rules.
- Integrate with reporting and admissions for official artifacts (report cards, certificates, application docs).

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2, Law 9)
- apps/platform_runtime/contracts.py (ComplianceContext)
- RunMyCampus: resolve access/retention from `request.tenant_runtime.compliance`; no hardcoded region/tenant rules.
