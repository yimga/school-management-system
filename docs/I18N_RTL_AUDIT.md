# i18n + RTL Audit (P11)

**Audit date:** 2026-05-17
**Pillar:** P11 — 12-pillar platform audit (i18n / RTL / deliverability slice)
**Locale count:** 17

This document is the **flattened locale state** + RTL coverage audit. Update when `LANGUAGES` in `config/settings.py` changes or when a translator delivers a new `.po` cycle.

---

## 1. Locale matrix

| Code | Language | Direction | Translation strategy | Notes |
|---|---|---|---|---|
| `en` | English | LTR | Source — passthrough (8403 msgids) | Authoritative; all msgids originate here |
| `es` | Spanish | LTR | AI-assisted draft | Native-speaker review required before production (MARKETING_VOICE.md) |
| `fr` | French | LTR | Stub | Falls back to English; 0 translated |
| `pt-br` | Portuguese (Brazil) | LTR | AI-assisted draft | Native-speaker review required |
| `de` | German | LTR | AI-assisted draft | Native-speaker review required |
| `it` | Italian | LTR | AI-assisted draft | — |
| `ru` | Russian | LTR | AI-assisted draft | — |
| `tr` | Turkish | LTR | AI-assisted draft | — |
| `ja` | Japanese | LTR | AI-assisted draft | — |
| `zh-hans` | Chinese (Simplified) | LTR | AI-assisted draft | — |
| `zh-hant` | Chinese (Traditional) | LTR | AI-assisted draft | — |
| `hi` | Hindi | LTR | AI-assisted draft | — |
| `ar` | Arabic | **RTL** | AI-assisted draft | `LANGUAGE_BIDI` triggers `body.bidi-rtl`; layout flip required |
| `pid` | Nigerian Pidgin | LTR | Stub | Cultural relevance for WAfrica corridor |
| `sw` | Swahili | LTR | Stub | Cultural relevance for EAfrica corridor |
| `ha` | Hausa | LTR | Stub | Cultural relevance for WAfrica corridor |
| `yo` | Yoruba | LTR | Stub | Cultural relevance for WAfrica corridor |

**Source:** `config/settings.py::LANGUAGES`, verified via `python manage.py shell -c "from django.conf import settings; print(len(settings.LANGUAGES))"` → 17.

**On-disk locale directories:** all 17 present under `locale/<code>/LC_MESSAGES/`.

---

## 2. Catalog freshness

| Gate | Mechanism |
|---|---|
| **Msgid extraction** | `python manage.py sync_i18n_catalog --compile` walks the source tree, extracts every `{% trans %}` / `{% blocktrans %}` / `_(...)` / `gettext_lazy(...)`, merges into every `.po`, compiles `.mo`. |
| **Freshness check** | [scripts/verify_i18n_catalog_fresh.py](../scripts/verify_i18n_catalog_fresh.py) — diffs scanned msgids vs `locale/en/LC_MESSAGES/django.po`. Exits 1 when code introduces new strings that haven't been catalog-synced. **Required to pass before merge.** |
| **Coverage drift** | [scripts/scan_locale_coverage.py](../scripts/scan_locale_coverage.py) — per-locale translated-count regression gate. Stub locales (yo/ha/sw/pid/fr) legitimately ship 0 translated and fall back to English; the gate trips only when a locale that USED to have translations regresses. |
| **Plural forms** | Each `.po` carries its locale's `Plural-Forms:` header. Validated implicitly during `.mo` compile. |

---

## 3. Language resolution priority

Per memory `marketing_mascot_poses_i18n_persistence_v3_12`:

1. **`User.preferred_language`** (CharField on User; persists across sessions)
2. **Session `_language`** (set by `set_language_persist` view at `/i18n/setlang/persist/`)
3. **`School.default_language`** (per-tenant default; migration `schools/0051`)
4. **`Accept-Language`** header from browser

Login signal `apply_preferred_language_on_login` writes user pref into session on every successful login.

**Hreflang emission:** [templates/marketing/partials/rmc_social_meta.html](../templates/marketing/partials/rmc_social_meta.html) emits `<link rel="alternate" hreflang="...">` for every supported language (uses view-context `hreflang_entries` if set, else enumerates `LANGUAGES` with `?lang=` + `x-default`).

