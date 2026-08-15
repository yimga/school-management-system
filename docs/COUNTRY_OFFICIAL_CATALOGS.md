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
returns the merged view for admin preview.

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

Idempotent and additive. See `apps/academics/data/official_catalogs/README.md`
for the file format and the honesty rule.

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
| Everywhere else | Curated mnemonic default (real codes only where a country publishes stable ones) | Representative regional calendar |

## The honesty rule

Only real, verifiable official codes go in `subject_codes`. Where a country
publishes no stable numeric codes, the shipped mnemonic default stands — a wrong
"official" code is worse than an honest mnemonic (the same reason `_to_alpha2`
returns `""` rather than a wrong guess). Extending coverage to a new country's
real data is a `<COUNTRY>.json` edit + one command, ordered by where real tenants
land — never a code change.
