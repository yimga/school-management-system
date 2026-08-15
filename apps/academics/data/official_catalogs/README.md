# Country official catalogs

One JSON file per country holding a country's **real official** academic data —
ministry/board subject codes and (representative) term-date windows. Loading a
file writes into the region-shared `EducationSystemProfile.config`, the same
override layer `resolve_subject_code` and `resolve_term_windows` already read, so
every school in that country inherits it **without a code change or deploy**.

This is the "pure data population through the same rows and tables" completion:
add a country's real codes by dropping in a file and running one command.

## Import

```bash
python manage.py import_country_official_catalog                 # this whole directory
python manage.py import_country_official_catalog --file KE.json  # one file
python manage.py import_country_official_catalog --dry-run       # report only, write nothing
```

The import is **idempotent** (re-running changes nothing) and **additive**
(config keys a catalog does not mention are preserved).

## File shape

```json
{
  "country": "KE",
  "sub_system": "",
  "source": "KNEC KCSE subject codes",
  "notes": "What is real vs representative — be honest here.",
  "subject_codes": { "english": "101", "mathematics": "121" },
  "term_windows": [[1, 5, 4, 5], [5, 2, 8, 5], [8, 28, 11, 25]]
}
```

- `country` — ISO alpha-2 or alpha-3.
- `sub_system` — optional education sub-system code (blank = the country default).
- `subject_codes` — subject name → code. Names match **case-insensitively** at
  resolve time. Use the **real official board/ministry codes**.
- `term_windows` — a single list of `[start_month, start_day, end_month, end_day]`
  for the country's term structure. These are almost always **representative**
  (dates are set annually and per-school), so say so in `notes`; each school
  confirms or adjusts its own real dates in-app.
- At least one of `subject_codes` / `term_windows` is required.

## Honesty rule

Only put **real, verifiable** official codes in `subject_codes`. Where a country
publishes no stable numeric codes, leave it to the shipped mnemonic default
rather than inventing one — a wrong "official" code is worse than an honest
mnemonic. Say what is real vs representative in `notes`.

## Shipped catalogs

- `KE.json` — real KNEC/KCSE numeric subject codes + representative Jan 3-term calendar.
- `IN.json` — real CBSE numeric subject codes + representative Apr 2-semester calendar.