---

## 4. RTL (Arabic) coverage

| Layer | Status | Mechanism |
|---|---|---|
| **Direction attribute** | ✓ | `<html dir="{% if LANGUAGE_BIDI %}rtl{% else %}ltr{% endif %}">` |
| **Body class** | ✓ | `body.bidi-rtl` toggled in `base_marketing.html` and dashboard shells |
| **Logical CSS properties** | ✓ where present | `margin-inline-start/end`, `padding-inline-start/end`, `text-align: start/end` used in `static/css/design-tokens.css` and component grammar |
| **Mascot side-anchor** | ✓ | [templates/marketing/components/_advisor_character.html](../templates/marketing/components/_advisor_character.html) flips for RTL |
| **Marketing pricing locale-aware numbers** | ✓ | `Intl.NumberFormat` reading `<html lang>` (memory v3.13) |
| **400% zoom layout for `ar`** | ⚠ Partial | Axe smoke covers visual tests up to 200%; explicit 400% zoom matrix queued for [`apps/compliance/tests/test_a11y_axe_smoke.py`](../apps/compliance/tests/test_a11y_axe_smoke.py) extension. |
| **RTL render check in CI** | ⚠ Partial | [scripts/verify_rtl_major_templates.py](../scripts/verify_rtl_major_templates.py) lints major templates; full Playwright `ar` render snapshot lives in [marketing-visual-truth.yml](../.github/workflows/marketing-visual-truth.yml) for marketing surface only — dashboard RTL snapshots queued. |

---

## 5. Deliverability

| Control | Implementation |
|---|---|
| **DKIM signing** | [apps/communication/email_signing.py](../apps/communication/email_signing.py) — gate refuses production with `console.EmailBackend`; requires anymail backend (Mailgun / SendGrid / Postmark / SES) + DKIM private key on tenant. |
| **SPF / DMARC** | TXT records published per tenant sending domain. Validated outside the repo (`dig _dmarc.<domain> TXT`). |
| **Bounce / complaint webhooks** | [apps/integrations_marketplace/email_backend.py](../apps/integrations_marketplace/email_backend.py) ingests provider bounce + complaint webhooks. |
| **List-Unsubscribe-Post** | Header emitted by all marketing-channel sends per CAN-SPAM. Transactional channel exempt. |
| **Channel separation** | Transactional vs. marketing routed through separate provider configs (CAN-SPAM/GDPR Art. 6 lawful-basis registry). |
| **SMS rate caps** | Per-tenant cap in `school.settings["sms_rate_limit_per_minute"]`. |

**Honest carve-out:** real-world deliverability (inbox vs. spam folder) is a function of warming, content, sender reputation — repo controls only the technical headers + signing. Operator runs `python scripts/check_no_committed_env.py` plus external tools (Mail-tester, GlockApps) for ongoing inbox-placement audit.

---

## 6. Daily operator drill

```bash
python manage.py sync_i18n_catalog --compile         # refresh catalogs on every wave
python scripts/verify_i18n_catalog_fresh.py          # zero-tolerance gate (must exit 0)
python scripts/scan_locale_coverage.py               # per-locale drift detection
python manage.py i18n_review_status --strict --threshold 95   # production-readiness threshold
python scripts/verify_rtl_major_templates.py         # template-level RTL audit
```

---

## 7. Honest carve-outs

- **AI-assisted drafts vs. production-ready translations** — 9 locales (es/pt-br/de/it/ru/tr/ja/zh-hans/zh-hant/hi) are AI-drafted and have not had native-speaker review. Marked in MARKETING_VOICE.md; production-ready threshold = 95% reviewed + sign-off recorded in `var/i18n-review-status.json`.
- **Stub locales (fr/yo/ha/sw/pid)** — present in LANGUAGES with their language-info dirs but ship with 0 translated; intentional. They fall back to English; the cultural relevance is in the OPTION (the dropdown shows them), the translation pipeline is staffed when a region commits.
- **400% zoom + dashboard-shell RTL Playwright snapshot** — declared above as ⚠ Partial; queued for the next a11y wave.
