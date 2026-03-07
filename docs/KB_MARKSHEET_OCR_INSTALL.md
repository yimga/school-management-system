# Knowledge Base: Marksheet OCR Setup & Mobile Guidance

## 1. Purpose
This KB page explains how schools install/configure the Tesseract OCR binary so teachers can upload handwritten marksheets, and how mobile users complete the workflow.

## 2. Server-side Requirements

### 2.1. Install Tesseract on the Host
| Platform | Command | Notes |
| --- | --- | --- |
| **Windows** | 1. Download [Tesseract installer](https://github.com/tesseract-ocr/tesseract/releases/latest).<br>2. Run installer (default path `C:\Program Files\Tesseract-OCR`).<br>3. Add that folder to `PATH`. | Restart the application pool/service after installation so the backend sees `tesseract`. |
| **macOS** | `brew install tesseract` | Use `brew --prefix tesseract` to confirm the binary location. |
| **Ubuntu/Debian** | `sudo apt update && sudo apt install -y tesseract-ocr` | Install language packs if you need languages beyond English (e.g., `tesseract-ocr-fra`). |
| **CentOS/RHEL** | `sudo dnf install -y tesseract` | Enable EPEL if missing. |

### 2.2. Configure the Command Path
1. Set the environment variable `MARKSHEET_OCR_COMMAND` to the absolute binary path (e.g., `/usr/local/bin/tesseract` or `C:\Program Files\Tesseract-OCR\tesseract.exe`).  
2. Alternatively, open **Site Settings → Marksheet OCR & Mobile Upload** and populate **Tesseract command** with the same absolute path.  
3. Restart any worker processes (Django, Celery, etc.) so they load the updated env var/setting.

### 2.3. Confirm Readiness
- Visit **Marks Entry → Upload Marksheet (OCR)** as a teacher.  
- The card will show **“Using <command> (vX.X.X)”** if Tesseract is available.  
- If the badge says “Blocked” or shows a warning, re-check the path and restart the service.

## 3. Teacher Workflow (Desktop & Mobile)

### 3.1. Preparing the Sheet
1. Use a clean, high-contrast handwritten marksheet template with student codes in the leftmost column and the related score columns separated by whitespace or columns.  
2. Scan or photograph at 300 DPI if possible; avoid glare and skew.

### 3.2. Desktop Upload
1. Pick the desired class/subject and click **Upload Marksheet (OCR)**.  
2. Choose the PNG/JPG file (max 8 MB).  
3. Click **Parse & Apply**.  
4. Review the preview table—each row shows extracted code, matched student name (if available), scores, and the auto-graded line.  
5. If the card requests manual verification (low confidence or forced), click **Apply parsed marks** after confirming the values. The system records a `GradeAudit` entry with `change_type = OCR Upload`.

### 3.3. Mobile Upload
1. From any modern mobile browser, open the same marks entry page.  
2. Tap **Choose File** and either capture a live photo or select an existing image (the hint “Works on mobile – choose or capture a photo directly” confirms support).  
3. Follow the same preview/confirmation steps as desktop.  

### 3.4. Audit Trace & Troubleshooting
- Every OCR-applied save adds a `GradeAudit` entry labeled **OCR Upload**; admins can filter the audit trail by that change type for traceability.  
- If no rows match the parse, check the student codes and retake the photo (better lighting, avoid cursive).  
- For low-confidence results, the system keeps the preview in the teacher’s session until they either confirm (Apply) or upload a new sheet.

## 4. Support Contacts
- If Tesseract is unavailable on your server, contact the devops/IT team with the installer link and the `MARKSHEET_OCR_COMMAND` path.  
- Provide a screenshot of the warning on the marks entry card so we can diagnose missing binaries or permission issues.
