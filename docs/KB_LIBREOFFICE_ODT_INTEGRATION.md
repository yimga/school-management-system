# KB LibreOffice (ODT) Integration

## Goal

- **All KB documentation** sourced from `docs/*.md` (and any operator-facing markdown) is converted to **LibreOffice Writer document format (ODT)** so that:
  - Documents are **properly formatted** (headings, lists, tables, code blocks) and look **professional**.
  - Users can **download and open** them in LibreOffice (or Word) for offline use, printing, or editing.
- The web KB still shows the existing article view (HTML); the ODT is the **canonical downloadable document** with clear structure and directions.

## What We Need

### 1. Conversion tool

| Option | Pros | Cons |
|--------|------|------|
| **Pandoc** | Best MD→ODT quality, supports reference ODT for styles, tables, code blocks | Must install Pandoc on server / in Docker |
| **LibreOffice headless** | No extra binary if LibreOffice is already used for PDF conversion | Converts HTML→ODT; MD→HTML→ODT adds a step; heavier |
| **Python only (odfpy)** | No system dependency | Building ODT from Markdown manually is complex and fragile |

**Recommendation:** Use **Pandoc** for conversion. Add a **reference ODT** (optional) so all KB documents share the same heading styles, body font, and table of contents style.

### 2. Reference ODT (professional formatting)

- Create a single **reference.odt** in LibreOffice Writer with:
  - **Heading 1 / 2 / 3** styles (font, size, spacing)
  - **Body text** style
  - **Code** or “Source text” style for code blocks
  - Optional: **Table of contents** style
- Pass it to Pandoc: `pandoc input.md -o output.odt --reference-doc=reference.odt`
- Store it in the repo (e.g. `static/kb/reference.odt` or `docs/templates/reference.odt`) so the command and CI use the same styling.

### 3. Storage and model

- **KBArticle** has an optional **`odt_file`** field (FileField, `upload_to='kb/odt/%Y/%m/'`).
- When we run the “generate ODT” step (see below), we write the ODT to media storage and set `article.odt_file` to that file.
- This gives:
  - One canonical ODT per article.
  - “Download as Word (ODT)” on the article page that serves this file.

### 4. When to generate ODT

- **Option A – On import:** When `import_docs_to_kb` runs, after creating/updating each article, run MD→ODT and save to `odt_file`. Keeps ODT in sync with every import.
- **Option B – Separate command:** A management command `generate_kb_odt` that:
  - Iterates over all (or selected) KB articles that have `content` (markdown),
  - Converts each to ODT (Pandoc),
  - Saves to `article.odt_file`.
- **Option C – On demand:** First time a user clicks “Download ODT”, generate and cache. More complex (async or blocking); Option A or B is simpler for “all docs as ODT”.

**Recommendation:** Use **Option B** (separate command) so you can run it after `import_docs_to_kb`, and optionally run it in CI or after doc changes. Optionally call the same conversion from Option A so import can do both in one go.

### 5. KB UI

- On the **KB article page**, add a button: **“Download as Word (ODT)”** (or “Download for LibreOffice”).
- It links to a view that serves `article.odt_file` with a correct filename (e.g. `{slug}.odt`) and `Content-Disposition: attachment`.
- If `odt_file` is empty, either hide the button or show “ODT not generated; run `generate_kb_odt`.”

### 6. Good structure and “directions” in the document

- **Title:** Use the article title as the document title (Pandoc can take `--metadata title=...`).
- **Headings:** MD `#` / `##` / `###` become Heading 1/2/3 in the reference ODT.
- **Summary:** Optionally add the KB summary as a subtitle or first paragraph.
- **Tables:** MD tables are converted by Pandoc to Writer tables.
- **Code blocks:** Use a monospace/style from the reference ODT so they’re readable.
- **Table of contents:** Pandoc can add a TOC with `--toc`; optional but improves “directions” for long docs.

So: **proper formatting** comes from the reference ODT and Pandoc; **good directions** come from consistent heading hierarchy and optional TOC.

