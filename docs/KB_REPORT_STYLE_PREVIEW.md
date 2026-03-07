# KB: Report Style Preview & PDF Workflow

## Admin controls
- Navigate to **Site Settings → Report Styles** to edit the template metadata.
  - layout_type: choose 	erm or nnual so the builder knows which template to use.
  - preview_contact: email/phone displayed in the preview modal footer.
  - logo_path, header_text, ooter_notes: text blocks that render inside the PDF.
  - is_active: flip the toggle to enable/disable that design.
- Each template references 	emplates/reports/term_report_card.html or 	emplates/reports/annual_report_card.html (customize as needed).

## Preview + download flow
1. The builder UI now shows a **Preview report** button beside the save action (guarded by eports.view or eports.preview permission).
2. Clicking the button calls /reports/preview/<report_id>/ which renders the chosen template with the saved rubric and marks the preview as last_previewed_at.
3. The preview page exposes a **Download PDF** link powered by the weasyprint driver; downloading is permission-checked (eports.pdf_download).
4. Admins can configure the default template via the report style record so guardians see the term layout while admins can opt for the annual design instead.

## Best practices
- Keep the template sections synced with the data keys saved by the builder (student info, scores, remarks).
- Use eports/tests/test_preview.py as a reference for permission guards and sample data overrides.
- Document any new template or PDF export in this KB so support knows how to update it.
