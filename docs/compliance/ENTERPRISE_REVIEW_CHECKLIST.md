# Enterprise review checklist

Use this checklist when preparing answers for **sales/security questionnaires**, **customer security reviews**, or **internal enterprise readiness** reviews. Mark items **done** / **partial** / **not done** for your engagement; this file does not track live state.

## Sales / security questionnaire

- [ ] Confirm which **deployment model** applies (self-hosted vs. hosted) and align answers to `docs/deployment/` runbooks.
- [ ] Summarize **authentication**: staff vs. student flows; SAML/SCIM if enabled in deployment; link to concrete settings and code areas only where accurate.
- [ ] **Data residency / subprocessors:** list actual subprocessors your org uses (hosting, email, error tracking). The repo does not substitute for your vendor list.
- [ ] **Encryption in transit:** describe TLS termination as configured in production (not claimed by this repo).
- [ ] **Audit logging:** reference SiteSettings / config mutation audit patterns and operational log collection in your environment.

## Customer security review

- [ ] Run `python scripts/verify_compliance_evidence.py` and attach or reference the **passing** output.
- [ ] Attach or summarize `docs/generated/security_surface_audit.json` (focus on `governance_tier` and `classification` hotspots).
- [ ] Attach or summarize `docs/generated/tenant_isolation_audit.json` for multi-tenant discussions.
- [ ] Provide **access model** narrative: roles, admin vs. portal, tenant admin boundaries — aligned with product behavior, not aspirations.
- [ ] Document **incident contacts** and escalation (organizational; see `INCIDENT_RESPONSE_POLICY.md` as a template).

## Deployment review

- [ ] Walk through deployment docs under `docs/deployment/` relevant to your stack.
- [ ] Confirm **rollback** steps: `docs/deployment/DEPLOYMENT_ROLLBACK.md`.
- [ ] Confirm **secrets** handling matches your organization (env vars, secret managers); do not embed secrets in tickets.
- [ ] Record **change window** and who approves production deploys (`CHANGE_MANAGEMENT_POLICY.md` alignment).

## Backup / restore review

- [ ] Map `BACKUP_AND_RESTORE_POLICY.md` to **actual** backup jobs (database, media, configuration).
- [ ] Last **restore test** date and outcome (organizational record).
- [ ] RPO/RTO targets stated as **your** commitments, not inferred from code.

## Access control review

- [ ] RBAC / staff roles as implemented; admin URL exposure vs. control-plane surfaces (`audit_admin_gravity.py` context).
- [ ] Offboarding: account disable / SSO deprovision process (organizational procedure).
- [ ] `ACCESS_CONTROL_POLICY.md` reviewed against practice.

## Incident response review

- [ ] Contact tree and severity definitions updated for your team.
- [ ] Runbook links (monitoring, logs) for production.
- [ ] Post-incident review template agreed (`INCIDENT_RESPONSE_POLICY.md`).

## Vendor review

- [ ] List vendors with access to production data or credentials.
- [ ] Vendor risk questionnaire status per vendor (`VENDOR_RISK_POLICY.md`).
- [ ] Subprocessor notification process for customers (if contractual).

---

**Reminder:** Policies under `docs/compliance/policies/` describe **RunMyCampus-aligned** expectations; legal review and organizational approval remain with the operator.
