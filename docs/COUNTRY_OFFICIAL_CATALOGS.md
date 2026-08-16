# Country academic data: representative defaults → ministry-exact, no deploy

The platform ships **representative** academic defaults for every sovereign
country — term-date calendars, subject codes, admission templates, TVET trades.
Two phrases in the "honest remaining line" — *ministry-exact term dates* and
*official numeric board codes for every country* — are not static datasets: term
dates are set **annually and per-school**, and most countries publish **no stable
numeric subject codes**. So the goal is not to hardcode data that does not exist;
it is to make reaching a country's real data **pure data population, never a code
change**. That is delivered in three parts.

## 1. Subject codes have the term-window override cascade

`apps.academics.country_subject_codes.resolve_subject_code` resolves in four
layers — the read-side twin of `country_term_calendars._lookup_windows`:

```
per-school   settings['subject_codes'][name]          (this school's edit)
  ▸ per-profile config['subject_codes'][name]         (region-wide, one edit)
  ▸ curated _NATIONAL_SUBJECT_CODES[country][name]     (shipped official codes)
  ▸ deterministic mnemonic fallback                   (every subject gets SOME code)
```

An operator enters a country's real codes **once** at the profile level
(`EducationSystemProfile.config['subject_codes']`) and every school in that
country inherits them — no code change, no deploy. `effective_subject_code_map`
returns the merged view; `subject_code_report(school)` returns the per-subject
resolved code + which layer supplied it (`school` / `profile` / `curated` /
`mnemonic`) + drift flags, and is surfaced read-only on the academics hub so an
admin can *see* which codes are real and which are generated placeholders.

### Propagating an import to already-seeded subjects (resync)

`Subject.code` is a stored column set at seed time, and report cards render the
stored value — so importing a country's real codes into the profile config reaches
**new** subjects immediately, but a subject seeded *before* the import keeps its old
default code. `backfill_subject_codes` only fills **blank** codes, so it does not
touch those. `resync_subject_codes(school)` closes the gap: it re-resolves every
subject and updates the ones whose stored code is a recognizable **system default**
(the curated value or the mnemonic) to the freshly-imported code — while leaving an
admin's explicit edit and an already-correct code untouched. Run it after an import:

```bash
python manage.py backfill_country_baseline --resync-codes            # every school
python manage.py backfill_country_baseline --school <id> --resync-codes --dry-run
```

The importer prints this exact follow-up command whenever an import changes codes,
so the propagation step is never silently skipped.

## 2. Representative calendars are labelled and confirmable

Seeded term calendars are representative approximations, not ministry truth.
`apps.academics.academic_calendar` records, per school, **which cascade layer** a
seeded calendar came from (`term_windows_source`): a *curated / even-split*
calendar is a representative default; a *school / profile* override is real
admin/operator data. A representative calendar surfaces a
confirm-before-go-live advisory (score-neutral, non-blocking) in the academics
hub and `setup_health_score`; a one-click POST to `academics:calendar_confirm`
attests the dates. Confirming is an attestation, never a lock — dates stay
editable. Schools seeded before this shipped read as *not representative* so no
live tenant is retroactively nagged.

## 3. Official catalogs load real data with no deploy

`apps/academics/data/official_catalogs/<COUNTRY>.json` holds a country's real
official data. `manage.py import_country_official_catalog` writes it into the
region-shared `EducationSystemProfile.config` — the layer (1) reads — so it is
live for every school in the country immediately.

```bash
python manage.py import_country_official_catalog            # shipped catalogs
python manage.py import_country_official_catalog --file apps/academics/data/official_catalogs/KE.json
python manage.py import_country_official_catalog --dry-run  # report only
```

Idempotent and additive. Every applied import is **conflict-aware** — the summary
(and `--dry-run`) reports each code as *added* or *overwritten* with the exact
`old → new` diff, so replacing a pre-existing code is never silent — and records a
**provenance** entry (`source` + timestamp + counts) into
`config['catalog_provenance']` for the audit trail. See
`apps/academics/data/official_catalogs/README.md` for the file format and the
honesty rule.

### Multiple term structures per country (`term_windows_by_count`)

`config['term_windows']` holds a **single** list of `[sm, sd, em, ed]` tuples for a
country's term structure. A country whose schools run **different** term structures
(e.g. a 2-semester sector alongside a 3-trimester one) uses the optional
`term_windows_by_count` key — an object keyed by term count, each value a
`term_windows` list of exactly that length:

```json
"term_windows_by_count": {
  "2": [[9, 1, 1, 31], [2, 1, 6, 30]],
  "3": [[9, 1, 12, 15], [1, 8, 4, 10], [4, 25, 7, 25]]
}
```

`country_term_calendars._lookup_windows` prefers the `term_windows_by_count` entry
matching the school's requested term count (at every layer — per-school
`settings`, per-profile `config`, and curated `_TERM_CALENDARS_BY_COUNT`), then
falls back to the single `term_windows`. It is fully additive: a catalog or config
without the key behaves exactly as before, so a school on the other structure no
longer silently falls through to the even-split default when its real windows are
supplied. Most countries need only `term_windows`.

To onboard a new country without starting from a blank file, export a pre-filled
template from the curated defaults, edit in the official values, then import it —
the demand-driven round-trip:

```bash
python manage.py export_country_catalog_template --country CM --out CM.json  # export -> edit -> import
python manage.py export_country_catalog_template --all --out-dir templates/  # every curated country
```

### What ships as real vs representative

| Country | Subject codes | Term windows |
|---|---|---|
| Kenya (`KE.json`) | **Real** KNEC/KCSE numeric | Representative Jan 3-term |
| India (`IN.json`) | **Real** CBSE numeric | Representative Apr 2-semester |
| Cameroon (`CM.json`) | **Real** GCE Board numeric (O-Level 05xx + A-Level 07xx, camgceb.org) | Representative Sept 3-term (from MINESEC 2025/2026 calendar) |
| Everywhere else | Curated mnemonic default (real codes only where a country publishes stable ones) | Representative regional calendar |

## The honesty rule

Only real, verifiable official codes go in `subject_codes`. Where a country
publishes no stable numeric codes, the shipped mnemonic default stands — a wrong
"official" code is worse than an honest mnemonic (the same reason `_to_alpha2`
returns `""` rather than a wrong guess). Extending coverage to a new country's
real data is a `<COUNTRY>.json` edit + one command, ordered by where real tenants
land — never a code change.
