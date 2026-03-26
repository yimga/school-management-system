# Service catalog (Zone A / Zone B)

Internal-first platform: Zone A = internal services and contracts; Zone B = external adapters. All external calls go through adapters; no view or core service imports vendor SDKs directly.

## Zone A — Internal services

| Service | Owner / module | API / contract | Events produced |
|---------|----------------|----------------|------------------|
| Notifications | `apps.communication.notification_service` | `send_email`, `send_sms`, `send_push`, `send_whatsapp` | — |
| Domain events | `apps.events.services` | `emit_event(event_type, payload, school_id=..., idempotency_key=...)` | Outbox consumed by tasks/webhooks |
| Payments (tenant) | `apps.finance.gateways` | `get_gateway(school, method_code)`, gateway `.charge()` etc. | — |
| Platform billing | `apps.billing.processors` | Processor interface; webhook routing by code | — |
| Workflow engine | `apps.siteconfig.workflow_engine` | Conditions + actions (notify, emit_event) | workflow.triggered (when configured) |
| Fee/invoice | `apps.finance.services` | `create_fee_invoices`, `create_payment_from_receipt`, `apply_payment` | invoice.created, payment.created |
| People | `apps.people` | Student/teacher/guardian CRUD; signals for critical tag, badges | student.created (signal) |
| AI orchestration | Single facade (see Phase 7) | One `generate_completion` / `get_embedding` entry point | — |
| Exchange rate | Finance API | GET `/api/v1/finance/exchange-rate` (required when reporting in multiple currencies) | Implemented; see `apps.api.views_v1.FinanceExchangeRateView`. |
| Document extraction (OCR) | `siteconfig.document_extraction` | `get_document_extraction_provider(method, tesseract_cmd)` | Evals marksheet + finance receipt; no direct vendor in app code. |

## Zone B — External adapters

| Capability | Adapter interface | Implementations | Config |
|------------|-------------------|-----------------|--------|
| SMS | `communication.providers.SMSProvider` | Twilio, AfricasTalking | SiteSettings.sms_provider, api_key, sender_id |
| Email | Django email backend | SMTP, SendGrid, etc. | Django EMAIL_*; SiteSettings.email_from_address |
| Push | `communication.channels.PushProvider` | FCM, web_push | Tenant integration (push) |
| WhatsApp | `communication.channels.WhatsAppProvider` | Meta Graph API | Tenant integration (whatsapp) |
| Payments (tenant) | `finance.gateways.base.BasePaymentGateway` | Stripe, PayStack, etc. | Policy payment_gateways |
| Platform billing | `billing.processors` base | Stripe Connect | Processor config |
| AI | Single orchestration → gateway | Ollama (chat), optional vLLM/LiteLLM (tasks) | Settings / env |

## Internal API governance

- **No direct vendor imports** in views or core services (payment, notification, AI). Use adapter interfaces.
- **Events**: Emit only from service layer; document new event types in `domain_events.md`.
- **Notifications**: All outbound SMS/email/push go through `communication.notification_service` (or evals wrapper that uses it).
- **Search**: Target read layer (e.g. OpenSearch) fed by events or sync; write path remains primary DB.

## References

- `docs/architecture/provider_abstraction_audit.md`
- `docs/architecture/domain_events.md`
- `docs/REDUCE_APIS_SCALE_WORKFLOWS.md`
