# Provider abstraction audit (RunMyCampus)

**Principle (Part C2):** Own the core; abstract the edges. External integrations must go through adapter interfaces. No view or service should import vendor-specific types or call vendor APIs directly in core flow.

## Adapter inventory

| Capability | Adapter / interface | Implementation(s) | Where used |
|------------|---------------------|--------------------|------------|
| **Payments (tenant-facing)** | `BasePaymentGateway` + registry | Gateways register via `finance.gateways.registry`; config from policy `payment_gateways`. | `apps/finance/gateways/` — `get_gateway(school, method_code, policy=...)`, `get_platform_fee(...)`. |
| **Platform billing (subscriptions)** | `BasePlatformBillingProcessor` | `StripeConnectProcessor` (Stripe webhooks, payouts). Processor code in config; webhook routed by code. | `apps/billing/processors.py`; `PlatformBillingProcessorConfig`; webhook URLs per processor. |
| **SMS / messaging** | `communication.providers.SMSProvider` + `notification_service.send_sms` | Twilio, AfricasTalking adapters in `apps/communication/providers/`. | Single entry point: `apps.communication.notification_service.send_sms`; evals/notifications and others use it. No direct Twilio/AfricasTalking in app code. |
| **Email** | `communication.notification_service.send_email` (Django backend) | SMTP, SendGrid, etc. via Django `EMAIL_BACKEND`. | All notification email via `send_email`; workflow_engine and evals use unified service. |
| **AI / LLM** | Portal AI provider abstraction | `apps/portal.ai_provider` (or similar) should expose a single interface; implementations call OpenAI/Azure/etc. | Audit: views and automation must call an internal `completion()` or `embed()` API, not `openai.*` directly. |
| **OCR / document extraction** | `DocumentExtractionProvider` in `apps.siteconfig.document_extraction`; proposal-only browser worker in `rmc-marksheet-device-ocr.js` | Server Tesseract, Pattern, Google Vision, AWS Textract use the provider. The pinned, self-hosted Tesseract.js worker is a client-only marks proposal path with no write API. | Evals server OCR and finance receipt verification use the provider. Browser marks OCR only fills teacher-review inputs; accepted changes use the canonical grade save/WAL contract. |
| **Storage (files)** | Django storage backends | DefaultStorage, S3, etc. via `DEFAULT_FILE_STORAGE` and per-field storage. | Already abstracted; avoid direct boto3 in app code. |
| **E-sign / video / maps** | Required when feature exists | Video: `communication.channels` / video_conferencing; e-sign/maps: add adapter when introduced. | Same pattern as payments/notifications. |

## Audit rules

1. **Payment:** All tenant payment flows use `finance.gateways.get_gateway(...)` (and optionally `policy=request.tenant_runtime.policy`). No `import stripe` or vendor SDK in views/services.
2. **Platform billing:** Webhook handlers live in `billing.processors`; config-driven processor selection. No Stripe-specific logic outside `StripeConnectProcessor`.
3. **Messaging:** Target: one `send_sms` / `send_notification` entry point that uses site/tenant config to choose provider. Replace any `twilio.Client` in the middle of flows with this.
4. **AI:** Target: one `generate_completion` / `get_embedding` (or similar) used by portal and automation; implementations in a dedicated module that talks to OpenAI/Azure/etc.

## Gaps to close (by priority)

- **SMS/email:** Done. Single path: `apps.communication.notification_service` (`send_email`, `send_sms`); adapters in `communication.providers`; evals and workflow_engine use it; no direct Twilio/SendGrid in views.
- **AI:** Confirm all LLM usage goes through a single orchestration layer (Phase 7); see `docs/architecture/ai_orchestration.md` when added.
- **OCR:** Done. All extraction via `apps.siteconfig.document_extraction.get_document_extraction_provider`; evals and finance use it; no direct pytesseract/cloud in app code.

## References

- `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` Part C2 (External Dependency Strategy).
- `apps/finance/gateways/base.py`, `apps/finance/gateways/registry.py`.
- `apps/billing/processors.py` (platform billing).
