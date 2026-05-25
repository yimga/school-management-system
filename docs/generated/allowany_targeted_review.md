# AllowAny Targeted Review (Batch 1506)

39 AllowAny sites — all anonymous-by-design.

| Bucket | Count | Rule |
| --- | ---: | --- |
| Anonymous discovery | 11 | Read-only catalog metadata; no tenant data |
| `.well-known` | 4 | RFC spec public endpoints |
| Management/verifier views | 6 | Staff-gated path; AllowAny on OPTIONS preflight |
| PWA offline fallback | 3 | Service worker fetches; static payload |
| Signed-token-in-URL | 8 | Token IS the auth (one-time / verify links) |
| CSP / RUM browser beacon | 5 | Browser cannot bear auth; capped + sanitized |

**Verdict:** Zero unsafe AllowAny sites. No repo-side action required.

External blockers (not faked): live PSP discovery endpoints, live Lane 2 health probe surface.
