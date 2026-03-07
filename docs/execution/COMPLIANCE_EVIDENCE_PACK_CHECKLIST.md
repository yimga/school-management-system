# Compliance Evidence Pack Checklist (SEC-607)

Use this checklist to generate and verify a regulator-ready compliance evidence bundle.

## Command

```bash
python manage.py export_compliance_evidence_pack --region USA --output-dir logs/compliance_evidence
```

Optional filters:
- `--school-slug <slug>`: export for one tenant.
- `--output-file <path>.zip`: explicit output path.
- `--include-inactive-schools`: include inactive tenants.

## Required Artifacts

The zip must contain:
- `manifest.json`
- `compliance_scorecard.json`
- `dsar_events.json`
- `policy_locks.json`
- `retention_snapshot.json`
- `region_feature_rules.csv`
- `README.txt`

## Validation Checklist

- `dsar_events.json` includes Art.17/Art.20 evidence (`gdpr_action`, `school_id`, `student_id`, timestamp).
- `policy_locks.json` includes lock metadata (`compliance_locked`, `requires_approval`, `tenant_editable` outcomes).
- `retention_snapshot.json` includes retention windows and counts past threshold for audit/session/access datasets.
- `region_feature_rules.csv` includes region-level feature guard statuses.
- `compliance_scorecard.json` is present and parseable as JSON.

## Suggested Follow-Up

1. Store zip in release evidence storage.
2. Attach `manifest.json` to go-live audit notes.
3. Re-run before production deploy cutover.
