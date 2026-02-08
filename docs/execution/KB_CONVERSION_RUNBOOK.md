# KB Conversion Runbook

## Objective

Produce clean, professional KB deliverables in both formats:
- `ODT` for LibreOffice workflows.
- `DOCX` for Word workflows.

## Preconditions

- KB articles are imported (`status=PUBLISHED`, non-empty `content`).
- At least one converter is available:
- `pandoc` (preferred)
- or LibreOffice (`soffice`)

Optional templates:
- `docs/templates/reference.odt`
- `docs/templates/reference.docx`

## Commands

### 1) Dry run

```bash
python manage.py generate_kb_odt --all --formats odt,docx --dry-run
```

### 2) Full conversion

```bash
python manage.py generate_kb_odt --all --formats odt,docx --engine auto --overwrite
```

### 3) Single article

```bash
python manage.py generate_kb_odt --article-slug teacher-onboarding --formats odt,docx --engine pandoc
```

### 4) Custom export folder

```bash
python manage.py generate_kb_odt --all --formats odt,docx --export-dir ./artifacts/kb
```

### 5) Styled output

```bash
python manage.py generate_kb_odt \
  --all \
  --formats odt,docx \
  --engine pandoc \
  --reference-doc docs/templates/reference.odt \
  --reference-docx docs/templates/reference.docx \
  --toc
```

## Validation checklist

- Command exits with `Errors: 0`.
- Export directory contains `.odt` and `.docx` per article.
- ODT opens in LibreOffice without warnings.
- DOCX opens in Word/LibreOffice with preserved headings and tables.
- Spot-check 3 long docs for TOC, heading depth, and code block rendering.

## Troubleshooting

- `Pandoc not found`: install pandoc or run `--engine libreoffice`.
- `LibreOffice not found`: install LibreOffice or set `SOFFICE_PATH`.
- Corrupt output: re-run with `--overwrite`; verify template file integrity.
- Missing files in export folder: set explicit `--export-dir` and check permissions.

## Recommended release sequence

1. `import_docs_to_kb --overwrite` (if source markdown changed)
2. `generate_kb_odt --all --formats odt,docx --engine auto --overwrite`
3. Sanity-check downloads from KB article pages
4. Archive generated artifacts with release tag
