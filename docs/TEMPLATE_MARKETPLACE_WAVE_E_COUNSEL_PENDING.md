# Template Marketplace — Wave E counsel-pending docket

**Status:** PENDING — gates NOT yet cleared. Wave E+ items in plan §11.5 (rows 8 + 9) cannot ship until every gate below is green.

This docket exists so the operator + counsel know exactly what evidence the platform requires before partner publishing and template monetization can go live. Both are NOT in scope for batches 1400–1404 (repo work). They are explicit external blockers.

---

## What Wave E unlocks

| Capability | Plan §11.5 row | Gate behind |
|---|---|---|
| **Partner-published templates** | 8 | `RMC_TEMPLATE_PARTNER_PUBLISH_ENABLED=1` (default `0`) |
| **Template monetization (paid templates, settlement, rev-share)** | 9 | `RMC_TEMPLATE_MONETIZATION_ENABLED=1` (default `0`) |

Both flags are read by the marketplace publishing surface (Wave E+ work). Until either flag flips:
- The partner-template publish endpoint refuses POST and returns 503 with `external_pending: true`.
- All template manifests are treated as `pricing_model="free"` regardless of any monetization manifest fragment.

## Pre-condition gates the operator must clear

### Gate 1 — Counsel signoff PDF on partner publishing terms

**Owner:** Legal / counsel.
**Evidence path:** `docs/legal/template_marketplace_partner_publishing_signoff.pdf` (file MUST be present and counsel-signed).
**Why:** Partner-published code runs inside tenant browsers + may declare locale/payment-rail defaults. Counsel must confirm liability allocation, indemnity, takedown procedure, and tenant-data-isolation guarantees.
**Reference:** mirror of `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` pattern (open docket framing CFAA / DMCA § 1201 / state computer-trespass).

### Gate 2 — Partner verification process documented + operational

**Owner:** Platform operator.
**Evidence path:** `docs/PARTNER_PUBLISHER_VERIFICATION_RUNBOOK.md`.
**Why:** `publisher_verified_at` field on the manifest must come from a real verification artifact (domain-DNS proof, business-registry record, or signed attestation). Without this, the marketplace becomes a vector for malicious template injection.

### Gate 3 — Stripe settlement infrastructure (monetization only)

**Owner:** Platform operator + Finance.
**Evidence path:** `var/evidence/template-marketplace/stripe_settlement_proof_<YYYY-MM-DD>.json` (sample successful payout receipt).
**Why:** Paid templates require Stripe Connect or equivalent settlement provider. Until live settlement is proven, no `pricing_model != "free"` manifest may be accepted.

### Gate 4 — Per-jurisdiction tax + revenue-recognition opinion

**Owner:** Counsel + Tax advisor.
**Evidence path:** `docs/legal/template_marketplace_tax_opinion_<YYYY-MM-DD>.pdf`.
**Why:** Revenue share with international partners triggers VAT/GST collection + revenue-recognition obligations that vary per country. Counsel must opine before any paid template publishes.

### Gate 5 — Refund + dispute SOP

**Owner:** Support + Finance.
**Evidence path:** `docs/SUPPORT_RUNBOOK_TEMPLATE_MARKETPLACE.md`.
**Why:** Paid templates create refund obligations + chargeback exposure. The support team must have a documented SOP before customers can buy.

### Gate 6 — Code-signing infrastructure for partner templates

**Owner:** Security.
**Evidence path:** `docs/PARTNER_TEMPLATE_CODE_SIGNING.md` + reference implementation in `apps/marketplace/template_signing.py` (Wave E+ to be written).
**Why:** `code_signature` field on the manifest is a 128-hex marker today. Wave E+ must back it with real cryptographic signature verification (sigstore / cosign / Ed25519 with verified publisher key).

---

## What is shipped TODAY (batch 1403)

Manifest schema scaffolds are in place so partners can self-check manifests against the contract the platform will eventually accept:

- `apps/marketplace/template_partner_manifest.py` — `validate_partner_template_manifest()` + `REQUIRED_FIELDS` + `ALLOWED_CATEGORIES` + `ALLOWED_LICENSES` + `example_manifest()`.
- `apps/marketplace/template_monetization_manifest.py` — `validate_monetization_manifest()` + `PRICING_MODELS` + `SETTLEMENT_PROVIDERS` + `ALLOWED_CURRENCIES` + `example_monetization_manifest()`.

Run a manifest through validation before submitting:

```python
from apps.marketplace.template_partner_manifest import validate_partner_template_manifest
result = validate_partner_template_manifest(my_manifest_dict)
assert result.ok, result.findings
```

When all 6 gates above are green, Wave E+ adds:
- A real `partner_publish_view` POST endpoint.
- A `TemplateMonetization` model storing the settlement state.
- Stripe Connect onboarding for partners.
- The `RMC_TEMPLATE_PARTNER_PUBLISH_ENABLED` + `RMC_TEMPLATE_MONETIZATION_ENABLED` gates flip ON.

Until then, do NOT claim partner publishing or monetization is live. The repo-scope verdict for the template marketplace stays **75 PREMIUM TEMPLATE SYSTEM READY — REPO SCOPE.**
