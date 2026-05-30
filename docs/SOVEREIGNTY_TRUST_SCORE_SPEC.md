# Sovereignty Trust Score — specification

Per-country 0-100 score surfaced on tenant dashboards and procurement RFP responses. Phase 6 turbo deliverable (`P6-sovereignty-trust-score`).

## Inputs (weights sum to 100)

| Signal | Weight | Source |
|--------|-------:|--------|
| Infra residency status | 25 | Deploy posture (metadata-only / partner-region / physically-pinned) |
| Key custody | 15 | HSM presence + KMS region + customer-managed-key support |
| Regulator API uptime (90-day) | 15 | `regulator_api_federation` health probes |
| Counsel signoff freshness | 15 | Counsel docket date < 365 days |
| Incident history (90-day) | 15 | Sentry / security log for the country residency region |
| Regulatory matrix completeness | 10 | `verify_regulatory_matrix_coverage.py` per-country pass |
| Statute citation freshness (provenance) | 5 | `verify_matrix_provenance.py --require-citation` |

## Output

```json
{
  "country_iso": "GB",
  "score": 87,
  "tier": "high_trust",
  "computed_at": "<iso>",
  "signals": { "infra_residency": 22, "key_custody": 12, "...": "..." },
  "citations": ["docs/generated/country_governance_matrix/GB.json"],
  "stale_signals": []
}
```

## Tiers

| Score | Tier |
|-------|------|
| 90-100 | `high_trust` |
| 70-89  | `validated` |
| 50-69  | `partial_evidence` |
| 0-49   | `evidence_required` |

## Refresh cadence

Live-recompute on any input change; nightly full sweep; SLO freshness < 24h.

## Surfaces

- Tenant dashboard (read-only widget).
- Procurement RFP auto-response pack (PDF export with citation footnotes).
- Public per-country page on `runmycampus.com/sovereignty/<iso>` (operator opt-in).

## Anti-patterns

- Surfacing the score without citation links.
- Padding the score to mask a stale counsel signoff.
- Reporting a score for a country where the regulator API has been down >7 days; the widget shows `evidence_required` instead.
