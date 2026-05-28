# Pilot defect triage (batch 1175)

Repo-scope intake for controlled school pilots. Real school feedback is Lane 2 external.

## Intake paths

| Artifact | Purpose |
| --- | --- |
| `apps/platform_runtime/models.PilotDefect` | Canonical defect rows (manager dashboard) |
| `var/evidence/geos-99/pilot/<slug>/defect_backlog.json` | Redacted export snapshot for GEOS evidence |
| `docs/generated/pilot_readiness_scorecard.json` | Slot 2+ pilot status (no secrets / full PII) |

## Operator workflow

1. File defects in **Pilot defect dashboard** (`platform_runtime:pilot_defect_dashboard` on manager host).
2. Set `severity`, `module`, `owner`, `status`; link `linked_test` or `documented_exception` before marking **fixed**.
3. Append a redacted summary to `defect_backlog.json` after each pilot session.
4. Update scorecard slot 2 (`onboarding_status`, `critical_bugs`, `user_feedback_notes`).
5. Run `python scripts/verify_pilot_defect_intake.py` → **PILOT_DEFECT_INTAKE_SCAFFOLD_PASS**.

## Verifiers

```bash
python scripts/write_geos_lane2_residual_evidence.py --school=gilead-school
python scripts/verify_lane2_residuals_on_disk.py
python scripts/verify_pilot_defect_intake.py
```
