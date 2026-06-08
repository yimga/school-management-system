# Audit Retention

Compliance retention uses archive-before-purge. The canonical service is
`apps.compliance.audit_retention`.

## Guarantees

- Eligible rows are serialized deterministically to gzip JSONL.
- Every bundle stores SHA-256 and an HMAC signature under a dedicated key.
- Verification checks the bundle hash, signature, manifest, unique row IDs, and
  row count before deletion.
- Purge requires `AUDIT_RETENTION_APPROVAL_TOKEN` and deletes only the exact IDs
  present in the verified bundle.
- Append-only `AuditLog` rows bypass the ORM guard only inside this verified,
  approval-gated transaction.
- Active legal holds are checked before archive and again before purge.
- A count mismatch rolls back the transaction.

Use:

```text
python manage.py archive_old_audits --dry-run
python manage.py archive_old_audits
python manage.py archive_old_audits --purge --approval-token <token>
```

`AUDIT_ARCHIVE_SIGNING_KEY` must be independent from the Django secret key.
Archive storage must be backed up with immutable retention and access controls.

Automatic conversion of the live audit table to PostgreSQL declarative
partitioning is intentionally not performed by application code. PostgreSQL
cannot safely convert an existing table in place; the required table swap,
foreign-key handling, and lock window are deployment-specific. Signed bounded
archives provide the portable retention mechanism. A partition migration, when
capacity evidence requires it, remains a separately reviewed infrastructure
change rather than an unsafe application startup action.
