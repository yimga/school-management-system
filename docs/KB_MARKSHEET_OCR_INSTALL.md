# Knowledge Base: Marksheet OCR

## What It Does

Marksheet OCR reads student codes and scores from a PNG, JPG, or WebP image. It
only creates a proposal. A teacher must review the proposal before any grade is
saved.

## Device OCR

1. Open **Marks Entry** and load the class roster.
2. Choose the marksheet image.
3. Click **Run on this device**.
4. On first use, allow the browser to download about 22 MB of self-hosted OCR
   runtime and English language data.
5. Review the highlighted cells. Existing marks are preserved when delta mode
   is enabled.
6. Click **Save All Marks** after reviewing every proposed value.

The image remains in the browser. After the first successful load, the service
worker cache allows the local runtime to work without internet. If the save is
offline, the existing encrypted grade queue handles reconnection, idempotency,
tenant validation, and conflict review.

## Server OCR

Install Tesseract when schools also need the server proposal path:

| Platform | Installation |
| --- | --- |
| Windows | Install from the official Tesseract project and add it to `PATH`. |
| macOS | `brew install tesseract` |
| Ubuntu/Debian | `sudo apt install -y tesseract-ocr` |
| CentOS/RHEL | `sudo dnf install -y tesseract` |

Set `MARKSHEET_OCR_COMMAND` when the binary is not on `PATH`, or configure the
same value in Site Settings.

Teacher steps:

1. Choose the image.
2. Click **Create server review proposal**.
3. Correct the staged values.
4. Check **I reviewed the student matches and every proposed score**.
5. Click **Apply teacher-confirmed proposal**.

Server confidence cannot bypass these steps.

## Troubleshooting

- Use a high-contrast image with the student code first on each row.
- Keep each score between 0 and 20.
- If device OCR reports uncached assets while offline, connect once and run it
  successfully before retrying offline.
- If server OCR is unavailable, check `tesseract --version` and
  `MARKSHEET_OCR_COMMAND`.
- Unmatched student codes are never applied.

## Operator Verification

```powershell
python scripts/verify_offline_ocr_proposal.py
```

The gate checks the pinned asset manifest, human-confirmation enforcement,
browser proposal behavior, and a real Chromium OCR run restricted to localhost.
