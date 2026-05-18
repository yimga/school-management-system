# Observability SLO Registry (P10)

**Audit date:** 2026-05-17
**Pillar:** P10 — 12-pillar platform audit
**Code authority:** [apps/observability/slo.py](../apps/observability/slo.py) (`SLOS` tuple — immutable, treated as code not config).
**Verifier:** [scripts/verify_slo_registry.py](../scripts/verify_slo_registry.py) — AST-parses the registry, asserts unique keys, allowed kinds, valid targets/windows/thresholds.

This document is the **flattened SLO table** — one row per `SLODefinition`. Add new SLOs in `apps/observability/slo.py`, then update this table.

---

## 1. Canonical SLO targets

| Key | Kind | Target | Window | Threshold (ms) | Owner | Sentry transaction |
|---|---|---|---|---|---|---|
| `web.availability` | availability | 99.9% | 30d | — | platform | `http.server` |
| `attendance.submit` | latency_p95 | 95% < threshold | 7d | 800 | academics | `attendance.submit` |
| `grade.entry` | latency_p95 | 95% < threshold | 7d | 900 | academics | `grade.entry` |
| `parent.dashboard` | latency_p95 | 95% < threshold | 7d | 1200 | parent | `parent.dashboard` |
| `migration.bundle_apply` | availability | 99% | 30d | — | migration_cloud | `migration.bundle_apply` |
| `ai.gateway.latency` | latency_p95 | 95% < threshold | 7d | 2500 | ai_platform | `ai.gateway.invoke` |
| `webhook.delivery` | availability | 99% | 30d | — | integrations | `webhook.deliver` |
| `sync.conflict_pending` | freshness | 99% | 7d | — | sync_engine | (queue freshness probe) |
| `finance.invoice_create` | latency_p95 | 95% < threshold | 7d | 900 | finance | `finance.invoice_create` |
| `finance.payment_record` | latency_p95 | 95% < threshold | 7d | 1100 | finance | `finance.payment_record` |
| `auth.login` | latency_p95 | 95% < threshold | 7d | 700 | accounts | `auth.login` |
| `api.public_config` | latency_p95 | 99% < threshold | 7d | 350 | platform | `api.public_config` |
| `ui.friction.validation_retry` | error_rate | (see code) | 7d | — | platform | (form retry tracker) |

**Total:** 13 SLOs across 7 owner teams.

---

## 2. Burn-rate alerting

Reference: Google SRE Workbook ch. 5 (Alerting on SLOs).

| Alert tier | Burn rate × window | Meaning | Page rule |
|---|---|---|---|
| Fast burn | 14.4× over 1h | 2% of monthly budget burned in 1h | Page primary on-call immediately |
| Slow burn | 6× over 6h | 5% of monthly budget burned over 6h | Page secondary on-call; primary if unacknowledged 15min |
| Drift | 1× over 24h | At-budget burn for a day | Ticket only (slack channel) |

Burn-rate math + thresholds live in [apps/observability/slo.py](../apps/observability/slo.py). The 14.4× constant is the canonical SRE-handbook fast-burn rate.

---

## 3. RUM (Real User Monitoring)

| Surface | Endpoint | What it captures |
|---|---|---|
| Browser RUM beacon | [apps/platform_runtime/views_rum.py](../apps/platform_runtime/views_rum.py) | `LCP`, `INP`, `CLS`, `TTFB`, route, user-agent class, tenant subdomain |
| Server timing | (middleware) | per-route p50/p95/p99 surfaced into Sentry |
| Synthetic probe | [apps/observability/db_liveness.py](../apps/observability/db_liveness.py) | DB ping latency (writes to liveness table) |

RUM CLS budget — gated in CI via [.github/workflows/lighthouse-ci.yml](../.github/workflows/lighthouse-ci.yml) at `< 0.1` (per `lighthouserc.cjs`).

---

## 4. Sentry alert rules (rules-as-code)

| Rule key | Threshold | Window | Action |
|---|---|---|---|
| `integrations.refresh_storm` | ≥ 5 in 10min | 10min | Page on-call |
| `integrations.refresh_transport_flap` | ≥ 20 in 1h | 1h | Page on-call |
| `integrations.webhook_handler_crash` | ≥ 1 | 1min | Page on-call (critical) |
| `integrations.subscription_renewal_failed` | ≥ 3 in 24h | 24h | Slack notify |
| `integrations.mailbox_fetch_unauthorized` | ≥ 1 | 1min | Page on-call (auth break) |

Source: [apps/integrations_marketplace/sentry_alert_rules.py](../apps/integrations_marketplace/sentry_alert_rules.py) `ALERT_RULES` tuple.

Drift gate: [scripts/verify_sentry_alert_rule_drift.py](../scripts/verify_sentry_alert_rule_drift.py) compares this tuple against `var/sentry-alert-rules-snapshot.json` (operator-exported via `sentry-cli`). Reports repo-only / snapshot-only / field-mismatched rules. **Soft-passes** when snapshot absent.

---

## 5. Incident model

[apps/observability/models.py](../apps/observability/models.py) — `PlatformIncident`. Severities follow PagerDuty convention: `SEV1` (full outage) → `SEV2` (significant degradation) → `SEV3` (partial / single-tenant) → `SEV4` (cosmetic / monitor-only).

**Postmortem template:** any incident at SEV1/SEV2 spawns a row in `PlatformIncident` with `postmortem_required=True`. Operator fills `lessons_learned` + `action_items` within 14 days of resolution.

---

## 6. Daily operator drill

```bash
python scripts/verify_slo_registry.py           # structural integrity
python scripts/verify_sentry_alert_rule_drift.py  # rules-as-code vs snapshot
python scripts/scan_sentry_boundary.py          # sentry_sdk fence check
```

All three must exit 0 on main.

---

## 7. Honest carve-outs

- **Live SLO dashboard URL** — owned outside the repo (Grafana / Sentry dashboards). Repo declares the targets; visualization is operator infrastructure.
- **Synthetic probe targeting `manager.runmycampus.com`** — declared in code but lives in operator's external uptime monitor (Pingdom / StatusCake / Render's built-in health check); not a CI gate.
- **Error-budget burn calculation** — code declares the constants; the actual count over a rolling window comes from Sentry's events/transactions API.
