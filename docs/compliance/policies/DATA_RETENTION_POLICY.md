# Data retention policy (product hooks)

## Principles

1. **Minimize** stored PII; use role-appropriate fields only.
2. **Audit logs** (e.g. config mutation): retention defaults should align with customer legal requirements — implement purge jobs per jurisdiction when scheduled.
3. **Evaluations / grades / finance** — governed by academic and finance modules; archival exports via EMIS/report flows where enabled.

## Technical levers

- Soft-delete and `is_active` flags on key models.
- Compliance export / evidence pack tooling where present under compliance-related apps.

Automated enterprise-wide retention enforcement is **not** fully implemented in code alone; operations must configure DB and object-store lifecycle rules.
