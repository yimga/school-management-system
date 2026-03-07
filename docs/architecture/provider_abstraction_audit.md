# Provider abstraction audit (RunMyCampus)

**Principle (Part C2):** Own the core; abstract the edges. External integrations must go through adapter interfaces. No view or service should import vendor-specific types or call vendor APIs directly in core flow.

## Adapter inventory

| Capability | Adapter / interface | Implementation(s) | Where used |
|------------|---------------------|--------------------|------------|
| **Payments (tenant-facing)** | `BasePaymentGateway` + registry | Gateways register via `finance.gateways.registry`; config from policy `payment_gateways`. | `apps/finance/gateways/` — `get_gateway(school, method_code, policy=...)`, `get_platform_fee(...)`. |
| **Platform billing (subscriptions)** | `BasePlatformBillingProcessor` | `StripeConnectProcessor` (Stripe webhooks, payouts). Processor code in config; webhook routed by code. | `apps/billing/processors.py`; `PlatformBillingProcessorConfig`; webhook URLs per processor. |
| **SMS / messaging** | Siteconfig / communication channel config | Twilio and others as configured in tenant/site config. | Prefer a single `NotificationProvider` or channel adapter; see `apps/communication` and `apps/siteconfig.models` (e.g. Twilio) for current usage. |
| **Email** | Django email backend + optional provider config | SMTP, SendGrid, etc. via Django `EMAIL_BACKEND` and settings. | Ensure no direct SendGrid/Twilio calls in views; use `send_mail` or a small `EmailSender` wrapper. |
| **AI / LLM** | Portal AI provider abstraction | `apps/portal.ai_provider` (or similar) should expose a single interface; implementations call OpenAI/Azure/etc. | Audit: views and automation must call an internal `completion()` or `embed()` API, not `openai.*` directly. |
| **OCR / document extraction** | (To be formalised) | If present, should be behind e.g. `DocumentExtractionProvider` with implementations per vendor. | Grep for direct Azure/Google OCR imports in app code; move behind adapter. |
| **Storage (files)** | Django storage backends | DefaultStorage, S3, etc. via `DEFAULT_FILE_STORAGE` and per-field storage. | Already abstracted; avoid direct boto3 in app code. |
| **E-sign / video / maps** | (As needed) | Add adapters when features are introduced; same pattern. | — |

## Audit rules

1. **Payment:** All tenant payment flows use `finance.gateways.get_gateway(...)` (and optionally `policy=request.tenant_runtime.policy`). No `import stripe` or vendor SDK in views/services.
2. **Platform billing:** Webhook handlers live in `billing.processors`; config-driven processor selection. No Stripe-specific logic outside `StripeConnectProcessor`.
3. **Messaging:** Target: one `send_sms` / `send_notification` entry point that uses site/tenant config to choose provider. Replace any `twilio.Client` in the middle of flows with this.
4. **AI:** Target: one `generate_completion` / `get_embedding` (or similar) used by portal and automation; implementations in a dedicated module that talks to OpenAI/Azure/etc.

## Gaps to close (by priority)

- **SMS/email:** Confirm a single notification path (e.g. `communication.services.send_notification`) and that no view imports Twilio/SendGrid directly.
- **AI:** Confirm all LLM usage goes through `apps/portal.ai_provider` or a shared `apps/*/ai_*.py` adapter; add wrapper if usage is scattered.
- **OCR:** If any document extraction exists, ensure it is behind an adapter; add one if vendor is called from services/views.

## References

- `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` Part C2 (External Dependency Strategy).
- `apps/finance/gateways/base.py`, `apps/finance/gateways/registry.py`.
- `apps/billing/processors.py` (platform billing).
