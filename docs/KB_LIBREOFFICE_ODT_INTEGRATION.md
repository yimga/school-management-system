# KB Document Conversion (ODT + DOCX)

## Scope

The KB conversion pipeline now supports both output standards:
- `ODT` as the canonical LibreOffice format attached to `KBArticle.odt_file`.
- `DOCX` as an export artifact for Microsoft Word compatibility.

Source of truth remains Markdown content (`KBArticle.content` and imported `docs/*.md`).

## Conversion engines

- `pandoc`: direct Markdown -> ODT/DOCX with optional reference style docs.
- `libreoffice`: Markdown -> HTML -> ODT/DOCX using headless LibreOffice.
- `auto`: prefers `pandoc`, falls back to LibreOffice.

## Command

Use `generate_kb_odt` (kept for backward compatibility) with format selection:

```bash
python manage.py generate_kb_odt --all --formats odt,docx
```

Important flags:
- `--article-slug <slug>`: convert one article only.
- `--engine auto|pandoc|libreoffice`: select converter.
- `--reference-doc <path.odt>`: ODT style template for Pandoc.
- `--reference-docx <path.docx>`: DOCX style template for Pandoc.
- `--toc`: include table of contents (Pandoc path).
- `--overwrite`: regenerate existing ODT/file exports.
- `--dry-run`: list work without conversion.
- `--export-dir <path>`: where generated `.odt/.docx` files are written.

Default export directory:
- `<MEDIA_ROOT>/kb/generated/`

## Professional formatting guidance

Use style templates in `docs/templates/`:
- `docs/templates/reference.odt`
- `docs/templates/reference.docx`

Recommended style setup:
- Heading hierarchy (`Heading 1/2/3`) with clear spacing.
- Body text style optimized for print and PDF.
- Code style with monospace font and subtle background.
- Table style with visible header contrast and grid lines.
- Header/footer with school identity and page numbering.

## Data flow

1. Markdown content is converted per requested format.
2. ODT output is attached to `KBArticle.odt_file`.
3. ODT and DOCX artifacts are written to export directory.
4. KB download endpoints continue serving:
- `/kb/<slug>/download/odt/`
- `/kb/<slug>/download/docx/` (converted from ODT when requested)

## Operational policy

- Markdown is authoritative.
- Regeneration can overwrite prior ODT and exported DOCX files.
- Keep templates versioned in repo for reproducible output.
