# Marksheet OCR & Manual Review

## 1. Verify the Tesseract runtime

1. Install Tesseract before the OCR helpers can run:
   - **Windows**: download the installer from https://github.com/tesseract-ocr/tesseract/releases and add the installation folder (e.g., `C:\Program Files\Tesseract-OCR`) to your `PATH`.
   - **macOS**: `brew install tesseract`.
   - **Linux**: `sudo apt install tesseract-ocr` (or the equivalent for your distro).
2. Run `tesseract --version` on the host to confirm the binary is reachable. The teacher upload page also displays whether the backend currently resolves the command.
3. If the binary is not on `PATH`, set the absolute path via:
   - The environment variable `MARKSHEET_OCR_COMMAND`, or
   - The **Site Settings → Marksheet OCR & Mobile Upload → Tesseract command** field (this overrides the env var for the school).

## 2. Admin controls

In **Site Settings → Marksheet OCR & Mobile Upload** you can:

| Control | Purpose |
| --- | --- |
| Enable marksheet OCR uploads | Turns the OCR card on/off for teachers. |
| OCR confidence threshold (%) | The minimum confidence before marks are applied automatically. |
| Force manual review | When enabled, parsed sheets always require confirmation even if the confidence is high. |
| Allow mobile uploads | Reveals the “choose or capture photo” hint for teachers on phones. |
| Tesseract command | Path to the binary when the host doesn’t expose `tesseract` via `PATH`. |

## 3. Teacher workflow

1. Teachers select the class, then upload a PNG/JPG marksheet. Mobile browsers can capture a fresh photo.
2. The backend extracts rows and shows a preview table (student code, parsed scores, extracted line).
3. If the confidence falls below the threshold or manual review is forced, the system retains the parsed rows and shows an “Apply parsed marks” button.
   - This staged data is held in the teacher’s session until they confirm or cancel, so they can review before persisting.
4. When everything looks correct, clicking **Apply parsed marks** writes the deltas (`seq1`, `seq2`, `exam`, etc.) to the matching students and clears the pending preview (a `GradeAudit` entry is created with change type `OCR Upload` for traceability).

## 4. Troubleshooting
* If you see “Tesseract is not available…” the backend couldn’t locate the native binary. Install Tesseract and/or set `MARKSHEET_OCR_COMMAND`.
* Parsing results will print a warning if no numeric rows are recognized—adjust the sheet layout or lighting and re-upload.
* For low confidence returns, the preview table highlights unmatched rows; reviewing and confirming ensures only verified data is committed.
