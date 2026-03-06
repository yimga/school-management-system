# Global Edge (16.4) and Global Testing Matrix (16.6)

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 16.4, 16.6.

---

## 1. Global edge (16.4) — Regional traffic routing

- **Intent:** CDN and edge routing so tenant and public traffic can be served from the nearest region (latency, compliance).
- **Configuration placeholders (env/settings):**
  - `EDGE_REGION_HEADER`: Header set by CDN/edge (e.g. `X-Region: eu-west-1`) for logging and optional routing.
  - `CDN_BASE_URL`: Base URL of CDN for static/media when using CDN.
  - `WAF_ENABLED`: Whether WAF is in front (for logging/audit).
- **Implementation:** Actual CDN/WAF and regional routing are infra/deployment concerns. Application respects `EDGE_REGION_HEADER` when present and logs it for observability; tenant resolution remains host-based.

---

## 2. Global testing matrix (16.6)

Supported regions and locales for QA and localization:

| Region        | Country code(s) | Locale(s) | Notes        |
|---------------|------------------|-----------|--------------|
| USA           | US               | en-US     | K-12, Common Core |
| Brazil        | BR               | pt-BR     | LGPD         |
| Germany       | DE               | de-DE     | GDPR         |
| Japan         | JP               | ja-JP     |              |
| Nigeria       | NG               | en-NG     |              |
| UAE           | AE               | ar-AE, en-AE | RTL       |
| Canada        | CA               | en-CA, fr-CA |              |
| UK            | GB               | en-GB     | GCSE/A-Level |

- **Config:** Optional `TESTING_MATRIX_REGIONS` in settings (list of country codes) for automated tests that assert locale/region behavior.
- **Pytest:** Tag tests with `@pytest.mark.region("US")` etc. when tests are region-specific; run matrix with `pytest -m region` or per-region jobs in CI.
