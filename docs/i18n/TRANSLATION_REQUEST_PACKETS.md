# Translation Request Packets

**Purpose:** for the 4 African locales (`yo` Yoruba, `ha` Hausa, `sw` Swahili, `pid` Nigerian Pidgin) currently at 0% translation coverage, this directory holds operator-facing packets — one per locale — ready to hand to a native-speaker translator.

The codebase intentionally does **not** ship AI-drafted translations for these languages. The cultural specificity of school-domain vocabulary (terms for "term", "form teacher", "guardian", "bursar", "report card") varies sharply within each language community; a bad AI draft would be worse than the English fallback because users would accept a wrong term as canonical.

## The 4 packets

| Locale | Packet | Source-locale count | Target context |
|---|---|---|---|
| `yo` (Yoruba) | [translation_requests/yo.md](translation_requests/yo.md) | 111 strings | West Africa private schools, Nigeria primary corridor |
| `ha` (Hausa) | [translation_requests/ha.md](translation_requests/ha.md) | 111 strings | West Africa private schools, Nigeria / Niger corridor |
| `sw` (Swahili) | [translation_requests/sw.md](translation_requests/sw.md) | 111 strings | East Africa private schools, Kenya / Tanzania corridor |
| `pid` (Nigerian Pidgin) | [translation_requests/pid.md](translation_requests/pid.md) | 111 strings | Pan-Nigeria operator-facing copy |

## What a translator receives

Each packet has:

- **Brand voice notes** (luxury / editorial / school-management-domain) extracted from [MARKETING_VOICE.md](../MARKETING_VOICE.md).
- **One row per string:** English source + brief context (where it appears: nav / CTA / hero / pricing / footer) + a blank target column for the translation.
- **Plural-form note:** each locale's `Plural-Forms:` header is preloaded in the `.po` file from `apps/siteconfig/i18n_catalog_builder.py`; the translator just fills `msgstr` (and `msgstr[N]` when the string has a plural).
- **Sign-off field:** translator name + date + native-speaker affirmation → written into `var/i18n-review-status.json` once the packet round-trips back.

## Operator workflow

1. Hand the packet to the translator (Markdown is portable; can be CSV-exported via `python scripts/export_translation_request.py <locale>` — TODO operator-side tooling).
2. Translator fills the right-hand column in a copy of the packet.
3. Operator copies the translations into `locale/<code>/LC_MESSAGES/django.po`.
4. `python manage.py sync_i18n_catalog --compile` regenerates the `.mo` files.
5. `python manage.py i18n_review_status --mark-reviewed <locale> --reviewer "<name>" --notes "<short>"` records sign-off.
6. CI gate `scan_locale_coverage.py` picks up the new count on the next run.

## Why not pre-fill with machine translation?

- **Hallucination cost** in the school domain is high: misrendering "term" / "trimester" / "semester" / "session" causes scheduling confusion.
- **Compromised brand voice:** the editorial luxury tone in [MARKETING_VOICE.md](../MARKETING_VOICE.md) doesn't survive round-tripping through cheap MT.
- **Pidgin in particular** has no standard orthography that a translator-without-domain-knowledge would expect; for that locale, ask a regional pilot school's English-teacher or admin instead of a generic translator.

## Status of the 11 AI-drafted locales

For locales that already shipped AI-assisted drafts (es / pt-br / de / it / ru / tr / ja / zh-hans / zh-hant / hi / ar), the audit trail lives in [`var/i18n-review-status.json`](../../var/i18n-review-status.json) and is queried via `python manage.py i18n_review_status`. Each locale's draft is marked `needs-native-review` until an operator flips it to `production-ready` via the management command.

French (`fr`) is a transition case: 96 strings landed AI-drafted (operator-readable French; the LLM produces working French at editorial register) in batch 1271 — same `needs-native-review` status as the other AI-drafted locales.
