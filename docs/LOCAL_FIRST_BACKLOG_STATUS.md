# Local-First / Cost-Control Backlog — Status

Status of the improvements that reduce paid APIs and external dependencies.  
*(Codex was working on these before timeout issues.)*

---

## Done (before or in this pass)

| Item | Status | Notes |
|------|--------|--------|
| **Remove external QR API** | Done | Digital IDs use local `_qr_png_data_uri()` in `apps/portal/views.py` with `qrcode[pil]` (no api.qrserver.com). |
| **Make AI strictly local-first by default** | Done | `DEFAULT_PROVIDER_ORDER` is `["ollama", "rules"]`; `general_chat` gateway tiers are `["ollama", "rules"]` only; legacy `gemini` in `AI_PROVIDER_PREFERENCE` is ignored. |
| **Default virtual classes to Jitsi** | Done | `VirtualClassroom.provider` and `VideoConferenceService` default to Jitsi. Migration `0013_virtualclassroom_default_jitsi.py` updates DB default. Zoom remains optional. |
| **Fix Zoom integration health check** | Done | `ZoomIntegration.get_token()` added in `apps/communication/integrations.py`; `check_health()` now uses it instead of calling a missing method. |
| **Enforce free OCR first** | Done | Receipt verification defaults to `pattern` in `apps/siteconfig/models.py` and `apps/finance/receipt_verification.py`. Paid cloud OCR is opt-in. |
| **Self-host HTMX (school finder)** | Done | `templates/schools/partials/school_finder_bento.html` loads `{% static "js/htmx.min.js" %}`. `static/js/htmx.min.js` vendored (1.9.12). |
| **Global seeding without network** | Done | `--skip-unesco` in `apps/siteconfig/management/commands/seed_global_brand_registry.py`; use in CI/staging for baseline-only seeding. |
| **Self-host Bootstrap + fonts** | Done | Bootstrap 5.3.3 and Bootstrap Icons in `static/vendor/`, Inter variable in `static/fonts/inter/`. `portal_base.html` and `base.html` use `{% static %}` only (no CDN). |
| **Reduce weather API traffic** | Done | `WEATHER_CACHE_TTL_SECONDS` = 900, stale = 3600. `show_header_context_weather` defaults to `False` in `default_backend_feature_flags` and observability/context. |
| **API cost guardrails in API Center** | Done | `integration_catalog.py`: per-integration `daily_cap`, `cooldown_seconds`, `fallback_channel`; `get_guardrail_config()` and `check_integration_guardrail()` for call sites. |
| **Payment default away from Stripe** | Done | `RecurringPaymentSubscription.payment_processor` default `'manual'`; `process_payment()` only runs Stripe when `payment_processor == 'stripe'`. Migration `0044_*`. |

---

## Summary

- **All items complete.** AI local-first, QR local, Jitsi default, Zoom health fix, free OCR first, HTMX vendored, Bootstrap/fonts/Inter vendored, weather TTL increased and off by default, API Center guardrails (caps, cooldowns, fallback), payment default manual with Stripe opt-in.

**Follow-ups (done):**
- React, React-DOM, TanStack Query, Zod vendored under `static/vendor/react/`; `portal_base.html` uses `{% static %}` (no unpkg).
- Scanner-path hardening: `config.middleware.BlockScannerPathsMiddleware` returns 404 for `/.git`, `/terraform*`, `/wp-config*`, `/env.js`, `/config.js`, and other common probe paths. See `docs/SCANNER_LOGS_AND_HARDENING.md`.
