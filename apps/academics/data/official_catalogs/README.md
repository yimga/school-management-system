# Country official catalogs

One JSON file per country holding a country's **real official** academic data —
ministry/board subject codes and (representative) term-date windows. Loading a
file writes into the region-shared `EducationSystemProfile.config`, the same
override layer `resolve_subject_code` and `resolve_term_windows` already read, so
every school in that country inherits it **without a code change or deploy**.

This is the "pure data population through the same rows and tables" completion:
add a country's real codes by dropping in a file and running one command.

## Export a starting template (don't start from a blank file)

Pre-fill a country's file from the shipped curated defaults (real subject
taxonomy + representative windows), then edit in the official values:

```bash
python manage.py export_country_catalog_template --country CM --out CM.json
python manage.py export_country_catalog_template --all --out-dir templates/   # every curated country
```

The exported `subject_codes` are readable mnemonics (or the real KE/IN codes) —
replace them with your official board/ministry codes — and `term_windows` are
representative. Then import the edited file.

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
- `term_windows_by_count` — *optional*. An object keyed by term count
  (`"2"`, `"3"`, …), each value a `term_windows` list of exactly that length. Use
  it when a country genuinely runs **more than one term structure** (e.g. a
  2-semester sector alongside a 3-trimester one). The resolver prefers the entry
  matching a school's requested term count, then falls back to the single
  `term_windows`. Most countries need only `term_windows`.
- At least one of `subject_codes` / `term_windows` / `term_windows_by_count` is required.

## Honesty rule

Only put **real, verifiable** official codes in `subject_codes`. Where a country
publishes no stable numeric codes, leave it to the shipped mnemonic default
rather than inventing one — a wrong "official" code is worse than an honest
mnemonic. Say what is real vs representative in `notes`.

## Shipped catalogs

- `KE.json` — real KNEC/KCSE numeric subject codes + representative Jan 3-term calendar.
- `IN.json` — real CBSE numeric subject codes + representative Apr 2-semester calendar.
- `CM.json` — real Cameroon GCE Board subject codes (O-Level 05xx + A-Level 07xx,
  from camgceb.org) + representative Sept 3-term calendar derived from the MINESEC
  2025/2026 national school-year calendar.
