# Payment reference semantics

**Status:** Policy (Phase 1.3)  
**Plan:** [PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md](./PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md)

## Rule

- **`Payment.external_reference`** — Use for the **external transaction ID** (payment provider ref, bank transaction ref, receipt ref, webhook reference). This is the canonical field for matching and idempotency: e.g. `update_or_create(invoice=..., external_reference=ext_ref)` so the same external payment is not applied twice.
- **`Payment.reference`** — May hold the same value as `external_reference` for backward compatibility, or a human-readable/internal label. When creating a payment from a receipt or webhook, set **both**: `external_reference` from the provider/receipt, and `reference` to the same value (or leave to default) so displays and logs show a ref.
- **Do not** use only `reference` for external IDs; use `external_reference` so matching and dedup are consistent.

## Where it is set

- **Receipt verification / create from receipt:** `services.record_provider_payment(..., reference=..., external_reference=...)`; `ext_ref = external_reference or reference`; both fields stored.
- **Webhook:** `views` set `external_reference=reference_id` (provider ref) and `reference=data.get("reference", "")`.
- **Manual entry:** Prefer setting `external_reference` when the user provides a bank/provider transaction ID; `reference` can be the same or a short note.

## Deprecation

`reference` is **not** deprecated: keep it for display and for cases where only a single ref is supplied. New code should prefer **`external_reference`** for any value that comes from an external system (provider, bank, receipt).
