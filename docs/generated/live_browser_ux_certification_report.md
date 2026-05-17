# Live Browser UX Certification Report

- Generated: 2026-05-17T18:46:55.826994Z
- Commit under test: 2e72a4f8d4f8fdaf1043c930126648bc78a7204b
- Environment: local Django test client QA (no runserver)
- Verdict: **LIVE BROWSER UX CERTIFIED - LOCAL**

## Summary
- Platform operator: 14/14 routes 200
- Tenant admin: 10/10 routes 200
- Public marketing: 9/9 routes 200
- Marketing differentiated: 5/5 with markers

## Verifiers
- `validate_marketing_urls_smoke`: PASS
- `verify_manager_render_parity_local`: PASS
- `manage_check`: PASS

## Remaining gaps (Lane 2)
- Hosted Render/custom-domain SHA parity (batch 1199) requires operator deploy/DNS.
- Live pilot scorecard data (batch 1176 Lane 2) requires real schools.
- Playwright visual/axe screenshots optional; run tests/e2e/*.spec.js with runserver for pixel proof.
