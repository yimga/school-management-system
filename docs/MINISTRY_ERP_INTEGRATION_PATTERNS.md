# Ministry and ERP integration patterns

1. **OneRoster export** — bulk pull for district/ministry data warehouse.
2. **CSV statutory** — scheduled SFTP or signed URL download.
3. **API push** — idempotent POST with agency_ref when government exposes endpoint (`EXTERNAL_CONNECTION_POINTS.md`).
4. **Big ERP** — finance/chart-of-accounts sync via documented CSV or partner iPaaS; RMC remains SIS of record.
