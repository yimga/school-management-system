# N24 — Observability, runbooks, and on-call (execution map)

> **CONSOLIDATED — read [OBSERVABILITY.md](OBSERVABILITY.md) + [operations/INCIDENT_RUNBOOK.md](operations/INCIDENT_RUNBOOK.md) first.**
> Per the 2026-05-17 12-pillar audit (P10 doc-hygiene), foundational observability lives in `OBSERVABILITY.md` and on-call / incident response lives in [`operations/INCIDENT_RUNBOOK.md`](operations/INCIDENT_RUNBOOK.md) (SOT batch 1213). This N24 doc is retained as a §0.1.5 execution-map index.

**Purpose:** Single index for operators implementing N24 (RUNMYCAMPUS §0.1.5). Full "metrics everywhere + 24/7 NOC" remains **ops**-dependent; this doc ties **repo truth** to **runbooks**.

## In-product / API

| Surface | Location |
|---------|----------|
| Tenant activity tail | `accounts:tenant_activity_log` — `PlatformEventLog` scoped to tenant (Wave 14 partial). |
| SLO dashboard (HTML/JSON) | `GET /api/observability/slo-dashboard/` — see [SLO_TARGETS_AND_OBSERVABILITY.md](SLO_TARGETS_AND_OBSERVABILITY.md). |
| LB / liveness | `GET /health/`, `/ready/`, `/api/health/` — same doc § Load balancer. |
| RUM web vitals (ingest) | Staff north-star RUM endpoint — [RUM_HOOK.md](RUM_HOOK.md). |
| Proactive deadlines (read model) | `GET /api/internal/north-star/upcoming-deadlines/?school_id=` — merged grading + calendar events (N28; staff/teacher/school-admin). |

## Runbooks and playbooks

- **Master index:** [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md)
- **Trust / resilience narrative:** [NORTH_STAR_TRUST_AND_OPS.md](NORTH_STAR_TRUST_AND_OPS.md)
- **Release:** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
- **Gate output (evidence):** `docs/generated/pre_deploy_gate_run.txt` (from `scripts/record_pre_deploy_gate_output.sh`)

## On-call / escalation (template)

1. **Primary:** Platform ops on-call rotation (define in your org wiki).  
2. **Severity:** P1 = full outage / data loss risk; P2 = degraded; P3 = cosmetic.  
3. **Handoff:** Link this doc + last gate run + trust center Health from incident ticket.

## SOT closure

- **Repo [x] for “structural N24”** when: indexes above exist, tenant activity log shipped, SLO doc + health URLs documented (done).  
- **Full N24 [x]** when: production metrics/traces vendor + on-call roster + paging are **live** (outside this repository).
