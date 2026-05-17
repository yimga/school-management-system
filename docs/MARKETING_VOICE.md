# RunMyCampus marketing voice

Editorial marketing copy for runmycampus.com follows these rules. Product and legal pages may be more formal; the home and verb-nav surfaces stay conversational.

## Tone

- **Honest:** Name trade-offs (migration effort, certification status, regional variance). No “10/10” or “world’s only” claims without evidence.
- **Operational:** Write for heads, bursars, teachers, parents, and IT leads — what happens on a Tuesday, not abstract “digital transformation.”
- **Warm, not cute:** Schoolhouse editorial (Source Serif 4, cream canvas). Avoid startup slang and exclamation piles.

## Structure

- **Headline:** One clear outcome (≤ 12 words when possible).
- **Subhead:** How the platform delivers it — concrete modules, not feature soup.
- **Proof:** Dashboard artifacts, timelines, or comparison rows — never stock-photo filler.
- **CTA:** Primary = Book a demo (`data-cta="demo"`). Secondary = deep link to module or persona page.

## Words we use

| Prefer | Avoid |
| --- | --- |
| School operating system / platform | All-in-one miracle suite |
| Tenant, campus, network | Instance (external audiences) |
| Register, fees collected, cutover | Synergy, leverage, disrupt |
| Governed, audit-friendly | Unlimited, magic |

## Personas (solutions/)

Each persona page (`/solutions/head/`, `/solutions/bursar/`, etc.) speaks in second person to that role. Bullets are verbs + outcomes, not feature names alone.

## Localization

User-facing strings go through `{% trans %}` / `gettext_lazy` in templates and `marketing_v3_surfaces.py`. Do not hardcode currency symbols in hero copy; pricing uses the currency switcher.

## Bell-clock brand

The bell-clock mark is the product spinner and favicon companion. Do not duplicate SVG geometry — use `{% include "components/_bell_clock_mark.html" %}`.

## Editorial advisor character

A subtle line-art figure paired with the bell-clock as the secondary recurring illustration. **Eight poses** available via the `pose` attr (default `intro`):

- `intro` — facing forward, holding a tablet at the waist. Home close-CTA, company page close, trust center close.
- `listening` — slight head-turn, tablet held at the side. Persona pages, why-switch migration timeline, 404 page.
- `explaining` — gesturing toward a small floating diagram. Demo page, pricing add-ons.
- `welcoming` — open-handed wave. Help center hero, global login discovery hero.
- `reviewing` — head bent over a chart with magnifier. Release notes hero, analytics surfaces.
- `thinking` — hand on chin with floating thought dots. FAQ, loading, "we're working on it" surfaces.
- `celebrating` — both hands gently raised with quiet confetti. Payment success, milestone surfaces.
- `pointing-up` — index finger raised with a tip dot. Help prompts, "did you know?" callouts, tooltips.

**Variants** (apply alongside `mkt-advisor-figure`): `--muted` (slate ink), `--on-dark` (ivory ink), `--brand` (tenant primary), `--alive` (perpetual subtle breathe), `--reveal` (one-shot fade-up), `--tiny` (icon-companion scale).

**Storybook:** Staff-only design-review page at `/siteconfig/dev/mascot/` (rendered by `apps/siteconfig/views_mascot_storybook.py`, protected by `staff_member_required`). Shows every pose × every variant + a sizes ladder, so changes can be reviewed in one glance.

**CI consistency:** `scripts/scan_advisor_consistency.py` (parallel to `scan_bell_clock_consistency`) flags any hand-rolled `<svg class="mkt-advisor ...">` outside the canonical partial. Add to the architectural-boundaries CI workflow alongside the bell-clock scanner.

The character is intentionally minimal: line-only, one colored element (the scarf, gradient terracotta), inherits ink via `currentColor`. Do not redraw — call `{% include "marketing/components/_advisor_character.html" with pose="…" size=200 %}` and let `.mkt-advisor-figure` handle entrance + float animation. Add `.mkt-advisor-figure--reveal` to layer a one-shot fade-in on the perpetual float. The figure suspends animation under `prefers-reduced-motion`.

The advisor is not named. They are the "campus advisor," a stand-in for the platform's role next to the school operator — not a mascot to be personified, not a character with a backstory.

**CSS lives in `static/css/rmc-bell-clock-product.css`** (loaded across all 5 shells), not in marketing-only CSS — so the advisor partial can render on shared surfaces like the 404 page and the help-center tenant view. Layout pairings (advisor-beside-content grids) stay in `static/marketing/css/marketing-v3-narrative.css` because they only apply on marketing pages.

**RTL:** `body.bidi-rtl` is set on the marketing surface when the active language is Arabic / Hebrew / Persian / Urdu. The advisor's side-column anchor flips automatically via `body.bidi-rtl .mkt-edt-close__figure { justify-self: end; }` (and siblings) so the figure sits on the trailing edge in RTL.

## Supported locales (marketing surface)

`LANGUAGES` in `config/settings.py` enumerates the locales the marketing surface ships translation catalogs for. Current set:

| Code      | Name                  | Marketing catalog status                                  |
| --------- | --------------------- | ---------------------------------------------------------- |
| `en`      | English               | Source-of-truth                                            |
| `es`      | Spanish               | AI-assisted draft — needs native review (~111 strings)     |
| `fr`      | French                | Stub (msgids only, msgstrs empty)                          |
| `pt-br`   | Brazilian Portuguese  | AI-assisted draft — needs native review (~111 strings)     |
| `de`      | German                | AI-assisted draft — needs native review (~49 strings)      |
| `it`      | Italian               | AI-assisted draft — needs native review (~49 strings)      |
| `ru`      | Russian               | AI-assisted draft — needs native review (~37 strings)      |
| `tr`      | Turkish               | AI-assisted draft — needs native review (~37 strings)      |
| `ja`      | Japanese              | AI-assisted draft — needs native review (~38 strings)      |
| `zh-hans` | Chinese (Simplified)  | AI-assisted draft — needs native review (~39 strings)      |
| `zh-hant` | Chinese (Traditional) | AI-assisted draft — needs native review (~37 strings)      |
| `hi`      | Hindi                 | AI-assisted draft — needs native review (~39 strings)      |
| `ar`      | Arabic (RTL)          | AI-assisted draft — needs native review (~38 strings)      |
| `pid`     | Pidgin English        | Stub                                                       |
| `sw`      | Kiswahili             | Stub                                                       |
| `ha`      | Hausa                 | Stub                                                       |
| `yo`      | Yoruba                | Stub                                                       |

Run `python manage.py i18n_review_status` for live per-locale coverage. Add `--strict --threshold=80` in CI when you want a hard gate that fails if any non-en locale drops below 80% translated.

### Operator workflow — adding or refreshing a locale

1. Add the entry to `LANGUAGES` in `config/settings.py`. Non-standard codes (e.g. `pid`, `sw`, `ha`, `yo`) also need a matching `EXTRA_LANG_INFO` block so the admin language switcher does not raise `KeyError`. Django built-ins (`es`, `pt-br`, `fr`, `de`, `ar`, `hi`, `zh-hans`, etc.) need no `EXTRA_LANG_INFO` entry.
2. Create `locale/<code>/LC_MESSAGES/django.po` with the standard header (see `locale/es/LC_MESSAGES/django.po` as a template). Codes with regions use Django's underscore form for the directory: `pt-br` → `locale/pt_BR/`.
3. Translate the marketing-critical msgids first (the ones in this doc's neighbourhood: hero, scale signal, switching moment, verb hubs, CTAs). Mark uncertain translations with a trailing `# fuzzy` flag for the translator's pass.
4. `python manage.py sync_i18n_catalog --compile` to merge in the rest of the discovered msgids (with empty `msgstr`s — they fall back to English) and write `django.mo`. Re-run after any subsequent translation edit.
5. Verify in the browser by setting the user's language preference (e.g. `?lang=es` if the language switcher is wired) or `Accept-Language: es`.

### Honesty principle for AI-assisted drafts

Translation files marked "AI-assisted draft" in their header MUST be reviewed by a native speaker before being treated as production translations. The infrastructure is shipped; the responsibility for fluency stays with humans.

### Language preference persistence

Four layers of priority, highest first:

1. **`User.preferred_language`** (`apps/accounts/models.py`) — set per user, applied on login via the `apply_preferred_language_on_login` signal in `apps/accounts/signals.py`. Writes `_language` to the session so `LocaleMiddleware` picks it up on the next request.
2. **Session `_language` key** — set by the language switcher in `templates/marketing/components/_language_switcher.html`, which POSTs to `set_language_persist` (`apps/accounts/views_i18n.py`). For authenticated users, this view ALSO writes to `User.preferred_language` so the choice survives logout. Anonymous users get session-only persistence + a `LANGUAGE_COOKIE` for cross-session continuity.
3. **`School.default_language`** (`apps/schools/models.py`, migration 0051) — tenant default. When an anonymous visitor lands on a tenant's marketing surface, this applies before Accept-Language. Operators set this in the tenant admin; default empty string means "fall through to platform default."
4. **`Accept-Language` header** — Django's standard fallback when no session/cookie/tenant default is present.

### Locale-aware pricing

`static/marketing/js/pricing-currency.js` uses `Intl.NumberFormat(activeLang, { style: "currency" })` when available, so numbers + decimal separators follow the active page language. `9,000` in `en-US` becomes `9.000` in `de-DE`, and the JPY column renders without decimals. The custom label ("Custom" for enterprise tier with no published price) is translated inline for the 13 active locales — see `customLabel()`.

### SEO / discoverability

- `hreflang` alternate links are emitted by `templates/partials/rmc_social_meta.html` for every page that includes it (which is every shell). It reads `hreflang_entries` from view context when set; otherwise enumerates `LANGUAGES` against `request.path` with a `?lang=<code>` suffix and a `x-default` fallback.
- `og:locale` meta tag already reflects `request.LANGUAGE_CODE`.
- The sitemap (`apps/schools/marketing_views.py::marketing_sitemap_xml`) emits verb-canonical URLs; per-entry hreflang is available via `_global_hreflang_entries()` for future expansion.

### RTL surfaces

Setting `LANGUAGES = [("ar", ...)]` or any RTL code triggers:
- `dir="rtl"` on `<html>` (via `LANGUAGE_BIDI` from Django's i18n context processor)
- `body.bidi-rtl` class for CSS scoping
- Advisor figure side-anchor flips via `body.bidi-rtl .mkt-*-figure { justify-self: end; }`
- Verify on real text: glyph shaping needs Noto Sans Arabic / system Arabic font fallback — already loaded via `font-family: var(--font-sans, Inter, system-ui, sans-serif)` (system-ui covers Arabic on macOS/iOS/Win).
