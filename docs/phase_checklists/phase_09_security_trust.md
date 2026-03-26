# Phase 9 — Security / trust / endpoints / raw SQL — checklist

**SOT:** §12 gates; trust templates under `templates/accounts/`, `templates/schools/super_trust_center.html`.

## Inventory scripts (when run)

- [ ] `scripts/build_phase8_security_ledger.py`
- [ ] `scripts/lint_broad_except.py` (allowlisted)
- [ ] Grep `csrf_exempt`, `AllowAny`, `cursor.execute` on touched PR scope

## Trust surfaces

- [x] `templates/schools/super_trust_center.html` — control plane
- [ ] `templates/accounts/security_trust_hub.html` — tenant/manager as applicable
- [ ] AI gateway: `services/ai_gateway.py`, `apps/portal/views_ai_gateway.py` — backend-only keys

## Validation

- [ ] `python -m pytest apps/accounts/tests/test_security_trust_hub_views.py` (if exists)
- [ ] `python -m pytest apps/portal/tests/test_ai_gateway.py` (scoped)

## Acceptance

- [ ] No provider secrets in browser-adjacent paths (touched scope)
- [ ] Trust posture visible on touched operator/tenant surfaces
