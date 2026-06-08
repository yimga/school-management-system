# Marksheet OCR And Mandatory Review

OCR always creates a proposal. Confidence never authorizes a grade write. A
teacher must review the student matches and every score, then explicitly confirm
the server proposal or use the existing **Save All Marks** action for a device
proposal.

## Server Runtime

1. Install Tesseract on the server:
   - Windows: install from the official Tesseract project and add the binary to
     `PATH`.
   - macOS: `brew install tesseract`.
   - Ubuntu/Debian: `sudo apt install tesseract-ocr`.
2. Run `tesseract --version`.
3. If the binary is not on `PATH`, set `MARKSHEET_OCR_COMMAND` or configure the
   Tesseract command in Site Settings.

The server runtime is a fallback. Device OCR does not require a server
Tesseract installation.

## Admin Controls

| Control | Current purpose |
| --- | --- |
| Enable marksheet OCR uploads | Enables both proposal paths for teachers. |
| OCR confidence threshold | Compatibility/display threshold only; it never bypasses teacher review. |
| Force manual review | Retained for compatibility. Manual review is mandatory for grade OCR. |
| Allow mobile uploads | Shows camera/file guidance on supported devices. |
| Tesseract command | Selects the server-side Tesseract binary. |

## Teacher Workflow

1. Select the class and subject, then choose a PNG, JPG, or WebP image up to
   8 MB.
2. Choose one proposal path:
   - **Create server review proposal** runs the configured server Tesseract
     provider.
   - **Run on this device** runs pinned, self-hosted Tesseract.js. The first run
     downloads about 22 MB of runtime and English language assets. The image
     stays in the browser.
3. Review every matched student and score.
4. Complete the write through the canonical path:
   - Server proposal: check the review attestation and click
     **Apply teacher-confirmed proposal**.
   - Device proposal: review the highlighted gradebook cells and click
     **Save All Marks**.

Device OCR retains confidence and source bounding boxes in the proposal. It has
no submit, fetch, or grade-write capability. Offline grade saves use the
existing encrypted grade WAL/outbox, tenant binding, idempotency, and manual
conflict policy.

## Offline And Retention

- The service worker caches the self-hosted OCR files after the first successful
  device run, allowing later runs without internet.
- Server proposals are held in the authenticated teacher session.
- Device proposal evidence is held in tab-scoped session storage. The image is
  not persisted by RunMyCampus.
- Confirmed server writes create the normal OCR grade audit record. Device
  proposals use the normal grade save/WAL audit path.

## Verification

Run:

```powershell
python scripts/vendor_tesseract_ocr.py
python scripts/verify_offline_ocr_proposal.py
```

The composite gate validates asset checksums, the no-auto-write contract,
Django integration tests, browser unit tests, and a localhost-only Chromium OCR
smoke with external network requests blocked.