---

## Implementation Summary

1. **Model:** Add `odt_file` (FileField, null=True, blank=True) to `KBArticle`; run migrations.
2. **Command:** Add `generate_kb_odt` that:
   - Requires Pandoc on `PATH`.
   - For each article with `content`:
     - Writes `content` to a temp `.md` file.
     - Runs: `pandoc input.md -o output.odt [--reference-doc=...] [--toc] --metadata title="..."`
     - Saves `output.odt` to `article.odt_file` (e.g. via default_storage).
   - Supports `--article-slug=...` and `--all`.
3. **Import (optional):** In `import_docs_to_kb`, after creating/updating an article, call the same conversion helper so ODT is generated in the same run (or document that users should run `generate_kb_odt` after import).
4. **Download view:** New view that:
   - Takes `article_slug`, fetches `KBArticle`, checks `odt_file`;
   - Returns `FileResponse` (or redirect to media URL) with `Content-Disposition: attachment; filename="<slug>.odt"`.
5. **Template:** In `kb_article.html`, add “Download as Word (ODT)” button linking to the download view when `article.odt_file` is set.
6. **Reference ODT:** Add a minimal `reference.odt` (or document where to place it) and wire its path into the command.

---

## Issues and Mitigations

| Issue | Mitigation |
|-------|------------|
| **Pandoc not installed** | Document in README/ops doc; in Docker, add Pandoc to image; command checks for `pandoc` and exits with clear message if missing. |
| **Server/CI environment** | Run `generate_kb_odt` in CI after doc changes and commit ODT to repo, or run on deploy; or run only when “Download ODT” is first requested (on-demand with caching). |
| **Version skew** | If someone edits the ODT offline, it’s no longer in sync with MD. Policy: **MD (and HTML) are source of truth**; ODT is an export. Regenerating overwrites `odt_file`. Document this for operators. |
| **Large docs / many articles** | Conversion can be slow; run in background (Celery) or overnight. For many articles, `generate_kb_odt --all` can be batched. |
| **Links in ODT** | Internal links in Markdown (e.g. to other KB articles) can point to URLs. Pandoc can keep links; ensure they use absolute portal URLs if you want “open in browser” from the doc. |
| **Non-ASCII / RTL** | Pandoc and ODT handle UTF-8; test with your locale. RTL needs extra styling in reference ODT if required. |
| **Storage and cleanup** | Old ODT files in media when regenerating: use the same `upload_to` path and overwrite, or delete previous file on save; Django’s FileField doesn’t auto-delete old file on replace, so do it in the command or in model save if you replace. |
| **Permissions** | Download view should respect same access as article view (e.g. only authenticated users who can see the article can download ODT). |

---

## File Layout (suggested)

```
docs/
  KB_LIBREOFFICE_ODT_INTEGRATION.md   # This file
  templates/
    reference.odt                     # Optional: reference ODT for Pandoc

apps/portal/
  management/commands/
    import_docs_to_kb.py             # Existing; optionally trigger ODT after each article
    generate_kb_odt.py                # New: batch MD → ODT, set article.odt_file
  models_kb.py                        # Add odt_file to KBArticle
  views_kb.py                         # Add download_article_odt view
  urls_kb.py                          # Add route for download
templates/portal/
  kb_article.html                     # Add "Download as Word (ODT)" button
```

---

## Quick start (after implementation)

1. Install Pandoc (e.g. `apt-get install pandoc` / `brew install pandoc` / Windows installer from pandoc.org).
2. (Optional) Create and place `reference.odt` under `docs/templates/` or `static/kb/`.
3. Import docs: `python manage.py import_docs_to_kb [--overwrite]`.
4. Generate ODTs: `python manage.py generate_kb_odt --all`.
5. Open any KB article; click “Download as Word (ODT)” to get the document in LibreOffice format.

All documentation you put in the KB (from `.md` files) will then be available as properly formatted LibreOffice (ODT) documents with clear structure and directions.
