# Migration Cloud — OCR for scanned / image-only PDFs

Migration Cloud reads **digital** PDFs (an exported transcript / fee statement /
roster with a real text layer) out of the box — `pdfplumber` + `pypdf`, pure
Python, no system binaries. That covers the common case and needs no setup.

**Scanned or photographed PDFs** (a photocopy — the page is an *image*, there is
no text to extract) additionally need Optical Character Recognition, which
requires two *system* binaries that pip cannot install:

- **Tesseract** — the OCR engine (`pytesseract` wraps it).
- **Poppler** — renders PDF pages to images (`pdf2image` wraps its `pdftoppm`).

Render's **native Python runtime** has no `apt` / root, so these can't be
`apt-get install`ed. Instead we vendor them from **conda-forge via micromamba**
into a project-local `.ocr-env/` during `build.sh` — no root required — behind a
single flag. The whole thing is **default-OFF and non-fatal**: nothing changes
until you opt in, and if the vendoring ever fails the deploy still succeeds with
OCR simply inert (scanned PDFs degrade to a clear "needs OCR" hint, never a 500).

## Enable it

1. Render Dashboard → **web** service → **Environment** → add
   `RMC_OCR_ENABLED` = `1`.
2. Repeat on the **`school-management-system-worker`** service (so async /
   Celery-driven ingest can OCR too). Keep the two in sync.
3. **Manual Deploy → "Clear build cache & deploy"** on the web service. The
   cache-clear forces `build.sh` to re-run and download the binaries; the first
   build is ~2–3 minutes slower. (The worker redeploys from the same commit.)
4. When the service is **Live**, upload a scanned PDF in Migration Cloud and
   confirm rows land.

To disable, set `RMC_OCR_ENABLED` back to `0` (or remove it) and redeploy.
Nothing else references the binaries, so OCR cleanly goes inert again.

## How it wires together

| Piece | Role |
|---|---|
| `RMC_OCR_ENABLED=1` | The single on/off switch. Read by **`build.sh`** (whether to vendor the binaries) **and** `pdf_extract.py::_try_ocr` (whether to attempt OCR). |
| `build.sh` | When the flag is `1`, a best-effort subshell (`set +e`, trailing `\|\| true`) curls micromamba and runs `micromamba create -p .ocr-env -c conda-forge tesseract poppler`. Any failure logs a WARNING and the deploy continues. |
| `apps/migration_cloud/pdf_extract.py::_ocr_paths` | At runtime, resolves the binaries: explicit env vars win, else auto-discovers `<repo>/.ocr-env/{bin,share/tessdata}`. |
| `apps/migration_cloud/pdf_extract.py::_try_ocr` | Returns `""` immediately unless the flag is `1`; otherwise renders pages via `pdf2image` (with the resolved `poppler_path`) and OCRs them via `pytesseract` (with the resolved `tesseract_cmd`). Every failure degrades to `""`. |
| `requirements.txt` | `pytesseract` + `pdf2image` — thin wrappers (Pillow-only deps), always safe to import; inert without the binaries. |

### Optional overrides

`_ocr_paths` honors these if you ever vendor the binaries elsewhere or the
auto-discovery of `.ocr-env` doesn't fit your layout:

- `RMC_OCR_TESSERACT_CMD` — absolute path to the `tesseract` binary.
- `RMC_OCR_POPPLER_PATH` — directory containing `pdftoppm`.
- `TESSDATA_PREFIX` — directory containing the `*.traineddata` language files.

## Troubleshooting

- **Scanned PDF still yields 0 rows after enabling.** Check the build log for
  `OCR ready: tesseract <version>`. If instead you see the WARNING that
  vendoring didn't complete, the conda-forge download failed (transient / mirror)
  — redeploy with cache clear. If the build shows OCR ready but extraction is
  still empty, the language data path may need pinning — set `TESSDATA_PREFIX` to
  `.ocr-env/share/tessdata` explicitly on both services.
- **Digital PDFs work, scanned don't, and the flag is off.** That's expected —
  OCR is only for image-only pages. Enable the flag as above.
- **Build got slower.** Only the *first* build after enabling downloads the
  binaries; subsequent builds reuse the vendored `.ocr-env` unless you clear the
  build cache.

## Why not Docker?

A Docker image could `apt-get install tesseract-ocr poppler-utils` directly, but
migrating the live web + worker services to Docker would mean re-provisioning
**every** system library the native runtime already supplies (Pango / Cairo /
GDK-Pixbuf for WeasyPrint, Node/npm for the WebGL globe build, etc.) — a large,
high-blast-radius change for a niche feature. Vendoring OCR into `.ocr-env` on
the existing native runtime keeps the blast radius at exactly one folder.
