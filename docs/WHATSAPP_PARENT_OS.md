# WhatsApp Parent OS — Operator Guide

**Wave H · v3.95.0 · 2026-05-26**

The Parent OS turns the existing outbound `WhatsAppIntegration` (Wave v2.76) into a **two-way conversational parent interface**. Parents can:

- Check fee balances
- Report a student absence
- Pull the latest report card
- Get today's homework summary
- Request a human callback
- Unsubscribe

The differentiator vs. consumer tools (FoondaMate) is institutional: messages are scoped to a school-issued Meta Business number, the inbound phone is matched against the tenant's guardian roster, and intents resolve against the tenant's actual records.

## Architecture

```
Meta Cloud API
     │  (POST /comms/whatsapp/webhook/)
     ▼
views_whatsapp_webhook.whatsapp_webhook
     │  1. verify_webhook (HMAC-SHA256, app-secret)
     │  2. feature-flag gate (whatsapp_parent_os_enabled)
     │  3. _parse_meta_webhook → [InboundMessage]
     ▼
whatsapp_parent_os.route_inbound_message
     │  • button_payload wins over body text
     │  • keyword classifier → intent
     │  • allowlist gate → degrade to UNKNOWN if disabled
     │  • per-phone rate limit (default 30/hour; STOP exempt)
     │  • placeholder_resolver fills {balance}, {student}, etc.
     ▼
OutboundIntent
     │
     ▼
WhatsAppIntegration.send_message (existing Wave v2.76 path)
     │  (uses tenant connector cascade or settings.WHATSAPP_*)
     ▼
Meta Cloud API
```

## Activation (per tenant)

1. **Meta Business setup** (operator concierge — out-of-band):
   - Verified WhatsApp Business Account.
   - Phone number with WhatsApp Business API enabled.
   - App secret + verify token recorded in tenant's `ServiceIntegration` row (`service_type=WHATSAPP`).
   - Webhook subscribed to `messages` field at `https://<tenant>.runmycampus.com/comms/whatsapp/webhook/`.
2. **Tenant flag flip**:
   - `SiteSettings.feature_settings.backend_feature_flags.whatsapp_parent_os_enabled = True`.
   - Optional: customize `whatsapp_parent_os_intent_allowlist` (subset of: `fee_balance`, `absence_report`, `report_card`, `homework`, `menu`, `help`, `human`, `stop`).
   - Optional: adjust `whatsapp_parent_os_rate_limit_per_hour` (default 30; STOP always exempt).

## Intent registry

| Intent | Template key | Example body |
|---|---|---|
| `fee_balance` | `parent_os_fee_balance_reply` | "Your fee balance is ₦145,000. Reply MENU for options." |
| `absence_report` | `parent_os_absence_acknowledged` | "Thank you. Marked Amara absent today. Get well soon." |
| `report_card` | `parent_os_report_card_link` | "Latest report card: <signed-link>. Expires in 7 days." |
| `homework` | `parent_os_homework_summary` | "Today's homework: Maths p.42, English essay 200 words." |
| `menu` | `parent_os_menu` | "Reply: FEES, ABSENT, REPORT, HOMEWORK, HUMAN." |
| `help` | `parent_os_help` | "Reply MENU to see options or HUMAN to reach a person." |
| `human` | `parent_os_handoff_human` | "Connecting you with the school office. Reply CANCEL to stop." |
| `stop` | `parent_os_unsubscribed` | "You are unsubscribed. Reply START to re-enable." |
| `unknown` | `parent_os_unknown_intent` | "Sorry, I didn't catch that. Reply MENU for options." |

Multi-locale keywords are recognized — `frais` (FR), `mensalidade` (PT), `ada` (Swahili) all resolve to `fee_balance`. See `_INTENT_KEYWORDS` in `apps/communication/whatsapp_parent_os.py`.

## Placeholder resolver

The kernel is pure — it does not query the database. The view (or any caller) passes a `placeholder_resolver: Callable[[InboundMessage, intent], dict[str, str]]` via `RoutingConfig`. Examples:

```python
def resolver(msg: InboundMessage, intent: str) -> dict[str, str]:
    if intent == "fee_balance":
        guardian = Guardian.objects.filter(phone=msg.from_phone).first()
        if guardian:
            return {"balance": format_money(guardian.outstanding_balance)}
    return {}
```

Failures in the resolver are swallowed (logged + body kept as the literal `{placeholder}` template). The kernel never raises into Meta's webhook.

## AI fallback (Wave H+1 — counsel-pending for live activation)

Long free-form parent messages that the keyword classifier can't resolve currently route to `UNKNOWN` (which sends the safe MENU response). Wave H+1 will add an AI fallback that classifies free-form text via `services.ai_helpers.classify_intent`. The boundary is enforced — direct `services.ai_gateway` imports are blocked by `scan_ai_gateway_boundary` (baseline 0).

## Privacy & audit

- Inbound phone numbers are SHA-256 hashed (`_hash_phone`) before any audit row.
- Bodies are never logged. Only intent + rate-limited flag.
- All outbound sends go through the existing `WhatsAppIntegration.send_message` path which already routes through circuit breaker + audit trail.

## Failure modes

| Condition | Behavior |
|---|---|
| Invalid HMAC signature | 403 (no leak) |
| Tenant flag disabled | 200 OK with `{"status": "disabled"}` (Meta requires 2xx) |
| Invalid JSON body | 400 |
| Send fails (network / Meta error) | Logged + swallowed; webhook still returns 200 so Meta doesn't retry-storm |
| Placeholder resolver raises | Logged + body sent with literal `{placeholder}` markers |

## Tests

`apps/communication/tests/test_whatsapp_parent_os.py` — 33 tests, all `SimpleTestCase`, no Meta network calls. Run:

```
python -m pytest apps/communication/tests/test_whatsapp_parent_os.py -x
```
